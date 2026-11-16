# Legacy to current Go AI SDK

Use with the inventory, user approval, and verification workflow in [SKILL.md](../SKILL.md). This is a code migration, not a change to existing AgentControl keys, variations, or tools.

## Sources and versions

- [Migration guide](https://launchdarkly.com/docs/sdk/ai/migration) and [Go reference](https://launchdarkly.com/docs/sdk/ai/go).
- Legacy: [`go-server-sdk-ai` v0.11.0](https://github.com/launchdarkly/go-server-sdk-ai/tree/v0.11.0/ldai), notably `client.go`, `config.go`, `ai_config_base.go`, `tracker.go`, and `judge/judge.go`.
- Older legacy: [`go-server-sdk/ldai` v0.9.4](https://github.com/launchdarkly/go-server-sdk/tree/ldai/v0.9.4/ldai). The package moved to `go-server-sdk-ai/ldai` at v0.10.0; that move alone is **not** the handler migration.
- Current: [`go-ai-sdk` v1.0.0](https://github.com/launchdarkly/go-ai-sdk/tree/v1.0.0), particularly `go.mod`, `aiserver/{config,types,lifecycle,registry,judges,tracking,graph,capture}.go`, and each handler's `handler.go`. Requires **Go 1.26+**. These examples target that tag; check installed exports before using another version. Its root README still describes 0.x early development despite the v1.0.0 tag; use the tag's source for API signatures.

## Assess: map each call site

| Legacy | Current |
|--------|---------|
| `ldai.NewClient(ldClient)` | Lazy environment initialization, or `aiserver.InitClient(ctx, aiserver.InitOptions{})`; reuse an existing client with `InitWithClient(ctx, ldClient, opts)` |
| `CompletionConfig`, deprecated `Config`, provider call + tracker | `openaimessages.OpenAIMessages(...)` for one provider/mode, or `aiserver.Config(aiserver.ConfigArgs{...}).Invoke(...)` |
| `AgentConfig` + manual tool loop | Same `Config().Invoke`; register an agent handler and `ToolHandlers`; mode comes from the variation |
| `CompletionConfigTemplate`, `AgentConfigTemplate`, `JudgeConfigTemplate` | For inspection use `InspectConfig`; for execution let the handler compose the prompt. Ask before replacing any custom template processing |
| `CreateTracker`, `TrackMetricsOf`, `TrackDurationOf`, standard generation/token/duration/tool tracking | Automatic metrics on `Invoke` / `Stream`; remove wrappers to avoid double-counting |
| `TrackTimeToFirstToken`, custom measurements supplied through `TrackRequest` or `TrackUsage` | No v1.0.0 TTFT event or equivalent API for overriding automatic measurements. Inventory and tell the user about any measurements that would be lost before deleting them. `TrackUsage` itself is a deprecated alias for `TrackTokens`: ordinary provider-reported token counts become automatic, not unsupported |
| `TrackFeedback` | `aiserver.Track(event, user, resp.TrackData, 1)` |
| `JudgeConfig`, `judge.New`, app-supplied judge `Provider`, `TrackJudgeResponse` | Attach judges to the variation; inline by default, or `SkipJudges` + deferred worker |
| `AgentConfigs`, `AgentGraph`, manual `Traverse`, `GraphTracker` | `aiserver.Graph(...).Invoke(...)`, or `ResolveGraph` + native runner |
| Tracker resumption tokens / reconstructed trackers | No tracker replacement. Preserve `TrackData` for explicit feedback; ask how any deferred generation work should be redesigned before deleting it |
| `Enabled()` / default object | Typed invocation errors and `InspectConfig(ctx, key, user)` |

The standard success/error, duration, and token events formerly emitted by `TrackRequest` become automatic too. Its caller-supplied latency/TTFT and token overrides do not: compare those values with the handler's actual measurements and tell the user about any changed metric semantics. Do not describe `TrackUsage` as an arbitrary custom-event API.

Handler packages are in **one module**, not separate modules: `openaimessages`, `openaiagents`, `claudemessages`, `claudeagents`, `bedrockmessages`, `bedrockagents`, `langchainmessages`, `langchainagents`. Constructors are `NewHandler(Options{}) (*aiserver.ProviderHandler, error)`. No Go LiteLLM or Vercel package is implied. LangChain-style Go handlers use this SDK's `llms` interface, not an official LangChain Go SDK. For unsupported providers inspect the installed handler contract before building a custom `aiserver.CreateHandler`.

Confirm the target, package changes, fallback policy, tools, and any provider-specific response dependencies with the user before editing. Inventory broad names such as `Config` by their imported package/receiver, including aliases.

## Execute: packages and lifecycle

```bash
go get github.com/launchdarkly/go-ai-sdk@v1.0.0
```

Import `github.com/launchdarkly/go-ai-sdk/aiserver` and the handler packages you need. After the last legacy call is removed, remove legacy imports and run `go mod tidy`; do not remove `go-server-sdk/v7` if ordinary flag code still imports it. Check Go 1.26+ before changing the module's toolchain. With the default `GOTOOLCHAIN=auto`, `go get` can download a newer toolchain and raise the `go` line in `go.mod` to satisfy the dependency's Go 1.26 requirement; confirm that upgrade with the user first and review the module diff afterward.

The SDK reads `LD_SDK_KEY`; handlers read provider credentials such as `OPENAI_API_KEY`. Initialize at startup to handle failure there rather than repeatedly waiting for lazy initialization during an outage:

```go
if _, err := aiserver.InitClient(ctx, aiserver.InitOptions{}); err != nil {
    return err
}
defer aiserver.Shutdown(ctx)
```

`Shutdown` flushes spans/events and closes the LD client, **including a client passed to `InitWithClient`**. Coordinate ownership with existing flag code. Use a live shutdown context after requests are drained. Pass the request `context.Context` to model calls for cancellation and tracing; targeting uses a separate `ldcontext.Context`.

Content capture is **on by default**, including prompts, output, tool payloads, and judge reasoning. Ask about sensitive data. Before the first handler call, opt out process-wide with `aiserver.Configure(aiserver.SDKOptions{CaptureContent: aiserver.CaptureOff})` and handle its error, or use the handler's `Options{CaptureContent: aiserver.CaptureOff}`. `Configure` cannot change the effective setting after the first call until shutdown.

## Completion: before and after

Legacy (inside a function; `aiClient` is initialized with `ldai.NewClient`):

```go
cfg := aiClient.CompletionConfig("support", user,
    ldai.NewAICompletionConfigDefault().WithEnabled(false), variables)
if !cfg.Enabled() {
    return fallbackAnswer, nil
}
tracker := cfg.CreateTracker()
// App merges cfg.Messages(), chooses cfg.ModelName(), calls the provider,
// and records TrackSuccess/TrackError, TrackDuration, and TrackTokens.
```

Current convenience call (imports `openaimessages` and `ldcontext`):

```go
resp, err := openaimessages.OpenAIMessages(ctx, "support", userInput,
    ldcontext.New("user-123"), &openaimessages.InvokeOptions{Variables: variables})
if err != nil {
    return "", err
}
return resp.Text(), nil
```

`OpenAIMessages` builds a fresh handler on every call and, unless `InvokeOptions.Handler.Client` is supplied, a fresh provider client. For hot paths, shared handlers, or multiple providers, construct handlers once, handle constructor errors, and reuse a registry with `Config`:

```go
h, err := openaimessages.NewHandler(openaimessages.Options{})
if err != nil {
    return err
}
registry := aiserver.NewRegistry(aiserver.RegistryEntries{
    Handlers: []*aiserver.ProviderHandler{h},
})
cfg := aiserver.Config(aiserver.ConfigArgs{Key: "support", Registry: registry})
```

Register every provider/mode the variations can serve; missing matches return `ErrNoHandler`. Provider names match exactly, including case: the OpenAI handler matches `"OpenAI"`, not `"openai"` (which returns `ErrNoHandler` unless a wildcard handler covers it). Go has **no global registry**: pass `*Registry` explicitly. Replace manual message merging and model/parameter plumbing with `Invoke`. Read `resp.Text()` for text or `resp.Response` for structured output, and `resp.Usage`; ask before changing consumers of raw provider response fields. Check each handler's forwarded parameter allowlist; move app-only knobs into `model.custom`, and never blindly spread parameters or tools in a custom handler.

## Fallbacks and inspection

Preserve the old fallback only for the errors the application's policy covers, not provider/tool/judge errors. There is no fallback argument. Match wrapped errors with `errors.Is`, not strings:

```go
// Include this branch only if the agreed policy is fallback on any LD init error.
if _, err := aiserver.InitClient(ctx, aiserver.InitOptions{}); err != nil {
    return fallbackAnswer, nil
}
resp, err := cfg.Invoke(ctx, userInput, user,
    aiserver.WithVariables(variables))
if err != nil {
    if errors.Is(err, aiserver.ErrConfigDisabled) || errors.Is(err, aiserver.ErrConfigNotFound) {
        return fallbackAnswer, nil
    }
    return "", err
}
return resp.Text(), nil
```

Missing `LD_SDK_KEY` and rejected-key/startup initialization failures match neither `ErrConfigDisabled` nor `ErrConfigNotFound`; `InitClient` does not wrap `ErrNotInitialized`. Preserving a legacy fallback-on-outage default therefore needs an explicit catch-all initialization-error policy, as illustrated above, agreed with the user. A failed `InitClient` is not cached, so running that branch per request retries initialization (waiting up to `WaitFor`) on every request during an outage; run it once at startup and keep the result for request handlers to check. Startup code that simply returns the initialization error instead will not preserve that fallback. Do not apply a catch-all to `Invoke` errors: provider/tool/judge errors must not become outage fallbacks. For a health check use `state, err := aiserver.InspectConfig(ctx, key, user)`: disabled means `!state.Enabled` with nil error; initialization/evaluation/parse failures return errors. Unlike the Python/Node inspection helpers it does **not** promise never to fail. An invocation may return a usable `resp.Response` alongside a judge error; preserve the app's intended policy for that partial success.

## Tools, variables, history, streaming

Agent mode uses an agent handler, for example `openaiagents.NewHandler(openaiagents.Options{})`, with errors handled as above. Move tool implementations into the registry's `Tools` or `ConfigArgs.ToolHandlers`:

```go
getPrefs := aiserver.ToolFunc(func(ctx context.Context, args map[string]any) (any, error) {
    return lookupPreferences(ctx, args)
})
tools := map[string]aiserver.ToolHandler{"get-prefs": getPrefs}
cfg := aiserver.Config(aiserver.ConfigArgs{
    Key: "support", Handlers: handlers, ToolHandlers: tools,
})
```

Keys must match the variation's tool names exactly, including case. A registered tool missing from the variation is silently unavailable to the model; registration alone does not expose it. Before deleting the manual loop and tracking, confirm every old tool exists on each variation, and preserve any loop limit or default model the old loop set in the variation or a custom handler. If any of these cannot be preserved, tell the user before proceeding. Do not assume Python/Node Claude host settings or built-ins apply to Go; inspect that handler's documented host-tool security behavior first.

Inventory tools stored only in `model.parameters.tools`: the legacy SDK used that list when root `tools` was absent, but v1.0.0 reads only the root `tools` map. Ask the user to move these definitions to root tools on every affected variation before migrating; do not silently drop them or change stored configs without approval. For OpenAI agents, preserve loop limits with `openaiagents.Options.MaxTurns` (zero defaults to 10), or the variation's `max_turns` model parameter, which takes precedence.

Move variables to `InvokeOptions.Variables` for convenience calls, or `aiserver.WithVariables(variables)` for `Invoke` / `Stream`. Context template injection is `{{ldContext.*}}`, replacing `{{ldctx.*}}`; use `{{name}}` without spaces. Pass history with `aiserver.WithHistory([]aiserver.Message{...})`, not a fourth positional message array. Convenience `InvokeOptions` does not expose history: use `Config` for history.

```go
for ev, err := range cfg.Stream(ctx, userInput, user,
    aiserver.WithVariables(variables), aiserver.WithHistory(history)) {
    if err != nil {
        return err
    }
    switch ev.Type {
    case aiserver.EventChunk:
        fmt.Print(ev.Text)
    case aiserver.EventDone:
        fmt.Println(ev.Response, ev.Usage)
    }
}
```

Drain through `EventDone`: breaking early abandons the run without success/error tracking. Stream events have no `TrackData`; do not invent streamed feedback attribution or assume `SkipJudges` returns deferred stream tasks.

## Feedback and judges

Replace `tracker.TrackFeedback(...)` after a non-streamed invocation with:

```go
event := "$ld:ai:feedback:user:negative"
if thumbsUp {
    event = "$ld:ai:feedback:user:positive"
}
aiserver.Track(event, user, resp.TrackData, 1)
```

`aiserver.Track` returns nothing and silently does nothing without an initialized client (or a defined targeting context). Unlike legacy `TrackFeedback`, which returned an error, it provides no error to check; do not claim feedback delivery succeeded just because this call returned.

Judges attached to the variation run inline by default. Confirm attachment before removing `judge.New`, its app-owned `Provider`, and `TrackJudgeResponse`. To defer, set `ConfigArgs.SkipJudges: true`, persist each `resp.JudgeTasks` item to a durable queue, and let an owned worker run it. Do not launch unowned goroutines with the request context. The worker supplies the handlers needed by the judge and explicitly tracks its evaluation metric:

```go
func runJudgeWorker(ctx context.Context, task aiserver.JudgeTask, handlers []*aiserver.ProviderHandler) error {
    res, err := aiserver.RunJudge(ctx, task, handlers)
    if err != nil {
        return err
    }
    if res != nil && task.EvaluationMetricKey != "" {
        aiserver.Track(task.EvaluationMetricKey, task.UserContext, res.TrackData, res.Score)
    }
    return nil
}
```

`RunJudge` returns `(nil, nil)` for no matching handler or no numeric verdict. It records generation telemetry but **not** the evaluation metric. Handle failed queue writes and worker errors; don't silently lose scores.

## Graphs and verification

Replace legacy `AgentGraph`, manual traversal, and `GraphTracker` with:

```go
out, err := aiserver.Graph("support-graph", aiserver.GraphOptions{Registry: registry}).
    Invoke(ctx, userInput, user, aiserver.WithVariables(variables))
if err != nil {
    return "", err
}
return out.Response, nil
```

The registry needs agent handlers for every node's provider. Match `ErrGraphDisabled` for execution fallback. For native runners, `ResolveGraph(ctx, key, user, opts)` returns topology; check both its error and `def.Enabled` (disabled topology can have nil error). Use `openaiagents.ToOpenAIAgents`, `claudeagents.ToClaudeAgents`, or `langchainagents.ToLangGraph` only after checking the installed signatures. Bare topology traversal emits no execution telemetry; prefer `Graph().Invoke` or a native runner rather than retaining an untracked walk.

For `ToOpenAIAgents` and `ToLangGraph`, explicitly set the respective `NativeGraphOptions.Context` to the targeting `ldcontext.Context`; leaving it undefined silently disables the native adapter's `$ld:ai:*` execution events even though spans still exist. `ToClaudeAgents` differs: its `AdapterOptions` has no `Context` field and it uses the context stored by `ResolveGraph`, so pass a defined targeting context when resolving the graph.

Graph event keys are mostly unchanged: `$ld:ai:graph:path` became `$ld:ai:graph:node`, and `$ld:ai:graph:redirect` is gone. Tell the user to update metrics built on those two keys.

Re-run the inventory by import/receiver (not names alone), then the app's existing build, lint, and tests. Test enabled and disabled configs, missing configs, empty input/history/tools, provider and tool errors, cancellation, stream completion/abandonment, and judge worker empty/error results where used. Verify fallback behavior under an unavailable LD connection without masking unrelated errors. Update mocks at the handler/config boundary, and confirm generations, tokens, duration, feedback, and deferred judge metrics in Monitoring when credentials and a safe test environment are available. Report anything not verified.
