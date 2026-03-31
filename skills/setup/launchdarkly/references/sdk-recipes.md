---
title: SDK Recipes
description: Detection patterns, install hints, official doc links, and a per-SDK detail file under sdk-snippets/ for every LaunchDarkly SDK in the index
---

# SDK Recipes

Use this reference to match a detected tech stack to the correct LaunchDarkly SDK.

**Field | Value** tables in this file are the **index layer**: package name, what to look for in the repo (detect files/patterns), a one-line install hint, and the official **Docs** link. Use them first to choose the right SDK and command—**before** opening a detail file.

Each recipe links to an **SDK detail** file under [`sdk-snippets/`](sdk-snippets/). Open that file for curated links to official docs, samples, and package registries. Ten of those files also include a **copy-paste onboarding sample**; the rest are pointer-only—follow LaunchDarkly's docs for install and initialization. Never commit real keys. Treat each **Docs** link in the table as canonical for API details and migrations.

> **Source of truth**: Official LaunchDarkly SDK documentation is authoritative. Prefer each recipe's **Docs** link over summaries here.

## Top 10 SDKs (start here)

These are the most common stacks—check here first before scanning less common SDKs below.

### React (Web)

| Field | Value |
|-------|-------|
| Package | `launchdarkly-react-client-sdk` |
| Detect files | `package.json` |
| Detect patterns | `react`, `react-dom`, `"react":` |
| Install | `npm install launchdarkly-react-client-sdk --save` |
| Docs | [React SDK reference](https://launchdarkly.com/docs/sdk/client-side/react) · [React Web SDK reference](https://launchdarkly.com/docs/sdk/client-side/react/react-web) |

**SDK detail:** [`sdk-snippets/react-web-sdk.md`](sdk-snippets/react-web-sdk.md) (includes onboarding sample)

### JavaScript (Browser)

| Field | Value |
|-------|-------|
| Package | `launchdarkly-js-client-sdk` |
| Detect files | `package.json`, `index.html` |
| Detect patterns | `webpack`, `vite`, `parcel`, `rollup`; use when not using React / Vue wrappers |
| Install | `npm install launchdarkly-js-client-sdk --save` |
| Docs | [JavaScript SDK reference](https://launchdarkly.com/docs/sdk/client-side/javascript) |

**SDK detail:** [`sdk-snippets/javascript-browser-sdk.md`](sdk-snippets/javascript-browser-sdk.md) (includes onboarding sample)

### Node.js (Server)

| Field | Value |
|-------|-------|
| Package | `@launchdarkly/node-server-sdk` |
| Detect files | `package.json` |
| Detect patterns | `express`, `fastify`, `koa`, `hapi`, `nestjs`, `next` (API routes), `"type": "module"` |
| Install | `npm install @launchdarkly/node-server-sdk --save` |
| Docs | [Node.js SDK reference (server-side)](https://launchdarkly.com/docs/sdk/server-side/node-js) |

**SDK detail:** [`sdk-snippets/node-server-sdk.md`](sdk-snippets/node-server-sdk.md) (includes onboarding sample)

### Python (Server)

| Field | Value |
|-------|-------|
| Package | `launchdarkly-server-sdk` |
| Detect files | `requirements.txt`, `pyproject.toml`, `setup.py`, `Pipfile` |
| Detect patterns | `flask`, `django`, `fastapi`, `starlette` |
| Install | `pip install launchdarkly-server-sdk` |
| Docs | [Python SDK reference](https://launchdarkly.com/docs/sdk/server-side/python) |

**SDK detail:** [`sdk-snippets/python-server-sdk.md`](sdk-snippets/python-server-sdk.md) (includes onboarding sample)

### React Native

| Field | Value |
|-------|-------|
| Package | `@launchdarkly/react-native-client-sdk` |
| Detect files | `package.json` |
| Detect patterns | `react-native` |
| Install | `npm install @launchdarkly/react-native-client-sdk --save` |
| Docs | [React Native SDK reference](https://launchdarkly.com/docs/sdk/client-side/react/react-native) |

**SDK detail:** [`sdk-snippets/react-native-sdk.md`](sdk-snippets/react-native-sdk.md) (includes onboarding sample)

### .NET (Server)

| Field | Value |
|-------|-------|
| Package | `LaunchDarkly.ServerSdk` |
| Detect files | `*.csproj`, `*.sln`, `*.fsproj` |
| Detect patterns | `Microsoft.AspNetCore`, `Microsoft.NET` |
| Install | `dotnet add package LaunchDarkly.ServerSdk` |
| Docs | [.NET SDK reference (server-side)](https://launchdarkly.com/docs/sdk/server-side/dotnet) |

**SDK detail:** [`sdk-snippets/dotnet-server-sdk.md`](sdk-snippets/dotnet-server-sdk.md) (includes onboarding sample)

### Java (Server)

| Field | Value |
|-------|-------|
| Package | `com.launchdarkly:launchdarkly-java-server-sdk` |
| Detect files | `pom.xml`, `build.gradle`, `build.gradle.kts` |
| Detect patterns | `spring`, `quarkus`, `micronaut`, `dropwizard` |
| Install | Add coordinates to Maven or Gradle |
| Docs | [Java SDK reference](https://launchdarkly.com/docs/sdk/server-side/java) |

**SDK detail:** [`sdk-snippets/java-server-sdk.md`](sdk-snippets/java-server-sdk.md) (includes onboarding sample)

### Go (Server)

| Field | Value |
|-------|-------|
| Package | `github.com/launchdarkly/go-server-sdk/v7` |
| Detect files | `go.mod`, `go.sum` |
| Detect patterns | `net/http`, `gin`, `echo`, `fiber`, `chi` |
| Install | `go get github.com/launchdarkly/go-server-sdk/v7` |
| Docs | [Go SDK reference](https://launchdarkly.com/docs/sdk/server-side/go) |

**SDK detail:** [`sdk-snippets/go-server-sdk.md`](sdk-snippets/go-server-sdk.md) (includes onboarding sample)

### Swift / iOS

| Field | Value |
|-------|-------|
| Package | `LaunchDarkly` (Swift Package Manager or CocoaPods) |
| Detect files | `Package.swift`, `Podfile`, `*.xcodeproj` |
| Detect patterns | `UIKit`, `SwiftUI`, `ios` |
| Install | Add package per docs |
| Docs | [iOS SDK reference](https://launchdarkly.com/docs/sdk/client-side/ios) |

**SDK detail:** [`sdk-snippets/ios-client-sdk.md`](sdk-snippets/ios-client-sdk.md) (includes onboarding sample)

### Android

| Field | Value |
|-------|-------|
| Package | `com.launchdarkly:launchdarkly-android-client-sdk` |
| Detect files | `build.gradle`, `build.gradle.kts`, `AndroidManifest.xml` |
| Detect patterns | `android`, `com.android`, `androidx` |
| Install | Add Maven dependency per docs |
| Docs | [Android SDK reference](https://launchdarkly.com/docs/sdk/client-side/android) |

**SDK detail:** [`sdk-snippets/android-client-sdk.md`](sdk-snippets/android-client-sdk.md) (includes onboarding sample)

---

## Server-side SDKs (other)

Server-side SDKs use an **SDK Key** and are intended for backends where the key stays secret.

The five most-used server runtimes (Node.js, Python, .NET, Java, Go) are in **[Top 10 SDKs (start here)](#top-10-sdks-start-here)** above.

### Apex (Salesforce)

| Field | Value |
|-------|-------|
| Package | Deploy from [apex-server-sdk](https://github.com/launchdarkly/apex-server-sdk) (no NuGet/Maven module) |
| Detect files | `sfdx-project.json`, `force-app`, `*.cls` |
| Detect patterns | `salesforce`, `Salesforce`, `Apex` |
| Install | Follow the docs (SFDX deploy and LaunchDarkly Salesforce bridge) |
| Docs | [Apex SDK reference](https://launchdarkly.com/docs/sdk/server-side/apex) |

**SDK detail:** [`sdk-snippets/apex-server-sdk.md`](sdk-snippets/apex-server-sdk.md)

### C++ (Server)

| Field | Value |
|-------|-------|
| Package | `launchdarkly-cpp-server` (via CMake `FetchContent`, vcpkg, or vendor) |
| Detect files | `CMakeLists.txt`, `Makefile`, `*.cpp`, `*.h` |
| Detect patterns | `cmake`, server-side C++ services |
| Install | See docs (CMake / vcpkg) |
| Docs | [C++ SDK reference (server-side)](https://launchdarkly.com/docs/sdk/server-side/c-c--) |

**SDK detail:** [`sdk-snippets/cpp-server-sdk.md`](sdk-snippets/cpp-server-sdk.md)

### Erlang / Elixir

| Field | Value |
|-------|-------|
| Package | Erlang: [launchdarkly_server_sdk](https://hex.pm/packages/launchdarkly_server_sdk) (Hex). Elixir: add the same dependency in `mix.exs` |
| Detect files | `rebar.config`, `mix.exs` |
| Detect patterns | `erlang`, `elixir`, `phoenix` |
| Install | Rebar or Mix per docs |
| Docs | [Erlang SDK reference](https://launchdarkly.com/docs/sdk/server-side/erlang) |

**SDK detail:** [`sdk-snippets/erlang-server-sdk.md`](sdk-snippets/erlang-server-sdk.md)

### Haskell (Server)

| Field | Value |
|-------|-------|
| Package | `launchdarkly-server-sdk` (Cabal / Stack / Hackage) |
| Detect files | `*.cabal`, `stack.yaml`, `package.yaml` |
| Detect patterns | `haskell`, `cabal`, `stack` |
| Install | Add dependency per docs |
| Docs | [Haskell SDK reference](https://launchdarkly.com/docs/sdk/server-side/haskell) |

**SDK detail:** [`sdk-snippets/haskell-server-sdk.md`](sdk-snippets/haskell-server-sdk.md)

### Lua (Server)

| Field | Value |
|-------|-------|
| Package | `launchdarkly-server-sdk` (LuaRocks) |
| Detect files | `*.lua`, `*.rockspec` |
| Detect patterns | `lua`, `luarocks`, OpenResty / NGINX / HAProxy Lua |
| Install | `luarocks install launchdarkly-server-sdk` (see docs for your runtime) |
| Docs | [Lua SDK reference](https://launchdarkly.com/docs/sdk/server-side/lua) |

**SDK detail:** [`sdk-snippets/lua-server-sdk.md`](sdk-snippets/lua-server-sdk.md)

### PHP (Server)

| Field | Value |
|-------|-------|
| Package | `launchdarkly/server-sdk` |
| Detect files | `composer.json` |
| Detect patterns | `laravel`, `symfony`, `slim` |
| Install | `composer require launchdarkly/server-sdk` |
| Docs | [PHP SDK reference](https://launchdarkly.com/docs/sdk/server-side/php) |

**SDK detail:** [`sdk-snippets/php-server-sdk.md`](sdk-snippets/php-server-sdk.md)

### Ruby (Server)

| Field | Value |
|-------|-------|
| Package | `launchdarkly-server-sdk` |
| Detect files | `Gemfile`, `*.gemspec` |
| Detect patterns | `rails`, `sinatra`, `hanami` |
| Install | `gem install launchdarkly-server-sdk` or add to Gemfile |
| Docs | [Ruby SDK reference](https://launchdarkly.com/docs/sdk/server-side/ruby) |

**SDK detail:** [`sdk-snippets/ruby-server-sdk.md`](sdk-snippets/ruby-server-sdk.md)

### Rust (Server)

| Field | Value |
|-------|-------|
| Package | `launchdarkly-server-sdk` |
| Detect files | `Cargo.toml` |
| Detect patterns | `actix`, `rocket`, `axum`, `warp` |
| Install | `cargo add launchdarkly-server-sdk` |
| Docs | [Rust SDK reference](https://launchdarkly.com/docs/sdk/server-side/rust) |

**SDK detail:** [`sdk-snippets/rust-server-sdk.md`](sdk-snippets/rust-server-sdk.md)

---

## Client-side SDKs (other)

Client-side SDKs use a **Client-side ID** for browser and desktop clients where that credential is expected to be visible in the app. Use the linked reference for bootstrap, privacy, and flag delivery behavior.

**React (Web)** and **JavaScript (browser)** are in **[Top 10 SDKs (start here)](#top-10-sdks-start-here)** above.

### Vue

| Field | Value |
|-------|-------|
| Package | `launchdarkly-vue-client-sdk` |
| Detect files | `package.json` |
| Detect patterns | `vue`, `"vue":` |
| Install | `npm install launchdarkly-vue-client-sdk --save` |
| Docs | [Vue SDK reference](https://launchdarkly.com/docs/sdk/client-side/vue) |

**SDK detail:** [`sdk-snippets/vue-client-sdk.md`](sdk-snippets/vue-client-sdk.md)

### Angular, Svelte, Preact, and other browser frameworks

| Field | Value |
|-------|-------|
| Package | `launchdarkly-js-client-sdk` |
| Detect files | `package.json`, `angular.json`, `svelte.config.js` |
| Detect patterns | `@angular`, `svelte`, `preact` |
| Install | `npm install launchdarkly-js-client-sdk --save` |
| Docs | [JavaScript SDK reference](https://launchdarkly.com/docs/sdk/client-side/javascript) (no dedicated SDK; use the JS client) |

**SDK detail:** [`sdk-snippets/browser-frameworks-sdk.md`](sdk-snippets/browser-frameworks-sdk.md)

### .NET (Client)

| Field | Value |
|-------|-------|
| Package | `LaunchDarkly.ClientSdk` |
| Detect files | `*.csproj`, `*.sln` |
| Detect patterns | `Xamarin`, `MAUI`, `WPF`, `UWP`, `Avalonia` |
| Install | `dotnet add package LaunchDarkly.ClientSdk` |
| Docs | [.NET SDK reference (client-side)](https://launchdarkly.com/docs/sdk/client-side/dotnet) |

**SDK detail:** [`sdk-snippets/dotnet-client-sdk.md`](sdk-snippets/dotnet-client-sdk.md)

### C++ (Client)

| Field | Value |
|-------|-------|
| Package | `launchdarkly-cpp-client` (CMake / vcpkg per docs) |
| Detect files | `CMakeLists.txt`, `Makefile`, `*.cpp`, `*.h` |
| Detect patterns | Desktop or embedded C++ clients |
| Install | See docs |
| Docs | [C++ SDK reference (client-side)](https://launchdarkly.com/docs/sdk/client-side/c-c--) |

**SDK detail:** [`sdk-snippets/cpp-client-sdk.md`](sdk-snippets/cpp-client-sdk.md)

### Electron

| Field | Value |
|-------|-------|
| Package | `launchdarkly-electron-client-sdk` |
| Detect files | `package.json` |
| Detect patterns | `electron` |
| Install | `npm install launchdarkly-electron-client-sdk --save` |
| Docs | [Electron SDK reference](https://launchdarkly.com/docs/sdk/client-side/electron) |

**SDK detail:** [`sdk-snippets/electron-client-sdk.md`](sdk-snippets/electron-client-sdk.md)

### Node.js (Client)

| Field | Value |
|-------|-------|
| Package | `launchdarkly-node-client-sdk` |
| Detect files | `package.json` |
| Detect patterns | Node scripts or desktop tooling **without** Electron (see Electron above) |
| Install | `npm install launchdarkly-node-client-sdk --save` |
| Docs | [Node.js SDK reference (client-side)](https://launchdarkly.com/docs/sdk/client-side/node-js) |

**SDK detail:** [`sdk-snippets/node-client-sdk.md`](sdk-snippets/node-client-sdk.md)

### Roku (BrightScript)

| Field | Value |
|-------|-------|
| Package | [roku-client-sdk](https://github.com/launchdarkly/roku-client-sdk) (GitHub releases) |
| Detect files | `manifest`, `*.brs`, SceneGraph `*.xml` |
| Detect patterns | `brightscript`, `roku`, `SceneGraph` |
| Install | Add SDK components per docs |
| Docs | [Roku SDK reference](https://launchdarkly.com/docs/sdk/client-side/roku) |

**SDK detail:** [`sdk-snippets/roku-client-sdk.md`](sdk-snippets/roku-client-sdk.md)

---

## Mobile SDKs (other)

These SDKs use a **Mobile key** for native or cross-platform mobile apps. Each **Docs** link points at the official reference (same pages as the client-side SDK family on launchdarkly.com/docs).

**Swift / iOS**, **Android**, and **React Native** are in **[Top 10 SDKs (start here)](#top-10-sdks-start-here)** above.

### Flutter

| Field | Value |
|-------|-------|
| Package | `launchdarkly_flutter_client_sdk` |
| Detect files | `pubspec.yaml` |
| Detect patterns | `flutter` |
| Install | `flutter pub add launchdarkly_flutter_client_sdk` |
| Docs | [Flutter SDK reference](https://launchdarkly.com/docs/sdk/client-side/flutter) |

**SDK detail:** [`sdk-snippets/flutter-client-sdk.md`](sdk-snippets/flutter-client-sdk.md)

---

## Edge SDKs

Edge SDKs run on edge platforms and use an **SDK Key** (see each platform's reference for environment and constraints).

| Platform | Detect pattern | Docs |
|----------|----------------|------|
| Akamai EdgeWorkers | `bundle.json`, `edgeworkers` | [Akamai SDK reference](https://launchdarkly.com/docs/sdk/edge/akamai) |
| Cloudflare Workers | `wrangler.toml`, `@cloudflare/workers-types` | [Cloudflare SDK reference](https://launchdarkly.com/docs/sdk/edge/cloudflare) |
| Fastly Compute | Fastly service config, `@fastly/js-compute` (per your stack) | [Fastly SDK reference](https://launchdarkly.com/docs/sdk/edge/fastly) |
| Vercel Edge | `vercel.json` with edge functions, `@vercel/edge` | [Vercel SDK reference](https://launchdarkly.com/docs/sdk/edge/vercel) |

**SDK detail:** [`sdk-snippets/edge-sdks.md`](sdk-snippets/edge-sdks.md) (all edge platforms)

---