---
name: observability-plugin-setup
description: "Set up LaunchDarkly observability for an app that already uses a LaunchDarkly SDK by adding the observability plugin to its existing client and opening a pull request. Use when an observability tool reports the project has never received data (observability_set_up or observabilitySetUp is false), when observability queries come back empty because nothing is instrumented, or when the user asks to add observability, error monitoring, logs, tracing, or session replay to a LaunchDarkly-enabled app."
license: Apache-2.0
compatibility: Needs a codebase with an existing LaunchDarkly SDK client. Uses the remotely hosted LaunchDarkly MCP server to confirm data arrives.
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# LaunchDarkly Observability Plugin Setup

You're using a skill that will guide you through turning on LaunchDarkly observability for an application that already evaluates flags with a LaunchDarkly SDK. Observability (errors, logs, traces, and session replay) starts when the LaunchDarkly observability plugin is added to that SDK client. Your job is to confirm observability is not set up, get the user's agreement, add the plugin to the client the app already initializes, open a pull request, and confirm data arrives once the change runs.

## Prerequisites

- A codebase you can edit that already initializes a LaunchDarkly SDK client. If there is none, observability needs the SDK first: say so and stop (see Edge Cases).
- The remotely hosted LaunchDarkly MCP server, for the verify step.

**MCP tools used:**
- `find-o11y-project` — confirm nothing has been received yet, and later that a service reports data
- `get-keys` — confirm the service name once data flows (`key=service_name`)

## Core Principles

1. **Ask before changing anything.** The user usually came for something else (often flag work). Explain the change in a few lines and edit only after they agree. If they decline, drop it for the rest of the session.
2. **One plugin on the client that already exists.** Add the plugin to the LaunchDarkly client's `plugins` option in the init code the app already has, or use the stack's equivalent registration (Flutter's `LDObserve.init`, .NET MAUI's `ObservabilityPlugin`). No second client, no second key, no new environment variable.
3. **Smallest diff.** One dependency and one plugin registration per client. No custom spans, log forwarding, network body recording, sampling, or service names unless the user asks.
4. **Strict privacy for session replay.** Unless the user names a level, use the strictest replay setting: `privacySetting: 'strict'` in the browser, every mask option turned on for mobile (see [Plugin wiring](references/plugin-wiring.md)).
5. **A pull request, not a push.** Put the change on a new branch and open a pull request for review. Never commit to the default branch.

## Workflow

### Step 1: Confirm observability is not set up

Use the signal you already have:

- An observability tool returned `observability_set_up: false`, or `find-o11y-project` returned `observabilitySetUp: false`: the project (or every project) has never received sessions, errors, logs, traces, or metrics. Continue.
- Observability data exists for the project: this skill does not apply. Answer the user's question with the observability tools (the `observability/investigate` skill) instead.
- You have neither signal: call `find-o11y-project` without `serviceName`. An empty project list with `observabilitySetUp: false` confirms it.

Do not keep retrying observability queries against a project that has never received data. They return nothing.

### Step 2: Explain and ask

Tell the user what you found and what the change is, in their terms. For example:

```
LaunchDarkly hasn't received any observability data for this project, so there's nothing to search yet.
Observability turns on by adding the LaunchDarkly observability plugin to the LaunchDarkly client this app
already sets up (src/lib/launchdarkly.ts). It's one dependency and one line in that client's options, using
the same key, and it adds error monitoring, logs, and traces (plus session replay for browser and mobile apps,
with the strictest privacy setting). Want me to make that change and open a pull request?
```

- If the codebase has more than one LaunchDarkly client (for example a web app and an API), list them and ask which to set up. Default to the one the current task is about.
- Proceed only on a clear yes.

### Step 3: Find the client and the stack

1. Find the LaunchDarkly SDK dependency in the manifest (`package.json`, `requirements.txt` / `pyproject.toml`, `go.mod`, `Gemfile`, `*.csproj`, `Podfile` / `Package.swift`, `build.gradle(.kts)` / `pom.xml`, `pubspec.yaml`).
2. Find the client initialization: for example `asyncWithLDProvider`, `withLDProvider`, `createLDReactProvider`, `createClient`, `initialize(`, `init(` from `@launchdarkly/node-server-sdk`, `ldclient.set_config(Config(`, `ld.MakeClient` / `ld.MakeCustomClient`, `LaunchDarkly::LDClient.new`, `new LdClient(` / `LdClient.Init(` / `Configuration.Builder(`, `new LDClient(` / `new LDConfig.Builder()`, `LDClient(LDConfig(`, `LDClient.start(`, `LDClient.init(`, `new ReactNativeLDClient(`.
3. If the app wraps LaunchDarkly behind its own module, edit the init inside that module.
4. Match the stack to a row in [Plugin wiring](references/plugin-wiring.md). If the stack has no plugin, stop (see Edge Cases).
5. Check the installed SDK version against the minimum in that table.

### Step 4: Add the plugin

Follow [Plugin wiring](references/plugin-wiring.md) for the package and where `plugins` goes:

1. Install the package with the project's package manager (from the lockfile). Do not pin a version except where the ecosystem requires one (Gradle, CocoaPods).
2. Construct the plugin and add it to the existing client's `plugins` option (Flutter instead registers it on the existing client with `LDObserve.init(client, ...)`). Keep everything else in the init unchanged.
3. Reuse the client's credential. Where a plugin constructor takes the key (Android), pass the same variable the client reads.
4. Add session replay only if the user wants it, with the strictest privacy setting unless they named one. How depends on the stack:
   - Browser, React Native, iOS, Android: add the replay plugin after the observability plugin in `plugins`.
   - Flutter: pass `replay: const SessionReplayOptions(...)` to the existing `LDObserve.init` call and wrap the app in `SessionReplayCapture`. Replay is not a second plugin, so do not add one.
   - .NET MAUI: pass `SessionReplayOptions` as the second `ObservabilityPlugin` constructor argument. Replay is not a second plugin, so do not add one.
5. Build or type-check the project, and run its existing tests if they are quick. Fix what you broke; do not change unrelated code.

If the installed SDK is below the plugin's minimum: a bump within the same major version is fine. A major-version upgrade or a different package needs the user's approval first.

### Step 5: Open the pull request

1. Create a branch, for example `launchdarkly/add-observability-plugin`.
2. Commit only the dependency, lockfile, and init change.
3. Open a pull request following the repository's conventions. Say:
   - **What:** adds the LaunchDarkly observability plugin (and session replay, if added) to the existing LaunchDarkly client in `<file>`, reusing its key.
   - **Why:** turns on error monitoring, logs, and traces in LaunchDarkly, tied to the flags this app already evaluates.
   - **Privacy:** the session replay setting used, or that replay was not added.
   - **How to verify:** run or deploy the app, use it, and check that the service appears under Observability in LaunchDarkly.
4. If you cannot open pull requests in this environment, leave the change on the branch and tell the user how to open it.

### Step 6: Verify

Data arrives only after the changed code runs (locally against a LaunchDarkly environment, or after deploy).

1. Ask the user to run the app and exercise it, or to tell you once it is deployed.
2. Call `find-o11y-project` with the app's service name, or without `serviceName`. A project listed with services means data is flowing. Confirm the name with `get-keys` (`productType` logs or traces, `key=service_name`).
3. Report:

```
✓ Observability is on: checkout-web is sending errors, logs, and traces to project storefront.
```

If nothing appears within a few minutes of the app running, check: the init change is the code path that actually runs, the client initializes successfully (same key as before), the app reached the network, and the environment is the one you are querying. For accounts on the EU instance, the plugin needs the EU endpoints set; see the [observability SDK docs](https://launchdarkly.com/docs/sdk/observability).

## Edge Cases

| Situation | Action |
|-----------|--------|
| No LaunchDarkly SDK in the codebase | Say observability needs the LaunchDarkly SDK first and stop. Do not install the SDK as part of this skill. |
| Stack has no observability plugin (for example PHP, Rust, edge SDKs) | Say in one line the plugin is not available for this stack yet, with the docs link, and stop. Do not substitute OpenTelemetry. |
| SDK too old for plugins, fix is a major upgrade | Ask first, naming the version problem in one line. Keep the existing SDK if the user declines. |
| Several LaunchDarkly clients (web, API, mobile) | List them, set up only the ones the user picks, one pull request. |
| Observability data already exists | Not this skill. Use the observability tools to answer the question. |
| User declines | Stop, and do not offer again in this session. |
| No permission to open pull requests | Leave the commit on a branch and give the user the branch name. |

## What NOT to Do

- Don't edit code or open a pull request before the user agrees.
- Don't create a second LaunchDarkly client, key, or environment variable.
- Don't add OpenTelemetry or another vendor's package instead of the plugin.
- Don't turn on network body recording, custom spans, log forwarding, or sampling unless asked.
- Don't commit to the default branch.
- Don't report observability as working until `find-o11y-project` or `get-keys` shows the service.

## References

- [Plugin wiring](references/plugin-wiring.md): package, install command, and where `plugins` goes for each supported stack, minimum SDK versions, and stacks without a plugin
