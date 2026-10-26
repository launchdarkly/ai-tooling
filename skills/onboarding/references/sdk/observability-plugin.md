---
title: Observability plugin
description: "Add LaunchDarkly observability and session replay to an existing LaunchDarkly client through its plugins option. Package and wiring per stack, scope rules, and what to do when a stack has no plugin."
---

# Observability plugin

Load this file when the user asks for any of: observability, session replay, error monitoring, logs, tracing, or "the observability plugin". A typical request, appended to the onboarding prompt:

> Also add the LaunchDarkly observability plugin for this stack to that client's `plugins` option, reusing its key. For a browser app, that's @launchdarkly/observability and @launchdarkly/session-replay with privacySetting "strict".

Resolve this once, from the user's original message, at kickoff. Treat it as part of the SDK install: the plugin is added in the same pass as the SDK, not offered as a later step.

## Rules

1. **It is a plugin on the client you already set up, not a second client.** Construct the plugin and add it as an element of the LaunchDarkly client's `plugins` option, in the same init code the SDK install wrote (or the existing init, if LaunchDarkly was already integrated).
2. **Reuse the client's credential.** The plugin uses the same client-side ID, SDK key, or mobile key as the client. Do not add a second env var, a second key, or a second credential prompt. Where a plugin constructor takes the key as an argument (Android), pass the same variable the client reads.
3. **The feature-management SDK comes first.** If the project has no LaunchDarkly client yet, run the normal detect, plan, and apply flow first, then add the plugin to the init you just wrote.
4. **Scope is the dependency and the `plugins` entry.** Do not add custom spans, log forwarding, network recording, error boundaries, sampling, service names, or privacy options the user did not ask for. The one exception is a privacy level the user named (for example `privacySetting: 'strict'`): set exactly that.
5. **Observability packages are in-scope LaunchDarkly installs** when the user asked for them. They do not need the extra approval that non-LaunchDarkly dependency changes need. If the installed SDK version is below the plugin's minimum (see the table), bumping within the same major version is fine; a major-version jump needs approval per [Apply code changes](../../sdk-install/apply/SKILL.md#permission-before-changing-other-dependencies).
6. **Do not pin plugin versions.** Let the package manager resolve the current release, except where the ecosystem requires a version (Gradle, CocoaPods); use the latest published release there.
7. **Session replay goes after observability** in the `plugins` list on every platform that has both.
8. **Read the package README before writing init code.** The per-package READMEs in [launchdarkly/observability-sdk](https://github.com/launchdarkly/observability-sdk) (under `sdk/@launchdarkly/<package>/`) and the [observability docs](https://launchdarkly.com/docs/home/observability) are authoritative. Take the plugin wiring from them and the client initializer from the recipe for the project's actual SDK. README examples can lag the SDKs, so do not copy a client initializer from a plugin README.

## Packages and wiring

Match the row to the SDK the project actually uses (from [SDK recipes](recipes.md)). The **Wiring** column shows only where the plugins go; keep the rest of the existing init unchanged.

### Browser

Browser apps get two packages: `@launchdarkly/observability` (errors, logs, traces) and `@launchdarkly/session-replay` (session replay). Both are default exports. There is no separate React package.

```shell
npm install @launchdarkly/observability @launchdarkly/session-replay
```

```ts
import Observability from '@launchdarkly/observability';
import SessionReplay from '@launchdarkly/session-replay';

const plugins = [
  new Observability(),
  new SessionReplay({ privacySetting: 'strict' }),
];
```

Add only the plugin(s) the user asked for. "Observability" alone means `Observability`; "session replay" means both, since replay builds on observability.

| SDK in the project | Where `plugins` goes |
|---|---|
| React, `launchdarkly-react-client-sdk` (v3) | `asyncWithLDProvider({ clientSideID, context, options: { plugins } })`, same for `withLDProvider` |
| React, `@launchdarkly/react-sdk` (v4) | `createLDReactProvider(clientSideID, context, { ldOptions: { plugins } })`. Under `ldOptions`, not at the top level of the third argument. |
| JavaScript, `@launchdarkly/js-client-sdk` (v4) | `createClient(clientSideID, context, { plugins })` |
| Vue, `launchdarkly-vue-client-sdk` | `app.use(LDPlugin, { clientSideID, context, options: { plugins } })` |
| Angular, Svelte, Preact, other browser frameworks | Same as JavaScript (`@launchdarkly/js-client-sdk`) |

If the project is on an older browser SDK that does not accept `plugins` (TypeScript rejects the option, or the SDK's changelog does not list plugin support), tell the user in one line and ask before upgrading.

### Next.js

Wire each client the onboarding installed:

- **Client components:** the React client SDK, with the browser packages above.
- **Server (Route Handlers, Server Components):** the Node server SDK, with `@launchdarkly/observability-node` (next section).

`@launchdarkly/observability-next` is a separate standalone package that initializes from a key without a LaunchDarkly client. It does not attach to a client's `plugins` option, so do not use it to satisfy a request to add the plugin to the client.

### Server and mobile

| Stack | Package | Install | Wiring | Minimum SDK |
|---|---|---|---|---|
| Node.js (server) | `@launchdarkly/observability-node` | `npm install @launchdarkly/observability-node` | `import { Observability } from '@launchdarkly/observability-node'`, then `init(sdkKey, { plugins: [new Observability()] })` | Current `@launchdarkly/node-server-sdk` |
| React Native | `@launchdarkly/observability-react-native` | `npm install @launchdarkly/observability-react-native` | `import { Observability } from '@launchdarkly/observability-react-native'`, then `new ReactNativeLDClient(mobileKey, AutoEnvAttributes.Enabled, { plugins: [new Observability()] })` | `@launchdarkly/react-native-client-sdk` v10 |
| React Native session replay | `@launchdarkly/session-replay-react-native` | `npm install @launchdarkly/session-replay-react-native` | `import { createSessionReplayPlugin } from '@launchdarkly/session-replay-react-native'`, then add `createSessionReplayPlugin()` after `Observability` in `plugins`. For "strict" privacy, pass `{ maskTextInputs: true, maskLabels: true, maskImages: true, maskWebViews: true }`. Native module: run `npx pod-install` on bare React Native. | React Native 0.75+ |
| Python | `launchdarkly-observability` | `pip install launchdarkly-observability` | `from ldobserve import ObservabilityPlugin`, then `Config(sdk_key, plugins=[ObservabilityPlugin()])` | `launchdarkly-server-sdk` 9.12+ |
| Ruby | `launchdarkly-observability` | add `gem 'launchdarkly-observability'` to the Gemfile, then `bundle install` | `require 'launchdarkly_observability'`, then `LaunchDarkly::Config.new(plugins: [LaunchDarklyObservability::Plugin.new])` | `launchdarkly-server-sdk` 8.11+ |
| Go | `github.com/launchdarkly/observability-sdk/go` | `go get github.com/launchdarkly/observability-sdk/go` | `ld.MakeCustomClient(sdkKey, ld.Config{Plugins: []ldplugins.Plugin{ldobserve.NewObservabilityPlugin()}}, timeout)` with `ldobserve` as the import alias | `go-server-sdk/v7` with `ldplugins` |
| .NET (server) | `LaunchDarkly.Observability` | `dotnet add package LaunchDarkly.Observability` | `Configuration.Builder(sdkKey).Plugins(new PluginConfigurationBuilder().Add(ObservabilityPlugin.Builder(builder.Services).Build()))`. Build the `LdClient` before `builder.Build()`. | `LaunchDarkly.ServerSdk` 8.10+ |
| iOS | `swift-launchdarkly-observability` (SPM), or pods `LaunchDarklyObservability` / `LaunchDarklySessionReplay` | SPM: add `https://github.com/launchdarkly/swift-launchdarkly-observability` and the `LaunchDarklyObservability` product (plus `LaunchDarklySessionReplay` for replay) | `import LaunchDarklyObservability`, then `config.plugins = [Observability(options: .init())]`; for replay also `import LaunchDarklySessionReplay` and append `SessionReplay(options: .init())` | iOS SDK 9.14+ |
| Android | `com.launchdarkly:launchdarkly-observability-android` | add `implementation("com.launchdarkly:launchdarkly-observability-android:<latest>")` next to the client SDK | `.plugins(Components.plugins().setPlugins(listOf(Observability(application, mobileKey))))` on `LDConfig.Builder`; for replay append `SessionReplay()` (`com.launchdarkly.observability.replay.plugin.SessionReplay`) | Android client SDK 5.9+ |

Confirm the iOS and .NET constructor options against the package README before writing them. Both packages are pre-1.0 and their option shapes change between releases.

### Stacks without a plugin

Java, PHP, Rust, Erlang/Elixir, Haskell, Lua, C/C++, Apex, Electron, Node.js (client), Roku, .NET (client), Flutter, and the edge SDKs have no observability plugin covered here. Check the [observability docs](https://launchdarkly.com/docs/home/observability) once. If nothing is listed for the stack, tell the user in one line that the observability plugin is not available for it yet, then continue onboarding with feature flags. Do not substitute OpenTelemetry setup or a different package.

## Verify

The plugin is done when:

- The package(s) appear in the dependency manifest and lockfile.
- The `plugins` entry is in the same init call the client uses, with no new credential.
- The project builds (same compile check as [Apply code changes](../../sdk-install/apply/SKILL.md#step-4-verify-the-code-compiles)).

Mention it in the completion summary in one line (for example "Observability and session replay are on, with strict privacy."). Do not offer observability again in the wrap-up choice.
