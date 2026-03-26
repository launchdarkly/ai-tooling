# LaunchDarkly SDK Onboarding

Onboard a project to LaunchDarkly by detecting the tech stack, installing the correct SDK, initializing it, validating the connection, and creating a first feature flag.

## When to Use

Use this skill when a user wants to:
- Add LaunchDarkly to their project
- Integrate a LaunchDarkly SDK
- Says "onboard me" or "set up LaunchDarkly"
- Get started with feature flags in an existing codebase

## Workflow

1. **Detect** — Identify language, framework, package manager, and existing SDK usage
2. **Plan** — Choose the correct SDK and generate a minimal integration plan
3. **Apply** — Install the SDK dependency and add initialization code
4. **Run** — Start the application and confirm SDK initialization
5. **Validate** — Verify LaunchDarkly sees the SDK connection
6. **First Flag** — Create a feature flag, evaluate it, and toggle it
7. **Recover** — If any step fails, diagnose and resume

## Supported SDKs

### Server-Side
Node.js, Python, Go, Java, Ruby, .NET, PHP, Rust, Erlang/Elixir

### Client-Side
React, Vue, JavaScript (browser), Node.js (Electron)

### Mobile
Swift/iOS, Android, Flutter, React Native

## Requirements

- LaunchDarkly account with an API access token
- LaunchDarkly MCP server (optional, enhances flag creation and validation)
