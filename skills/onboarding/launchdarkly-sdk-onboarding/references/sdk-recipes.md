---
title: SDK Recipes
description: Detection patterns, install commands, import statements, and initialization snippets for all LaunchDarkly SDKs
---

# SDK Recipes

Use this reference to match a detected tech stack to the correct LaunchDarkly SDK. Each recipe includes detection patterns, install commands, and initialization code.

## Server-Side SDKs

Server-side SDKs use an **SDK Key** and are designed for backend services where the key can be kept secret.

### Node.js (Server)

| Field | Value |
|-------|-------|
| Package | `@launchdarkly/node-server-sdk` |
| Detect files | `package.json` |
| Detect patterns | `express`, `fastify`, `koa`, `hapi`, `nestjs`, `next` (API routes), `"type": "module"` |
| Install | `npm install @launchdarkly/node-server-sdk --save` |

```javascript
// Import
const LaunchDarkly = require('@launchdarkly/node-server-sdk');

// Initialize
const ldClient = LaunchDarkly.init(process.env.LAUNCHDARKLY_SDK_KEY);
await ldClient.waitForInitialization();

// Evaluate
const context = { kind: 'user', key: 'user-key-123' };
const flagValue = await ldClient.variation('flag-key', context, false);
```

### Python (Server)

| Field | Value |
|-------|-------|
| Package | `launchdarkly-server-sdk` |
| Detect files | `requirements.txt`, `pyproject.toml`, `setup.py`, `Pipfile` |
| Detect patterns | `flask`, `django`, `fastapi`, `starlette` |
| Install | `pip install launchdarkly-server-sdk` |

```python
# Import
import ldclient
from ldclient import Context
from ldclient.config import Config

# Initialize
ldclient.set_config(Config(os.environ['LAUNCHDARKLY_SDK_KEY']))
client = ldclient.get()

# Evaluate
context = Context.builder("user-key-123").name("User").build()
flag_value = client.variation("flag-key", context, False)
```

### Go (Server)

| Field | Value |
|-------|-------|
| Package | `github.com/launchdarkly/go-server-sdk/v7` |
| Detect files | `go.mod`, `go.sum` |
| Detect patterns | `net/http`, `gin`, `echo`, `fiber`, `chi` |
| Install | `go get github.com/launchdarkly/go-server-sdk/v7` |

```go
// Import
import (
    ld "github.com/launchdarkly/go-server-sdk/v7"
    "github.com/launchdarkly/go-sdk-common/v3/ldcontext"
)

// Initialize
ldClient, err := ld.MakeClient(os.Getenv("LAUNCHDARKLY_SDK_KEY"), 5*time.Second)

// Evaluate
context := ldcontext.NewBuilder("user-key-123").Name("User").Build()
flagValue, _ := ldClient.BoolVariation("flag-key", context, false)
```

### Java (Server)

| Field | Value |
|-------|-------|
| Package | `com.launchdarkly:launchdarkly-java-server-sdk` |
| Detect files | `pom.xml`, `build.gradle`, `build.gradle.kts` |
| Detect patterns | `spring`, `quarkus`, `micronaut`, `dropwizard` |
| Install | Add `com.launchdarkly:launchdarkly-java-server-sdk` to your build file |

```java
// Import
import com.launchdarkly.sdk.*;
import com.launchdarkly.sdk.server.*;

// Initialize
LDClient client = new LDClient(System.getenv("LAUNCHDARKLY_SDK_KEY"));

// Evaluate
LDContext context = LDContext.builder("user-key-123").name("User").build();
boolean flagValue = client.boolVariation("flag-key", context, false);
```

### Ruby (Server)

| Field | Value |
|-------|-------|
| Package | `launchdarkly-server-sdk` |
| Detect files | `Gemfile`, `*.gemspec` |
| Detect patterns | `rails`, `sinatra`, `hanami` |
| Install | `gem install launchdarkly-server-sdk` or add to Gemfile |

```ruby
# Import
require 'ldclient-rb'

# Initialize
client = LaunchDarkly::LDClient.new(ENV['LAUNCHDARKLY_SDK_KEY'])

# Evaluate
context = LaunchDarkly::LDContext.create({ kind: 'user', key: 'user-key-123', name: 'User' })
flag_value = client.variation('flag-key', context, false)
```

### .NET (Server)

| Field | Value |
|-------|-------|
| Package | `LaunchDarkly.ServerSdk` |
| Detect files | `*.csproj`, `*.sln`, `*.fsproj` |
| Detect patterns | `Microsoft.AspNetCore`, `Microsoft.NET` |
| Install | `dotnet add package LaunchDarkly.ServerSdk` |

```csharp
// Import
using LaunchDarkly.Sdk;
using LaunchDarkly.Sdk.Server;

// Initialize
var client = new LdClient(Environment.GetEnvironmentVariable("LAUNCHDARKLY_SDK_KEY"));

// Evaluate
var context = Context.Builder("user-key-123").Name("User").Build();
var flagValue = client.BoolVariation("flag-key", context, false);
```

### PHP (Server)

| Field | Value |
|-------|-------|
| Package | `launchdarkly/server-sdk` |
| Detect files | `composer.json` |
| Detect patterns | `laravel`, `symfony`, `slim` |
| Install | `composer require launchdarkly/server-sdk` |

```php
// Import
use LaunchDarkly\LDClient;

// Initialize
$client = new LDClient(getenv('LAUNCHDARKLY_SDK_KEY'));

// Evaluate
$context = LDContext::builder('user-key-123')->name('User')->build();
$flagValue = $client->variation('flag-key', $context, false);
```

### Rust (Server)

| Field | Value |
|-------|-------|
| Package | `launchdarkly-server-sdk` |
| Detect files | `Cargo.toml` |
| Detect patterns | `actix`, `rocket`, `axum`, `warp` |
| Install | `cargo add launchdarkly-server-sdk` |

```rust
// Import
use launchdarkly_server_sdk::{Client, ConfigBuilder, ContextBuilder};

// Initialize
let config = ConfigBuilder::new(&std::env::var("LAUNCHDARKLY_SDK_KEY").unwrap()).build();
let client = Client::build(config).expect("Failed to create client");
client.start_with_default_executor();

// Evaluate
let context = ContextBuilder::new("user-key-123").name("User").build().unwrap();
let flag_value = client.bool_variation(&context, "flag-key", false);
```

### Erlang/Elixir (Server)

| Field | Value |
|-------|-------|
| Package | `ldclient` |
| Detect files | `rebar.config`, `mix.exs` |
| Detect patterns | `erlang`, `elixir`, `phoenix` |
| Install | Add `ldclient` to your `rebar.config` or `mix.exs` dependencies |

```erlang
%% Initialize
ldclient:start_instance(os:getenv("LAUNCHDARKLY_SDK_KEY")).

%% Evaluate
Context = ldclient_context:new(<<"user-key-123">>),
FlagValue = ldclient:variation(<<"flag-key">>, Context, false).
```

---

## Client-Side SDKs

Client-side SDKs use a **Client-side ID** and are designed for browser/frontend applications where the key is visible to users.

### React

| Field | Value |
|-------|-------|
| Package | `launchdarkly-react-client-sdk` |
| Detect files | `package.json` |
| Detect patterns | `react`, `react-dom`, `"react":` |
| Install | `npm install launchdarkly-react-client-sdk --save` |

```tsx
// Import
import { asyncWithLDProvider, useFlags } from 'launchdarkly-react-client-sdk';

// Initialize (in app entry)
const LDProvider = await asyncWithLDProvider({
  clientSideID: process.env.REACT_APP_LAUNCHDARKLY_CLIENT_SIDE_ID,
  context: { kind: 'user', key: 'anonymous' },
});

// Wrap app
<LDProvider><App /></LDProvider>

// Evaluate (in component)
const { myFlagKey } = useFlags(); // camelCase access
```

**Note:** React SDK converts kebab-case flag keys to camelCase. `my-flag-key` becomes `myFlagKey`.

### Vue

| Field | Value |
|-------|-------|
| Package | `launchdarkly-vue-client-sdk` |
| Detect files | `package.json` |
| Detect patterns | `vue`, `"vue":` |
| Install | `npm install launchdarkly-vue-client-sdk --save` |

```javascript
// Import
import { LDPlugin } from 'launchdarkly-vue-client-sdk';

// Initialize
app.use(LDPlugin, { clientSideID: process.env.VUE_APP_LAUNCHDARKLY_CLIENT_SIDE_ID });
```

### JavaScript (Browser)

| Field | Value |
|-------|-------|
| Package | `launchdarkly-js-client-sdk` |
| Detect files | `package.json`, `index.html` |
| Detect patterns | `webpack`, `vite`, `parcel`, `rollup` (without React/Vue/Angular) |
| Install | `npm install launchdarkly-js-client-sdk --save` |

```javascript
// Import
import * as LDClient from 'launchdarkly-js-client-sdk';

// Initialize
const context = { kind: 'user', key: 'anonymous' };
const client = LDClient.initialize('YOUR_CLIENT_SIDE_ID', context);
await client.waitForInitialization();

// Evaluate
const flagValue = client.variation('flag-key', false);
```

### Node.js (Client / Electron)

| Field | Value |
|-------|-------|
| Package | `launchdarkly-node-client-sdk` |
| Detect files | `package.json` |
| Detect patterns | `electron` |
| Install | `npm install launchdarkly-node-client-sdk --save` |

```javascript
// Import
const LDClient = require('launchdarkly-node-client-sdk');

// Initialize
const context = { kind: 'user', key: 'user-key-123' };
const client = LDClient.initialize('YOUR_CLIENT_SIDE_ID', context);
await client.waitForInitialization();

// Evaluate
const flagValue = client.variation('flag-key', false);
```

---

## Mobile SDKs

Mobile SDKs use a **Mobile Key** and are designed for native mobile applications.

### Swift / iOS

| Field | Value |
|-------|-------|
| Package | `LaunchDarkly` (Swift Package Manager) |
| Detect files | `Package.swift`, `Podfile`, `*.xcodeproj` |
| Detect patterns | `UIKit`, `SwiftUI`, `ios` |
| Install | Add `LaunchDarkly` to `Package.swift` or `Podfile` |

```swift
// Import
import LaunchDarkly

// Initialize
var config = LDConfig(mobileKey: ProcessInfo.processInfo.environment["LAUNCHDARKLY_MOBILE_KEY"]!)
let context = try LDContextBuilder(key: "user-key-123").build().get()
LDClient.start(config: config, context: context)

// Evaluate
let flagValue = LDClient.get()!.boolVariation(forKey: "flag-key", defaultValue: false)
```

### Android

| Field | Value |
|-------|-------|
| Package | `com.launchdarkly:launchdarkly-android-client-sdk` |
| Detect files | `build.gradle`, `build.gradle.kts`, `AndroidManifest.xml` |
| Detect patterns | `android`, `com.android`, `androidx` |
| Install | Add `com.launchdarkly:launchdarkly-android-client-sdk` to `build.gradle` |

```java
// Import
import com.launchdarkly.sdk.android.*;

// Initialize
LDConfig config = new LDConfig.Builder()
    .mobileKey(BuildConfig.LAUNCHDARKLY_MOBILE_KEY)
    .build();
LDContext context = LDContext.builder("user-key-123").build();
LDClient.init(application, config, context, 5);

// Evaluate
boolean flagValue = LDClient.get().boolVariation("flag-key", false);
```

### Flutter

| Field | Value |
|-------|-------|
| Package | `launchdarkly_flutter_client_sdk` |
| Detect files | `pubspec.yaml` |
| Detect patterns | `flutter` |
| Install | `flutter pub add launchdarkly_flutter_client_sdk` |

```dart
// Import
import 'package:launchdarkly_flutter_client_sdk/launchdarkly_flutter_client_sdk.dart';

// Initialize
final config = LDConfig(AutoEnvAttributes.enabled, 'YOUR_MOBILE_KEY');
final context = LDContextBuilder().kind('user', 'user-key-123').build();
final client = LDClient(config, context);
await client.start();

// Evaluate
final flagValue = await client.boolVariation('flag-key', false);
```

### React Native

| Field | Value |
|-------|-------|
| Package | `@launchdarkly/react-native-client-sdk` |
| Detect files | `package.json` |
| Detect patterns | `react-native` |
| Install | `npm install @launchdarkly/react-native-client-sdk --save` |

```tsx
// Import
import { LDProvider, useFlags } from '@launchdarkly/react-native-client-sdk';

// Initialize (wrap app)
<LDProvider mobileKey="YOUR_MOBILE_KEY">
  <App />
</LDProvider>

// Evaluate (in component)
const { myFlagKey } = useFlags();
```
