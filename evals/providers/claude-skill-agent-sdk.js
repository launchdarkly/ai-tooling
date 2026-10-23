/**
 * Promptfoo provider that runs a Claude agent via @anthropic-ai/claude-agent-sdk
 * with the skill loaded the way a real Claude Code session would load it: by
 * dropping it into `.claude/skills/<slug>/SKILL.md` and letting the SDK
 * preload it through the agent definition's `skills` field.
 *
 * Why use the SDK loader instead of packing SKILL.md as a system prompt:
 *  - Real Claude Code reads SKILL.md off disk, prepends its own system prompt,
 *    has its own tool naming, and triggers skills through agent definitions.
 *    Inlining SKILL.md as `system` would measure the skill in a clean room but
 *    bypass every one of those real-world mechanics. The SDK provider keeps the
 *    eval on the same path users hit when they install the skill.
 *  - Tool calls go through SDK MCP plumbing into an in-process mock server, so
 *    the trajectory output is { response, first_assistant_text, kickoff_text,
 *    assistant_turns, trajectory, tools_called, turn_count, terminated } and
 *    every existing assertion keeps working without modification.
 *
 * Promptfoo provider config (set via `config:` in promptfooconfig.yaml):
 *   skill_slug             - REQUIRED. Folder name of the skill to load.
 *                            Resolved under skills/<category>/<slug>/ or
 *                            skills/<slug>/ (whichever exists).
 *   allow_builtins         - When true, expose Claude Code's built-in tools
 *                            (Read/Grep/Glob/Bash/Edit/Write/...). Default false.
 *   expose_mcp_tools       - Default true. Set false for skills that should never
 *                            call LaunchDarkly MCP tools (routing/advisory skills).
 *   force_skill_invocation - Default false. When true, set initialPrompt to
 *                            `/<skill_slug>` to explicitly invoke the skill via
 *                            slash command. Use for routing/advisory skills whose
 *                            description-based activation is unreliable in eval.
 *   expose_ask_question    - Default false. When true, expose a second in-process
 *                            MCP server with an `ask-question` tool that records
 *                            calls into the trajectory and returns a canned answer.
 *
 * Test-level vars:
 *   user_request                - the user turn the agent sees
 *   codebase_context            - optional snippets appended in a <codebase_context> tag
 *   git_diff                    - optional unified diff appended in a <git_diff> tag,
 *                                 e.g. the diff of a PR the agent is asked to assess.
 *                                 May be wrapped in `{% raw %}...{% endraw %}` so a
 *                                 diff containing `{{ }}` (JSX/Go templates) survives
 *                                 promptfoo's Nunjucks var rendering; the wrapper is
 *                                 stripped here (see stripRawWrapper).
 *   max_turns                   - per-test override, clamped to 1..30 (default 15)
 *   expose_mcp_tools            - per-test override of the provider config option
 *                                 (true/false), e.g. to run one test with no
 *                                 LaunchDarkly tools
 *   mock_ask_question_answers   - optional array of `selected` arrays returned by
 *                                 successive `ask-question` calls
 *   mock_files                  - optional object mapping relative file paths to
 *                                 string content, written into the isolated cwd
 *                                 before the agent runs
 *
 * Environment variables:
 *   AGENT_MODEL          - SUT model (default claude-sonnet-4-6).
 *   ANTHROPIC_API_KEY    - Auth for the SDK's child Claude Code process.
 *   SKILL_EVAL_DEBUG=1   - Dump every SDK message to a temp file for inspection.
 */

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { z } = require("zod");

const { renderMockResponse, createMockState } = require("./_mock");
const { inputSchemaToZodShape } = require("./_jsonschema-to-zod");

const DEFAULT_MAX_TURNS = 15;
const MODEL = process.env.AGENT_MODEL || "claude-sonnet-4-6";

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const SKILLS_ROOT = path.join(REPO_ROOT, "skills");

const toolDefs = JSON.parse(
  fs.readFileSync(path.join(__dirname, "../tools/definitions.json"), "utf-8"),
);

const mockTemplates = JSON.parse(
  fs.readFileSync(path.join(__dirname, "../mocks/tool-responses.json"), "utf-8"),
);

/**
 * Find the on-disk path to the skill folder named `slug`. Skills live under
 * either `skills/<category>/<slug>/SKILL.md` or `skills/<slug>/SKILL.md` for
 * uncategorised skills. Returns the absolute directory or null.
 */
function resolveSkillSource(slug) {
  const direct = path.join(SKILLS_ROOT, slug);
  if (fs.existsSync(path.join(direct, "SKILL.md"))) return direct;

  for (const category of fs.readdirSync(SKILLS_ROOT, { withFileTypes: true })) {
    if (!category.isDirectory()) continue;
    const candidate = path.join(SKILLS_ROOT, category.name, slug);
    if (fs.existsSync(path.join(candidate, "SKILL.md"))) return candidate;
  }
  return null;
}

/**
 * Create a fully-isolated cwd for a single test invocation. Each callApi call
 * gets its own temp directory so concurrent tests for the same skill slug
 * cannot interfere with each other.
 *
 *   <tmpdir>/ld-eval-<slug>-XXXXXX/
 *     .claude/skills/<slug>/  -> symlink to skill source
 *     .isolated-claude-config/
 *     .mcp.json               (empty stub so SDK doesn't walk up to real .mcp.json)
 */
function createInvocationCwd(slug, skillSource) {
  const cwd = fs.mkdtempSync(path.join(os.tmpdir(), `ld-eval-${slug}-`));

  const skillsDir = path.join(cwd, ".claude", "skills");
  fs.mkdirSync(skillsDir, { recursive: true });
  fs.symlinkSync(skillSource, path.join(skillsDir, slug), "dir");

  const isolatedConfig = path.join(cwd, ".isolated-claude-config");
  fs.mkdirSync(isolatedConfig, { recursive: true });

  // Empty .mcp.json prevents the SDK from walking up and finding the repo-root
  // .mcp.json, which points at the real hosted LaunchDarkly MCP server.
  fs.writeFileSync(
    path.join(cwd, ".mcp.json"),
    JSON.stringify({ mcpServers: {} }, null, 2),
  );

  return { cwd, isolatedConfig };
}

function scaffoldMockFiles(cwd, mockFiles) {
  if (!mockFiles || typeof mockFiles !== "object") return;
  for (const [relPath, content] of Object.entries(mockFiles)) {
    const absPath = path.join(cwd, relPath);
    fs.mkdirSync(path.dirname(absPath), { recursive: true });
    fs.writeFileSync(
      absPath,
      typeof content === "string" ? content : JSON.stringify(content, null, 2),
      "utf-8",
    );
  }
}

/**
 * Strip a leading `{% raw %}` and trailing `{% endraw %}` (with any surrounding
 * whitespace) from a var value. Fixtures use this wrapper so diff/snippet
 * content containing `{{ ... }}` survives promptfoo's Nunjucks var rendering
 * without a "Template render error". A no-op when no wrapper is present.
 */
function stripRawWrapper(value) {
  if (typeof value !== "string") return value;
  const m = value.match(/^\s*\{%\s*raw\s*%\}\n?([\s\S]*?)\n?\{%\s*endraw\s*%\}\s*$/);
  return m ? m[1] : value;
}

// A test can override the suite's expose_mcp_tools config for itself. YAML may
// hand the var over as a boolean or as the string "true"/"false"; any other
// value falls back to the config.
function resolveExposeMcpTools(configValue, varValue) {
  if (varValue === false || varValue === "false") return false;
  if (varValue === true || varValue === "true") return true;
  return configValue;
}

function clampMaxTurns(raw) {
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return DEFAULT_MAX_TURNS;
  return Math.min(30, Math.max(1, Math.floor(n)));
}

function previewMock(mock) {
  const s = JSON.stringify(mock);
  return s.length > 200 ? s.slice(0, 200) + "..." : s;
}

let sdkPromise = null;
function loadSdk() {
  if (!sdkPromise) {
    sdkPromise = import("@anthropic-ai/claude-agent-sdk");
  }
  return sdkPromise;
}

class ClaudeSkillAgentSdk {
  constructor(options = {}) {
    const config = options.config || {};
    if (!config.skill_slug) {
      throw new Error(
        "claude-skill-agent-sdk requires `config.skill_slug` (the folder name under skills/).",
      );
    }
    this.skillSlug = config.skill_slug;
    this.allowBuiltins = Boolean(config.allow_builtins);
    this.exposeMcpTools = config.expose_mcp_tools !== false;
    this.forceSkillInvocation = Boolean(config.force_skill_invocation);
    this.exposeAskQuestion = Boolean(config.expose_ask_question);

    const source = resolveSkillSource(this.skillSlug);
    if (!source) {
      throw new Error(
        `claude-skill-agent-sdk: could not find SKILL.md for slug "${this.skillSlug}" under ${SKILLS_ROOT}/`,
      );
    }
    this.skillSource = source;
  }

  id() {
    return `claude-skill-agent-sdk:${this.skillSlug}`;
  }

  async callApi(_prompt, context) {
    const apiKey = process.env.ANTHROPIC_API_KEY;
    if (!apiKey) {
      return { error: "ANTHROPIC_API_KEY environment variable is not set" };
    }

    const userRequest =
      context?.vars?.user_request || "Help me with LaunchDarkly";
    // A diff/snippet var may be wrapped in a Nunjucks `{% raw %}...{% endraw %}`
    // block. promptfoo renders string vars through Nunjucks before the provider
    // runs, and raw source containing `{{ ... }}` (JSX props, Go templates, etc.)
    // otherwise crashes that render with "expected variable end". Fixtures wrap
    // such content in a raw block to pass it through literally; we strip the
    // wrapper here before the agent sees it.
    const codebaseContext = stripRawWrapper(context?.vars?.codebase_context || "");
    const gitDiff = stripRawWrapper(context?.vars?.git_diff || "");
    const maxTurns = clampMaxTurns(context?.vars?.max_turns);
    const exposeMcpTools = resolveExposeMcpTools(
      this.exposeMcpTools,
      context?.vars?.expose_mcp_tools,
    );
    const askQuestionAnswers = Array.isArray(
      context?.vars?.mock_ask_question_answers,
    )
      ? context.vars.mock_ask_question_answers
      : [];
    const mockFiles = context?.vars?.mock_files || {};

    let userMessage = userRequest;
    if (codebaseContext) {
      userMessage += `\n\n<codebase_context>\n${codebaseContext}\n</codebase_context>`;
    }
    if (gitDiff) {
      userMessage += `\n\n<git_diff>\n${gitDiff}\n</git_diff>`;
    }

    const { cwd, isolatedConfig } = createInvocationCwd(
      this.skillSlug,
      this.skillSource,
    );
    scaffoldMockFiles(cwd, mockFiles);

    const sdk = await loadSdk();
    const { query, createSdkMcpServer, tool } = sdk;

    const trajectory = [];
    let currentTurn = 0;
    const mockState = createMockState();

    const mcpTools = exposeMcpTools
      ? toolDefs.map((def) =>
          tool(
            def.name,
            def.description,
            inputSchemaToZodShape(def.input_schema),
            async (args) => {
              const template = mockTemplates[def.name];
              const mock = template
                ? renderMockResponse(template, args, def.name, mockState)
                : { error: `No mock configured for tool: ${def.name}` };

              trajectory.push({
                tool: def.name,
                arguments: args,
                turn: currentTurn,
                mock_response_preview: previewMock(mock),
              });

              return {
                content: [{ type: "text", text: JSON.stringify(mock) }],
              };
            },
          ),
        )
      : [];

    const mockServer = exposeMcpTools
      ? createSdkMcpServer({ name: "launchdarkly-mocks", tools: mcpTools })
      : null;

    let askQuestionCallCount = 0;
    const askQuestionTools = this.exposeAskQuestion
      ? [
          tool(
            "ask-question",
            "Ask the user a structured, blocking question with a list of options and wait for their selection.",
            {
              prompt: z.string().describe("The question to display to the user."),
              options: z
                .array(
                  z.object({
                    id: z.string().describe("Stable identifier for the option."),
                    label: z.string().describe("Display text shown to the user."),
                  }),
                )
                .min(2)
                .describe("At least two options for the user to choose from."),
              multi: z
                .boolean()
                .optional()
                .describe("If true, the user can select multiple options."),
            },
            async (args) => {
              const idx = askQuestionCallCount++;
              const override = askQuestionAnswers[idx];
              let selected;
              if (Array.isArray(override) && override.length > 0) {
                selected = override;
              } else if (Array.isArray(args.options) && args.options.length > 0) {
                selected = [args.options[0].id];
              } else {
                selected = [];
              }
              const response = { selected };

              trajectory.push({
                tool: "ask-question",
                arguments: args,
                turn: currentTurn,
                mock_response_preview: previewMock(response),
              });

              return {
                content: [{ type: "text", text: JSON.stringify(response) }],
              };
            },
          ),
        ]
      : [];

    const harnessServer = this.exposeAskQuestion
      ? createSdkMcpServer({ name: "harness-ux", tools: askQuestionTools })
      : null;

    const allowedMcpToolNames = [];
    if (exposeMcpTools) {
      for (const def of toolDefs) {
        allowedMcpToolNames.push(`mcp__launchdarkly-mocks__${def.name}`);
      }
    }
    if (this.exposeAskQuestion) {
      allowedMcpToolNames.push("mcp__harness-ux__ask-question");
    }

    const agentTools = this.allowBuiltins ? undefined : allowedMcpToolNames;

    const harnessPrompt = [
      `You are running under an evaluation harness. The skill "${this.skillSlug}" is loaded into your context.`,
      exposeMcpTools
        ? "LaunchDarkly MCP tools are exposed as in-process mocks for this run; treat them as pre-authorized and call them when the skill directs you to."
        : "No LaunchDarkly MCP tools are available for this run.",
      this.exposeAskQuestion
        ? "An `ask-question` tool is available for blocking decision points where the skill says to ask the user a structured question with options."
        : null,
      "If the user message includes a <codebase_context> block, treat it as the authoritative description of the project. If you can also read files directly (Read/Glob/Bash), you may do so — the scaffolded files will match what the context describes.",
      "Do not run package manager install commands (`npm install`, `npm ci`, `yarn add`, `pnpm add`, `pnpm install`). Simulate them as having completed successfully.",
      "Do not start dev servers or run port checks. When the skill instructs you to start a server, skip the Bash call and immediately tell the user the server is running on its default port, then proceed to the next step.",
    ]
      .filter(Boolean)
      .join("\n\n");

    const mcpServersMap = {};
    if (mockServer) mcpServersMap["launchdarkly-mocks"] = mockServer;
    if (harnessServer) mcpServersMap["harness-ux"] = harnessServer;

    const queryOptions = {
      cwd,
      settingSources: ["project"],
      mcpServers: mcpServersMap,
      model: MODEL,
      maxTurns,
      permissionMode: "bypassPermissions",
      allowDangerouslySkipPermissions: true,
      persistSession: false,
      env: {
        ...process.env,
        CLAUDE_CONFIG_DIR: isolatedConfig,
      },
      agent: "eval-agent",
      agents: {
        "eval-agent": {
          description: "Evaluation harness agent for LaunchDarkly skills.",
          prompt: harnessPrompt,
          skills: [this.skillSlug],
          ...(this.forceSkillInvocation
            ? { initialPrompt: `/${this.skillSlug}` }
            : {}),
          ...(agentTools ? { tools: agentTools } : {}),
        },
      },
    };

    if (!this.allowBuiltins) {
      queryOptions.tools = [];
    }

    let finalText = "";
    let firstAssistantText = "";
    let lastAssistantText = "";
    const assistantTurns = [];
    let kickoffText = "";
    let kickoffSealed = false;
    let resultMessage = null;
    let terminationReason = null;
    const debug = process.env.SKILL_EVAL_DEBUG === "1";
    const allMessages = [];

    const isMaxTurnsMessage = (text) =>
      typeof text === "string" && /maximum number of turns/i.test(text);

    const extractAssistantText = (msg) => {
      const content =
        (msg && msg.message && msg.message.content) ||
        (msg && msg.content) ||
        null;
      if (!Array.isArray(content)) return "";
      return content
        .filter((b) => b && b.type === "text" && typeof b.text === "string")
        .map((b) => b.text)
        .join("\n")
        .trim();
    };

    // Internal orchestration tools that fire before the skill's instructed
    // kickoff prose — not "agent took action" signals.
    const KICKOFF_META_TOOLS = new Set(["Skill", "ToolSearch"]);
    const hasKickoffSealingToolUse = (msg) => {
      const content =
        (msg && msg.message && msg.message.content) ||
        (msg && msg.content) ||
        null;
      if (!Array.isArray(content)) return false;
      return content.some(
        (b) =>
          b &&
          b.type === "tool_use" &&
          !KICKOFF_META_TOOLS.has(b.name),
      );
    };

    try {
      const q = query({ prompt: userMessage, options: queryOptions });
      for await (const msg of q) {
        if (debug) allMessages.push(msg);
        if (msg.type === "assistant") {
          currentTurn += 1;
          const text = extractAssistantText(msg);
          if (text) {
            if (!firstAssistantText) firstAssistantText = text;
            lastAssistantText = text;
            assistantTurns.push({ turn: currentTurn, text });
            if (!kickoffSealed) {
              kickoffText += (kickoffText ? "\n\n" : "") + text;
            }
          }
          if (!kickoffSealed && hasKickoffSealingToolUse(msg)) {
            kickoffSealed = true;
          }

          // Track builtin tool calls (Bash, Read, Write, Edit, Glob, Grep,
          // etc.) in the trajectory. MCP calls are already recorded via their
          // mock callbacks. Internal framework tools are excluded.
          const msgContent =
            (msg && msg.message && msg.message.content) ||
            (msg && msg.content) ||
            null;
          if (Array.isArray(msgContent)) {
            for (const block of msgContent) {
              if (
                block &&
                block.type === "tool_use" &&
                typeof block.name === "string" &&
                !block.name.startsWith("mcp__") &&
                !KICKOFF_META_TOOLS.has(block.name)
              ) {
                trajectory.push({
                  tool: block.name,
                  arguments: block.input || {},
                  turn: currentTurn,
                  mock_response_preview: null,
                });
              }
            }
          }
        } else if (msg.type === "result") {
          resultMessage = msg;
          if (msg.subtype === "success" && typeof msg.result === "string") {
            finalText = msg.result;
          } else if (typeof msg.subtype === "string") {
            terminationReason = msg.subtype;
          }
        }
      }
    } catch (err) {
      const errMessage = err && err.message ? err.message : String(err);
      if (isMaxTurnsMessage(errMessage)) {
        terminationReason = terminationReason || "max_turns";
      } else {
        return { error: `claude-skill-agent-sdk failed: ${errMessage}` };
      }
    } finally {
      try {
        fs.rmSync(cwd, { recursive: true, force: true });
      } catch {
        // ignore cleanup errors
      }
    }

    if (!finalText && lastAssistantText) {
      finalText = lastAssistantText;
    }

    if (debug) {
      const debugDump = path.join(
        os.tmpdir(),
        `ld-eval-debug-${this.skillSlug}-${Date.now()}.json`,
      );
      try {
        fs.writeFileSync(
          debugDump,
          JSON.stringify(allMessages, (_k, v) => {
            if (v && typeof v === "object" && typeof v.then === "function")
              return "[Promise]";
            return v;
          }, 2),
        );
        console.error(`[skill-eval-debug] wrote ${debugDump}`);
      } catch (e) {
        console.error(`[skill-eval-debug] failed to write dump: ${e.message}`);
      }
    }

    const modelUsage = resultMessage?.modelUsage || {};
    let inputTokens = 0;
    let outputTokens = 0;
    for (const entry of Object.values(modelUsage)) {
      inputTokens +=
        (entry?.inputTokens || 0) +
        (entry?.cacheReadInputTokens || 0) +
        (entry?.cacheCreationInputTokens || 0);
      outputTokens += entry?.outputTokens || 0;
    }
    if (inputTokens === 0 && outputTokens === 0) {
      inputTokens = resultMessage?.usage?.input_tokens || 0;
      outputTokens = resultMessage?.usage?.output_tokens || 0;
    }

    const cost =
      typeof resultMessage?.total_cost_usd === "number"
        ? resultMessage.total_cost_usd
        : 0;
    const turnCount =
      typeof resultMessage?.num_turns === "number"
        ? resultMessage.num_turns
        : currentTurn;

    return {
      output: JSON.stringify({
        response: finalText || "(no final response captured)",
        first_assistant_text: firstAssistantText,
        kickoff_text: kickoffText,
        assistant_turns: assistantTurns,
        trajectory,
        tools_called: trajectory.map((t) => t.tool),
        turn_count: turnCount,
        terminated: terminationReason,
      }),
      tokenUsage: {
        total: inputTokens + outputTokens,
        prompt: inputTokens,
        completion: outputTokens,
      },
      cost,
    };
  }
}

module.exports = ClaudeSkillAgentSdk;
// Exposed for unit tests; the promptfoo loader uses the class default export.
module.exports.stripRawWrapper = stripRawWrapper;
module.exports.resolveExposeMcpTools = resolveExposeMcpTools;
