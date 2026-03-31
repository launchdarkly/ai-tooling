---
title: Java Server SDK — SDK detail
description: Onboarding sample and links for the LaunchDarkly Java server-side SDK
---

# Java (Server) — SDK detail

- Official docs: [Java SDK reference](https://launchdarkly.com/docs/sdk/server-side/java)
- Recipe (detect / install): [SDK Recipes](../sdk-recipes.md) (Java Server)

**Includes:** Copy-paste onboarding sample below.

```java
import com.launchdarkly.sdk.*;
import com.launchdarkly.sdk.server.*;

public class Main {
  public static void main(String[] args) {
    LDConfig config = new LDConfig.Builder().build();

    // Set your LaunchDarkly SDK key.
    // This is inlined as example only for onboarding.
    // Never hardcode your SDK key in production.
    final LDClient client = new LDClient(System.getenv("LAUNCHDARKLY_SDK_KEY"), config);

    if (client.isInitialized()) {
      // For onboarding purposes only we flush events as soon as
      // possible so we quickly detect your connection.
      // You don't have to do this in practice because events are automatically flushed.
      client.flush();
      System.out.println("SDK successfully initialized!");
    }
  }
}
```