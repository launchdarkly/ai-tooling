---
name: onboarding
description: "Onboard a project to LaunchDarkly: kickoff roadmap, resumable log, explore repo, MCP, companion flag skills, nested SDK install (detect/plan/apply), first flag. Use when adding LaunchDarkly, setting up or integrating feature flags in a project, SDK integration, or 'onboard me'."
license: Apache-2.0
compatibility: Requires an MCP-capable coding agent, `npx` on PATH for optional skill installs, and a LaunchDarkly account. SDK keys, client-side IDs, mobile keys, and API tokens are only needed when the step that uses them runs (see Prerequisites).
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# LaunchDarkly SDK Onboarding

Orchestrates LaunchDarkly setup in an existing codebase: on kickoff, show a **roadmap** in chat (see [Kickoff: onboarding roadmap](#kickoff-onboarding-roadmap)); **Step 0** writes a living onboarding log so a new session or the user can resume; then explore the project, detect the agent, install flag-management skills, **configure the LaunchDarkly MCP server early**, install and initialize the SDK (**sdk-install** and nested detect/plan/apply), and create a **first feature flag**. Nested skills: [mcp-configure](mcp-configure/SKILL.md), [sdk-install](sdk-install/SKILL.md), [first-flag](first-flag/SKILL.md).

## Prerequisites

- **`npx`:** Available on PATH when using `npx skills add` to install companion skills (see Step 3).
- **LaunchDarkly account (outset only):** Early in onboarding -- right after the [Kickoff roadmap](#kickoff-onboarding-roadmap) if the log does not already say -- ask **only** whether the user already has a LaunchDarkly account (they can sign in at [https://app.launchdarkly.com](https://app.launchdarkly.com)). **Do not** ask in the same turn for SDK keys, client-side IDs, mobile keys, API access tokens, or whether keys are in env; defer those until the step that needs them (below).
  - **If they do not have an account yet:** Point them to https://app.launchdarkly.com/signup?source=agent. Continue with repo exploration, agent detection, and companion skills where those do not require LaunchDarkly API access; MCP OAuth and SDK work wait on account access.
  - **If they have an account:** Proceed through the workflow. Still **do not** prompt for SDK key material until **Step 5** [Apply code changes](sdk-install/apply/SKILL.md) (or until **run** if they prefer to paste into env later).
- **Keys and tokens (defer -- do not bundle with the account question):** Collect these only when the path requires them -- never as part of the initial "do you have an account?" prompt.
  - **Step 4 -- MCP:** **Hosted MCP** uses OAuth; no API token or SDK key needed to configure it. **Local `npx` MCP** (federal/EU, etc.): API access token per [mcp-configure](mcp-configure/SKILL.md) and [MCP Config Templates](mcp-configure/references/mcp-config-templates.md).
  - **Step 5 -- SDK:** **SDK keys / client-side ID / mobile key** when wiring env in [Apply code changes](sdk-install/apply/SKILL.md), after the integration plan is confirmed. **`ldcli` / REST** for discovery: use **`ldcli login`** or an access token when you first run those commands, not at hello.
  - **Key type must match the integration:** server-side SDK -> **SDK key**; browser/client-side SDK -> **Client-side ID**; mobile -> **Mobile key**. Env variable names and bundler rules: [Apply code changes](sdk-install/apply/SKILL.md).

**MCP (preferred):** Complete **Step 4** via [mcp-configure/SKILL.md](mcp-configure/SKILL.md) before SDK work when possible. If MCP is unavailable or the user opts out, use **ldcli** / **REST** fallbacks described in that skill (including [MCP Config Templates](mcp-configure/references/mcp-config-templates.md) for local `npx` fallback when hosted MCP does not apply) -- onboarding must still be completable.

**Optional MCP tools (when configured):**

- `get-environments` -- list environments for a project; the response includes SDK keys, client-side IDs, and mobile keys per environment. **Use this as the single source for all key types** -- do not make separate requests for individual keys.
- `create-feature-flag` -- create the boolean flag for [Step 6: Create Your First Feature Flag](#step-6-create-your-first-feature-flag).
- `update-feature-flag` -- toggle or patch flag configuration during Step 6; see [Create first feature flag](first-flag/SKILL.md) for ldcli/API fallbacks.

**Other MCP tools you may use if present** (not required): `list-feature-flags`, `get-feature-flag`, `get-flag-status-across-environments`.

## Agent Behavior Directives

### Progress Tracking

The roadmap (Steps 0-6 + follow-through) MUST be tracked using your agent's native task-tracking tool in addition to the onboarding log file.

- **Cursor:** Use `TodoWrite` to create a todo for each step before beginning work. Update status as each step completes.
- **Claude Code:** Use `TaskCreate` to create a task for each step (or `TodoWrite` if native tasks are unavailable).
- **Other agents:** If your agent provides a native task list or progress tracking tool, use it. If not, present a numbered checklist in chat and update it after each step.

Do NOT work through steps mentally or rely solely on the `LAUNCHDARKLY_ONBOARDING.md` log for in-session tracking.

### Decision Points

When a step requires user input to determine branching, you MUST collect the answer by calling a tool — do NOT write the question as prose text in your response.

**Call the tool directly.** Use the first tool from this list that
your environment provides:

1. `AskQuestion` — call it with a `prompt` and `options` array
2. `TaskAsk` or equivalent structured-input tool
3. (fallback) If the tool call fails or no such tool exists, THEN
   render the question as numbered options in text and wait.

Do NOT decide in advance whether you have the tool. Attempt the call. The tool call IS the question — do not also write the question as text.

Throughout this skill and its nested skills you will see decision-point markers formatted like this:

```
**D1 -- BLOCKING:** <instruction to call your question tool>
- question: "<the question>"
- options:
  - "<option A>" -> <what happens>
  - "<option B>" -> <what happens>
- STOP. Do not continue until the user selects an option.
```

These are **instructions for you to follow**, not content to display. When you reach one: make the tool call (or render numbered options if no tool exists), then STOP and wait. Do NOT copy the marker text into your response.

### User-Facing Communication

Every reply during onboarding must sound like a friendly, knowledgeable colleague walking someone through setup — not a workflow engine quoting internal instructions. Follow these rules in all user-facing output:

**Required response structure.** Every substantive onboarding reply must include:

1. **What we just did** — one or two sentences summarizing the completed action and its result.
2. **What we're doing next** — a plain-English preview of the next step.
3. **What you need to do** (only when the user has a manual action) — a concrete instruction, not a vague label like "Your turn." Include **where** to perform the action (e.g. "in Cursor's integrated terminal," "in the project folder," "in your browser," "in macOS Terminal").

**Forbidden in user-facing output:**

- Internal decision-point IDs (D1, D5, D7, etc.), step numbers as labels (e.g. "Step 5 -- detect"), or skill file names (e.g. "sdk-install/apply/SKILL.md").
- Quoting or paraphrasing raw skill instructions, directive headings, or markdown from these files.
- Workflow-engine language ("BLOCKING," "STOP," "call your structured question tool," "proceed to the next nested skill").

**When telling the user to run a command**, always say **where** to run it. Good examples:
- "Run this in the integrated terminal in your editor"
- "Run this from the project root in your terminal"
- "Open a terminal in the `packages/api` folder and run …"

Bad: "Run `npm install`" (without location context).

**Tone:** Friendly, conversational, and confident — like a knowledgeable colleague, not a manual. Use first person naturally (e.g. "I just detected that the flag was created, now I'm going to …"). Assume the reader is an engineer so don't over-explain basic concepts (what a package manager is, what an environment variable does), but do explain LaunchDarkly-specific concepts briefly on first mention (what a context is, what an SDK key is for, why there are different key types).

### Step Execution Rules

Do NOT treat the user's initial request (e.g. "onboard me," "set up LaunchDarkly") as blanket permission for file writes, installs, or configuration changes. Each action that modifies the repo, installs packages, or writes secrets requires its own consent at the step where it occurs.

**Blocking decision points** (you MUST halt and wait for the user's response before continuing):

| ID | Location | Question |
|----|----------|----------|
| D1 | Kickoff | Do you have a LaunchDarkly account? |
| D4-LOCAL | Step 4 (local MCP) | User chooses whether to handle the access token themselves (recommended) or let the agent help |
| D5-NOAPP | Step 5 -- detect | No runnable app found: user points to app or requests demo |
| D5-UNCLEAR | Step 5 -- detect | Weak evidence: user confirms the correct app folder |
| D5 | Step 5 -- detect | SDK confirmation / one-vs-both-SDKs scope choice |
| D6 | Step 5 -- plan | Approve the integration plan before any code changes |
| D7 | Step 5 -- apply | User chooses how secrets are set up: user-specified location, user handles it, or `.env` fallback |
| D8 | Step 5 -- apply | Approval before changing non-LaunchDarkly dependencies |
| D9 | Step 6 | Auth errors (401/403): stop, do not retry automatically |

**Non-blocking** (you may proceed automatically): Step 0 onboarding log (write it directly), Step 1 exploration (read-only), Step 3 skill install (installs to agent config, not the user's repo), Step 5 detect (file reads only), compile check (Step 5 apply Step 4), follow-through file writes (`LAUNCHDARKLY.md`, editor rules).

## Core Principles

1. **Detect, don't guess:** Inspect the repo for language, framework, and package manager.
2. **Minimal changes:** Add SDK code alongside existing code; don't restructure the project.
3. **Match existing patterns:** Follow env vars, config files, and initialization patterns already in use.
4. **Validate end-to-end:** Confirm the SDK is connected before treating the first flag as proof of success.
5. **Paper trail:** Keep the Step 0 onboarding log current so another agent or session can continue without re-deriving context.
6. **Orient the user first:** On a fresh onboarding request, show the [Kickoff roadmap](#kickoff-onboarding-roadmap) before substantive work so the user knows the full arc.
7. **Stage credential questions:** Confirm **account** at the outset; ask for **SDK keys / tokens** only in Step 4-5 when that step's skill says they are required ([Prerequisites](#prerequisites)).
8. **Deep-link to the dashboard:** When generating LaunchDarkly dashboard URLs and the **project key** and/or **environment key** are known (from MCP tools, user input, or the onboarding log), construct the most specific URL possible instead of linking to a generic page. Use these patterns:

   | What you need to show | URL pattern |
   |-----------------------|-------------|
   | Project flags list | `https://app.launchdarkly.com/projects/{projectKey}/flags` |
   | Specific flag | `https://app.launchdarkly.com/projects/{projectKey}/flags/{flagKey}` |
   | Environment keys / SDK keys | `https://app.launchdarkly.com/projects/{projectKey}/settings/environments/{envKey}/keys` |
   | Project environments list | `https://app.launchdarkly.com/projects/{projectKey}/settings/environments` |
   | All projects | `https://app.launchdarkly.com/projects` |

   Only generate deep links when the required keys are known from tool responses or confirmed user input. If they are unknown, use the most specific generic path available and tell the user how to navigate from there (e.g. "Open your project in the LaunchDarkly dashboard, then go to **Settings > Environments** to find your SDK key").

## Kickoff: onboarding roadmap

When the user invokes this onboarding flow (for example by asking you to follow this skill, run LaunchDarkly onboarding, or set up feature flags in the project), treat it as a **fresh kickoff** unless you are clearly resuming (see **Resuming** below).

### Kickoff sequence (new run — before any numbered step)

Perform these in **order** in the **same assistant turn**, then **stop at D1** until the user answers:

1. **Task list:** Call your native task tool ([Progress Tracking](#progress-tracking)) and create **one task per step for Steps 0 through 6** (seven tasks minimum — one for each numbered row in the table below). Do this **before** rendering the roadmap table so progress tracking is in place before you pause on D1.
2. **Roadmap:** Render the roadmap table below in the user-visible reply (adjust row wording only if an [Edge case](#edge-cases) will obviously skip a step). The roadmap is a chat artifact only -- **do not** create a file for it unless the user asks.
3. **D1:** Call your structured question tool for the account question (see **D1** below). **Do not** create or update `LAUNCHDARKLY_ONBOARDING.md`, explore the repo for Step 1, detect the agent for Step 2, or run **`npx`** (or any shell install) for Step 3 until the user has answered D1.

- **Resuming:** If `LAUNCHDARKLY_ONBOARDING.md` already exists, read it first per [Step 0](#step-0-create-or-refresh-the-onboarding-log). Show the same roadmap with a **Status** column filled from the log, or a shorter "where we are" summary -- whichever keeps the user oriented. Refresh the task list to match the log if needed; if D1 (account status) is already recorded in the log, **do not** ask D1 again -- continue from the log's **Next step**.

| Step | What happens | You get |
|------|--------------|---------|
| **0** -- Onboarding log | Create or refresh `LAUNCHDARKLY_ONBOARDING.md` (or `docs/...`) | Resumable checklist, context, next-step pointer |
| **1** -- Explore project | Detect language, framework, existing LD usage, environment type | Stack summary for the user |
| **2** -- Detect agent | Cursor, Claude Code, Copilot, etc. | Correct `--agent` for `npx skills add` |
| **3** -- Companion skills | `npx skills add ...` flag skills from `launchdarkly/ai-tooling` | `launchdarkly-flag-*` skills available |
| **4** -- MCP | Configure LaunchDarkly MCP; user restarts; agent auto-verifies on next turn | MCP tools (or ldcli/API fallback) |
| **5** -- SDK install | detect -> plan -> apply ([sdk-install](sdk-install/SKILL.md)) | Packages + init wired to env vars |
| **6** -- First flag | Create boolean flag, evaluate, toggle, add interactive demo ([first-flag](first-flag/SKILL.md)) | End-to-end proof + visible "wow" moment |
| **Follow-through** | Optional: `LAUNCHDARKLY.md`, editor rules ([1.8-summary](references/1.8-summary.md), [1.9-editor-rules](references/1.9-editor-rules.md)) | Durable docs for the repo |

**D1 -- BLOCKING** (end of kickoff sequence): Call your structured question tool now.

- question: "Do you already have a LaunchDarkly account you can sign into?"
- options:
  - "Yes, I have an account" -> proceed through full workflow
  - "No / not yet" -> point to https://app.launchdarkly.com/signup?source=agent, continue Steps 1-3 only
- STOP. Do not write the question as text. Do not continue until the user selects an option.

If they need an account, point them to https://app.launchdarkly.com/signup?source=agent and explain which later steps (MCP, SDK keys) will wait on it. Then proceed with [Step 0](#step-0-create-or-refresh-the-onboarding-log) (or the log's **Next step** if resuming).

## Workflow

Follow **Steps 0-6** in order unless an **Edge case** says otherwise. When **Step 6** (first flag) completes successfully, continue with [Default follow-through](#default-follow-through-not-numbered-steps).

### Step 0: Create or Refresh the Onboarding Log

Before substantive work, give this run a **durable paper trail** so a new agent or a later session can see what was decided, what ran, and what is next.

1. **Look for an existing log** at the repo root: `LAUNCHDARKLY_ONBOARDING.md`. If the project keeps docs under `docs/`, prefer `docs/LAUNCHDARKLY_ONBOARDING.md` when that folder already exists and the root file is absent.
2. **Create or update the log file.** This is part of the onboarding workflow -- write it directly without asking for permission.
3. **If resuming:** read the log first, align with the stated **next step**, and only redo work the log marks incomplete or invalid.
4. **What to write** (update after each numbered step finishes or when something important changes):
   - **Checklist:** Steps 0-6 with status (`not started` / `in progress` / `done` / `skipped` + brief reason).
   - **Context:** coding agent id (once known), language/framework summary, monorepo target path if any, LaunchDarkly **project key** and **environment key** when known (never paste secrets or full SDK keys -- say "stored in env" or "user provided offline").
   - **MCP:** configured yes/no, hosted vs fallback, link to config path if relevant.
   - **Commands run:** e.g. `npx skills add ...` (no secrets).
   - **Blockers / errors:** what failed and what was tried.
   - **Next step:** single explicit step number and name (e.g. "Step 5: Install and Initialize the SDK").
5. **After errors:** append or edit the log with what broke and where you are resuming.

This file is a **working** log during onboarding. After success, the user may delete it, archive it, or fold facts into `LAUNCHDARKLY.md` ([Onboarding Summary](references/1.8-summary.md)).

### Step 1: Explore the Project

Understand what you are integrating before installing packages.

1. **Identify language and framework.** Check dependency files: `package.json`, `go.mod`, `requirements.txt` / `pyproject.toml` / `Pipfile`, `pom.xml` / `build.gradle`, `Gemfile`, `*.csproj` / `*.sln`, `Cargo.toml`, etc.
2. **Check for existing LaunchDarkly usage.** Search for `launchdarkly`, `ldclient`, `ld-client`, `LDClient`, `@launchdarkly`.
   - If already present: note SDK version and patterns; you may shorten or skip [Step 5](#step-5-install-and-initialize-the-sdk) per edge cases.
   - If not present: plan full SDK setup.
3. **Identify environment type:** server-side app, client SPA, mobile, edge, etc. -- this drives SDK choice.
4. **Summarize to the user:** language, framework, environment type, whether LD is already integrated.

Deep detection details: [Detect repository stack](sdk-install/detect/SKILL.md) (nested under [sdk-install](sdk-install/SKILL.md)).

### Step 2: Detect the Agent Environment

Determine which coding agent is running so MCP config and `npx skills add --agent` use the right target. **Infer the agent silently — do not ask the user.**

1. Check for indicators (in priority order — stop at the first strong match):
   - **Cursor:** `.cursor/`, `.cursorrules`, or `CURSOR_` env vars
   - **Claude Code:** `~/.claude/`, `CLAUDE.md`, or `CLAUDE_` env vars
   - **Windsurf:** `.windsurfrules`
   - **GitHub Copilot:** `.github/copilot/`
   - **Codex:** `~/.codex/`, `AGENTS.md`

2. If multiple indicators are present, pick the one whose runtime you are **currently executing inside** (e.g. if you have access to Cursor-specific tools like `AskQuestion` or `TodoWrite`, you are in Cursor). If none of the indicators match, default to the agent whose tool surface you observe at runtime.

3. Remember the agent id for Step 3 (e.g. `cursor`, `claude-code`). Mention the detected agent briefly when presenting the Step 1/2 summary so the user can correct you if wrong, but do not block on a question.

### Step 3: Install Companion Skills

Install flag-management skills from the public repo so later steps can delegate when appropriate (see **Bundled vs public** below).

**From `launchdarkly/ai-tooling` (flag workflows):**

```bash
npx skills add launchdarkly/ai-tooling --skill launchdarkly-flag-create launchdarkly-flag-discovery launchdarkly-flag-targeting launchdarkly-flag-cleanup -y --agent <detected-agent>
```

Replace `<detected-agent>` with the value from Step 2. Confirm success; skip skills already installed.

**Bundled vs public:** Orchestration and setup for this flow live **in this folder** -- parent [SKILL.md](SKILL.md), nested [mcp-configure](mcp-configure/SKILL.md), [sdk-install](sdk-install/SKILL.md) (detect / plan / apply), [first-flag](first-flag/SKILL.md), and `references/` ([SDK recipes](references/sdk/recipes.md), [snippets](references/sdk/snippets/), summary, editor rules, etc.). The command above installs **flag-management** skills from the public [launchdarkly/ai-tooling](https://github.com/launchdarkly/ai-tooling) repo only.

### Step 4: Configure the MCP Server

Hand off to [mcp-configure/SKILL.md](mcp-configure/SKILL.md) for setup (hosted MCP, quick install, manual JSON, agent authorization).

MCP setup requires the user to act outside the agent (clicking a quick-install link, completing OAuth, enabling the server in editor settings). After presenting the instructions, **tell the user to restart or refresh the agent** so MCP tools become available. Then continue to Step 5 — do not block here with a confirmation question.

**Auto-verify on next turn:** When the conversation resumes (after the user restarts or sends a message), probe for MCP by calling a lightweight MCP tool such as `list-feature-flags` with the known project key. If the tool responds normally, MCP is live — note it in the onboarding log and use MCP tools for later steps. If the call fails or no MCP tools are visible, fall back silently to ldcli/API for Steps 5-6 and note the fallback in the onboarding log. **Do not ask** the user whether MCP is working — find out by trying it.

Do not duplicate MCP procedures in this file. Do not block Step 5 indefinitely on MCP.

### Step 5: Install and Initialize the SDK

If the project **already has LaunchDarkly installed and initialized** (see [detect decision tree](sdk-install/detect/SKILL.md#decision-tree)), skip to [Step 6: Create Your First Feature Flag](#step-6-create-your-first-feature-flag).

Otherwise hand off to [LaunchDarkly SDK Install (onboarding)](sdk-install/SKILL.md), which runs nested skills in order: [Detect repository stack](sdk-install/detect/SKILL.md) -> [Generate integration plan](sdk-install/plan/SKILL.md) -> [Apply code changes](sdk-install/apply/SKILL.md), using [SDK recipes](references/sdk/recipes.md) and [SDK snippets](references/sdk/snippets/). If the user asked for **both** server and client (e.g. API + SPA, Next.js server + browser), follow [Dual SDK integrations](sdk-install/plan/SKILL.md#dual-sdk-integrations) through plan and apply so **both** SDKs are really installed and initialized.

**Blocking decision points inside Step 5** (see nested skills): D5 (SDK scope), D6 (plan approval), D7 (secret consent), D8 (dependency changes). Do NOT batch tool calls across these boundaries.

### Step 6: Create Your First Feature Flag

Create and evaluate a boolean flag; toggle and observe end-to-end.

1. Follow [Create first feature flag](first-flag/SKILL.md).
2. If the **`launchdarkly-flag-create`** skill (installed in Step 3) is available, you may use it for create/evaluation wiring **only** while still completing the verify/toggle checklist in [Create first feature flag](first-flag/SKILL.md). Onboarding must remain completable without it.

Install or refresh flag skills via:

`npx skills add launchdarkly/ai-tooling --skill launchdarkly-flag-create -y --agent <detected-agent>`

See D9 in [first-flag](first-flag/SKILL.md) for the blocking stop on auth errors.

## Default follow-through (not numbered steps)

Do these when finishing onboarding -- same session when possible. They are **documentation and handoff** tasks, not repeats of Steps 0-6. **Do not skip this section** -- it is the primary deliverable the user keeps after onboarding.

**Setup summary (`LAUNCHDARKLY.md`) -- REQUIRED**

Generate the repo summary per [Onboarding Summary](references/1.8-summary.md). Write it directly -- this is part of the onboarding workflow. The generated `LAUNCHDARKLY.md` **must** include all of the following (see template in that reference):

1. **SDK Details** -- which SDK(s) are installed, package names, key types, initialization files
2. **Configuration** -- env var names, how secrets are managed, bundler-specific conventions
3. **Where to Find Things** -- dashboard links with real project key substituted
4. **How Feature Flags Work** -- a language-specific code example showing flag evaluation in this project's stack (not a generic snippet -- use the same pattern the agent wired during Step 5)
5. **Next Steps / Advanced Capabilities** -- links to Percentage Rollouts, Targeting Rules, Experimentation, AI Configs, Guarded Rollouts, and Observability
6. **AI Agent Integration** -- MCP server setup for continued agent-driven flag management

This is **not** the same file as `LAUNCHDARKLY_ONBOARDING.md`. The onboarding log is a working checklist; `LAUNCHDARKLY.md` is the **permanent reference** for the team.

**Clean up the onboarding log:** After writing `LAUNCHDARKLY.md`, **delete** `LAUNCHDARKLY_ONBOARDING.md` (or `docs/LAUNCHDARKLY_ONBOARDING.md` if that was the location used). This is part of the workflow -- do not ask for permission. Removing the working log avoids confusion from having two LaunchDarkly docs in the repo.

**Editor rules / skills**

- Add editor-specific rules or skill hooks per [Editor Rules and Skills](references/1.9-editor-rules.md). Write them directly -- this is part of the onboarding workflow.

## Edge Cases

| Situation | Action |
|-----------|--------|
| SDK already installed **and** initialized (see [detect decision tree](sdk-install/detect/SKILL.md#decision-tree)) | Skip **Step 5**; go to **Step 6** (First flag) |
| SDK in dependencies **but** not initialized | Continue **Step 5** from [apply](sdk-install/apply/SKILL.md) / init (see [sdk-install](sdk-install/SKILL.md)); do not skip validation |
| SDK state unclear | Re-run [Detect repository stack](sdk-install/detect/SKILL.md), then follow its decision tree |
| No runnable app found or app target unclear | Follow the workspace classification in [Detect: classify workspace confidence](sdk-install/detect/SKILL.md#5a-classify-workspace-confidence) — ask the user to point to the real app or offer to create a demo. Do not proceed to plan or apply without a confirmed app target. |
| Multiple languages in repo | **Blocking (D5):** use question tool to ask which target to integrate first -- do not guess |
| User wants **both** frontend and backend (or server + browser) in the same target | [Dual SDK plan](sdk-install/plan/SKILL.md#dual-sdk-integrations): two packages, two entrypoints, two inits; [apply](sdk-install/apply/SKILL.md) must complete **both** tracks |
| Monorepo | **Blocking (D5):** use question tool to ask which package/service to integrate -- do not assume the root |
| No package manager detected | **Blocking (D5):** use question tool to ask which SDK to install; provide manual install instructions from [SDK recipes](references/sdk/recipes.md) |
| Companion flag skills already installed (Step 3) | Skip re-running `npx skills add` for those skill names |
| Resuming after a break or new agent session | Read `LAUNCHDARKLY_ONBOARDING.md` (Step 0); continue from **Next step**; refresh the log as you go |
| MCP configuration fails or user declines MCP | Continue with **Step 5** using ldcli/API/dashboard per [mcp-configure](mcp-configure/SKILL.md); note limitation for flag tooling |
| User / repo already fully onboarded | Summarize state from Step 0 log and repo; offer next steps without redoing completed steps |

## What NOT to Do

- Don't install an SDK without exploring the project and detecting the stack (Steps 1 and 5); keep the Step 0 log updated as you go.
- Don't upgrade, pin, or add **non-LaunchDarkly** dependencies (peer-deps, lockfile churn, "latest" bumps) to install or compile the SDK without **explicit user approval** -- see [Apply -- Permission before changing other dependencies](sdk-install/apply/SKILL.md#permission-before-changing-other-dependencies).
- Don't hardcode SDK keys in source code -- always use environment variables (see [Apply code changes](sdk-install/apply/SKILL.md)).
- Don't restructure the user's project or refactor unrelated code.
- Don't create flags before **Step 5** (SDK install) completes.
- Don't write decision-point questions as chat text -- use your structured question tool (see [Decision Points](#decision-points)).

## References

**Continuity**

- Step 0 -- `LAUNCHDARKLY_ONBOARDING.md` (working log; see [Step 0](#step-0-create-or-refresh-the-onboarding-log))

**Step 4 -- MCP (nested skill is primary)**

- [mcp-configure/SKILL.md](mcp-configure/SKILL.md) -- hosted MCP, verify, edge cases (**follow this first**)
- [MCP UI links](mcp-configure/references/mcp-ui-links.md) -- HTTPS + `command:` links to open MCP settings per editor
- [MCP Config Templates](mcp-configure/references/mcp-config-templates.md) -- per-agent JSON; **Local server via `npx`** when hosted MCP is unavailable

**Step 5 -- SDK install (nested skills)**

- [sdk-install/SKILL.md](sdk-install/SKILL.md) -- orchestrates **detect -> plan -> apply** (**follow this first**)
- [Detect repository stack](sdk-install/detect/SKILL.md)
- [Generate integration plan](sdk-install/plan/SKILL.md)
- [Apply code changes](sdk-install/apply/SKILL.md)

**First flag (Step 6)**

- [Create first feature flag](first-flag/SKILL.md)

**Default follow-through**

- [Onboarding Summary](references/1.8-summary.md) -- template for `LAUNCHDARKLY.md`
- [Editor Rules and Skills](references/1.9-editor-rules.md)

**SDK index**

- [SDK recipes](references/sdk/recipes.md)
- [SDK snippets](references/sdk/snippets/)

**Public flag skills (install via Step 3)**

- [github.com/launchdarkly/ai-tooling](https://github.com/launchdarkly/ai-tooling) -- `launchdarkly-flag-create`, `launchdarkly-flag-discovery`, `launchdarkly-flag-targeting`, `launchdarkly-flag-cleanup`
