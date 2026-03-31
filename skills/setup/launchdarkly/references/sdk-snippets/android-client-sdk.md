---
title: Android Client SDK — SDK detail
description: Kotlin onboarding sample and links for the LaunchDarkly Android SDK
---

# Android — SDK detail

- Official docs: [Android SDK reference](https://launchdarkly.com/docs/sdk/client-side/android)
- Recipe (detect / install): [SDK Recipes](../sdk-recipes.md) (Android)

**Includes:** Copy-paste onboarding sample below.

```kotlin
import com.launchdarkly.sdk.*
import com.launchdarkly.sdk.android.*

val ldConfig = LDConfig.Builder(AutoEnvAttributes.Enabled)
    .mobileKey(BuildConfig.LAUNCHDARKLY_MOBILE_KEY)
    .build()

// A "context" is a data object representing users, devices, organizations, and other entities.
val context = LDContext.create("EXAMPLE_CONTEXT_KEY")

// If you don't want to block execution while the SDK tries to get
// latest flags, move this code into an async IO task and await on its completion.
val client: LDClient = LDClient.init(this@BaseApplication, ldConfig, context, 5)
```