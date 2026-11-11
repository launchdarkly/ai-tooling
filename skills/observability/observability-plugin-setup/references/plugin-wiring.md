---
title: Observability plugin wiring
description: "Package, install command, and where the plugins option goes for each stack that has a LaunchDarkly observability plugin, minimum SDK versions, and stacks without a plugin."
---

# Observability plugin wiring

Add the plugin to the `plugins` option of the LaunchDarkly client the app already initializes. Keep the rest of the init unchanged and reuse its credential. Most rows mirror `skills/onboarding/references/sdk/observability-plugin.md`; keep the shared rows in sync.

Read the package README before writing init code. The per-package READMEs in [launchdarkly/observability-sdk](https://github.com/launchdarkly/observability-sdk) (under `sdk/@launchdarkly/<package>/`) and the [observability SDK docs](https://launchdarkly.com/docs/sdk/observability) are authoritative for plugin options. README examples can lag the SDKs, so take the client initializer from the app's existing code, not from a plugin README.

## Browser

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

Add session replay only if the user wants it. It goes after `Observability`, with `privacySetting: 'strict'` unless the user named another level.

| SDK in the project | Where `plugins` goes |
|---|---|
| React, `launchdarkly-react-client-sdk` (v3) | `asyncWithLDProvider({ clientSideID, context, options: { plugins } })`, same for `withLDProvider` |
| React, `@launchdarkly/react-sdk` (v4) | `createLDReactProvider(clientSideID, context, { ldOptions: { plugins } })`. Under `ldOptions`, not at the top level of the third argument. |
| JavaScript, `@launchdarkly/js-client-sdk` (v4) | `createClient(clientSideID, context, { plugins })` |
| Vue, `launchdarkly-vue-client-sdk` | `app.use(LDPlugin, { clientSideID, context, options: { plugins } })` |
| Angular, Svelte, Preact, other browser frameworks | Same as JavaScript (`@launchdarkly/js-client-sdk`) |

An older browser SDK that does not accept `plugins` (for example `launchdarkly-js-client-sdk` 2.x, where TypeScript rejects the option) needs a move to `@launchdarkly/js-client-sdk`. That is a different package, so ask the user first.

## Next.js

Wire each client the app has:

- **Client components:** the React client SDK, with the browser packages above.
- **Server (Route Handlers, Server Components):** the Node server SDK, with `@launchdarkly/observability-node` (next section).

`@launchdarkly/observability-next` is a standalone package that initializes from a key without a LaunchDarkly client. It does not attach to a client's `plugins` option, so do not use it here.

## Server and mobile

| Stack | Package | Install | Wiring | Minimum SDK |
|---|---|---|---|---|
| Node.js (server) | `@launchdarkly/observability-node` | `npm install @launchdarkly/observability-node` | `import { Observability } from '@launchdarkly/observability-node'`, then `init(sdkKey, { plugins: [new Observability()] })` | Current `@launchdarkly/node-server-sdk` |
| React Native | `@launchdarkly/observability-react-native` | `npm install @launchdarkly/observability-react-native` | `import { Observability } from '@launchdarkly/observability-react-native'`, then `new ReactNativeLDClient(mobileKey, AutoEnvAttributes.Enabled, { plugins: [new Observability()] })` | `@launchdarkly/react-native-client-sdk` v10 |
| React Native session replay | `@launchdarkly/session-replay-react-native` | `npm install @launchdarkly/session-replay-react-native` | `import { createSessionReplayPlugin } from '@launchdarkly/session-replay-react-native'`, then add `createSessionReplayPlugin()` after `Observability` in `plugins`. With no privacy level named, pass `{ maskTextInputs: true, maskLabels: true, maskImages: true, maskWebViews: true }`. Native module: run `npx pod-install` on bare React Native. | React Native 0.75+ |
| Python | `launchdarkly-observability` | `pip install launchdarkly-observability` | `from ldobserve import ObservabilityPlugin`, then `Config(sdk_key, plugins=[ObservabilityPlugin()])` | `launchdarkly-server-sdk` 9.12+ |
| Ruby | `launchdarkly-observability` | add `gem 'launchdarkly-observability'` to the Gemfile, then `bundle install` | `require 'launchdarkly_observability'`, then `LaunchDarkly::Config.new(plugins: [LaunchDarklyObservability::Plugin.new])` | `launchdarkly-server-sdk` 8.11+ |
| Go | `github.com/launchdarkly/observability-sdk/go` | `go get github.com/launchdarkly/observability-sdk/go` | `ld.MakeCustomClient(sdkKey, ld.Config{Plugins: []ldplugins.Plugin{ldobserve.NewObservabilityPlugin()}}, timeout)` with `ldobserve` as the import alias | `go-server-sdk/v7` with `ldplugins` |
| .NET (server) | `LaunchDarkly.Observability` | `dotnet add package LaunchDarkly.Observability` | `Configuration.Builder(sdkKey).Plugins(new PluginConfigurationBuilder().Add(ObservabilityPlugin.Builder(builder.Services).Build()))`. Build the `LdClient` before `builder.Build()`. | `LaunchDarkly.ServerSdk` 8.10+ |
| iOS | `swift-launchdarkly-observability` (SPM), or pods `LaunchDarklyObservability` / `LaunchDarklySessionReplay` | SPM: add `https://github.com/launchdarkly/swift-launchdarkly-observability` and the `LaunchDarklyObservability` product (plus `LaunchDarklySessionReplay` for replay) | `import LaunchDarklyObservability`, then `config.plugins = [Observability(options: .init())]`; for replay also `import LaunchDarklySessionReplay` and append `SessionReplay(options: .init(privacy: .init(maskTextInputs: true, maskWebViews: true, maskLabels: true, maskImages: true)))` | iOS SDK 9.14+ |
| Android | `com.launchdarkly:launchdarkly-observability-android` | add `implementation("com.launchdarkly:launchdarkly-observability-android:<latest>")` next to the client SDK | `.plugins(Components.plugins().setPlugins(listOf(Observability(application, mobileKey))))` on `LDConfig.Builder`; for replay append `SessionReplay(ReplayOptions(privacyProfile = PrivacyProfile(maskTextInputs = true, maskText = true, maskImageViews = true, maskWebViews = true)))` (`SessionReplay` from `com.launchdarkly.observability.replay.plugin`, `ReplayOptions` and `PrivacyProfile` from `com.launchdarkly.observability.replay`) | Android client SDK 5.9+ |
| Java (server) | `com.launchdarkly:launchdarkly-java-server-sdk-observability` | add `implementation("com.launchdarkly:launchdarkly-java-server-sdk-observability:<latest>")` (or the Maven `<dependency>`) next to the server SDK | `import com.launchdarkly.observability.ObservabilityPlugin` and `com.launchdarkly.observability.ObservabilityOptions`, then `.plugins(Components.plugins().setPlugins(List.of(new ObservabilityPlugin(new ObservabilityOptions.Builder().build()))))` on `LDConfig.Builder` | `launchdarkly-java-server-sdk` 7.10.1+, Java 11+, OpenTelemetry Java 1.38+ at runtime |
| Flutter | `launchdarkly_flutter_observability` | `flutter pub add launchdarkly_flutter_observability` | Not a `plugins` option: after the app constructs its `LDClient`, call `LDObserve.init(client, observability: const ObservabilityOptions())`, which registers the plugin on that client. For replay (iOS and Android only) also pass `replay: const SessionReplayOptions(privacy: PrivacyOptions(maskTextInputs: true, maskWebViews: true, maskLabels: true, maskImages: true))` and wrap the app in `SessionReplayCapture` (`runApp(const SessionReplayCapture(child: MyApp()))`). iOS: deployment target 15.0, then `pod install` | `launchdarkly_flutter_client_sdk` 4.18+, Flutter 3.27+ |
| .NET MAUI | `LaunchDarkly.SessionReplay` (NuGet; namespaces `LaunchDarkly.Observability` and `LaunchDarkly.SessionReplay`) | `dotnet add package LaunchDarkly.SessionReplay` | `Configuration.Builder(mobileKey, ConfigurationBuilder.AutoEnvAttributes.Enabled).Plugins(new PluginConfigurationBuilder().Add(new ObservabilityPlugin(new ObservabilityOptions())))`; for replay pass `new SessionReplayOptions(privacy: new SessionReplayOptions.PrivacyOptions(maskTextInputs: true, maskWebViews: true, maskLabels: true, maskImages: true))` as the second `ObservabilityPlugin` argument | `LaunchDarkly.ClientSdk` 5.8+, .NET 9 or 10 with the MAUI workload |

Confirm the iOS, Android, Java, Flutter, and .NET constructor options against the package README before writing them. Most of these packages are pre-1.0 and their option shapes change between releases.

Mobile session replay has no single `strict` preset. The package defaults mask only text inputs, so with no privacy level named, turn on every mask option as shown above: text inputs, text labels, images, and web views. If the user names a level, set exactly what they asked for.

## Stacks without a plugin

PHP, Rust, Erlang/Elixir, Haskell, Lua, C/C++, Apex, Electron, Node.js (client), Roku, the .NET client SDK outside MAUI, and the edge SDKs have no observability plugin here. Check the [observability SDK docs](https://launchdarkly.com/docs/sdk/observability) once. If nothing is listed for the stack, tell the user in one line that the plugin is not available for it yet. Do not substitute OpenTelemetry setup or a different package.
