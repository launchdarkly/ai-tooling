---
title: .NET Server SDK — SDK detail
description: ASP.NET Core onboarding sample and links for the LaunchDarkly server-side .NET SDK
---

# .NET (Server) — SDK detail

- Official docs: [.NET SDK reference (server-side)](https://launchdarkly.com/docs/sdk/server-side/dotnet)
- Recipe (detect / install): [SDK Recipes](../sdk-recipes.md) (.NET Server)

**Includes:** Copy-paste onboarding sample below.

```csharp
using LaunchDarkly.Sdk;
using LaunchDarkly.Sdk.Server;

var builder = WebApplication.CreateBuilder(args);

// Set your LaunchDarkly SDK key.
// This is inlined as example only for onboarding.
// Never hardcode your SDK key in production.
var ldConfig = Configuration.Default(Environment.GetEnvironmentVariable("LAUNCHDARKLY_SDK_KEY"));
var client = new LdClient(ldConfig);

if (client.Initialized)
{
    // For onboarding purposes only we flush events as soon as
    // possible so we quickly detect your connection.
    // You don't have to do this in practice because events are automatically flushed.
    client.Flush();
    Console.WriteLine("*** SDK successfully initialized!\n");
}
else
{
    Console.WriteLine("*** SDK failed to initialize\n");
    Environment.Exit(1);
}
```