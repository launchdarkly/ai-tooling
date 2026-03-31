---
title: iOS (Swift) Client SDK — SDK detail
description: Onboarding sample and links for the LaunchDarkly iOS SDK
---

# Swift / iOS — SDK detail

- Official docs: [iOS SDK reference](https://launchdarkly.com/docs/sdk/client-side/ios)
- Recipe (detect / install): [SDK Recipes](../sdk-recipes.md) (Swift / iOS)

**Includes:** Copy-paste onboarding sample below.

```swift
import LaunchDarkly

// Set your LaunchDarkly mobile key.
// Never hardcode your mobile key in production.
let mobileKey = ProcessInfo.processInfo.environment["LAUNCHDARKLY_MOBILE_KEY"]!
var config = LDConfig(mobileKey: mobileKey)

// A "context" is a data object representing users, devices, organizations, and other entities.
let context = try LDContextBuilder(key: "EXAMPLE_CONTEXT_KEY").build().get()

LDClient.start(config: config, context: context)

if let client = LDClient.get(), client.isInitialized {
    // For onboarding purposes only we flush events as soon as
    // possible so we quickly detect your connection.
    client.flush()
    print("SDK successfully initialized!")
} else {
    print("SDK failed to initialize")
}
```