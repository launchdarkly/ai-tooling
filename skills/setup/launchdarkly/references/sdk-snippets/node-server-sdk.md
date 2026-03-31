---
title: Node.js Server SDK — SDK detail
description: Onboarding sample and links for the LaunchDarkly Node.js server-side SDK
---

# Node.js (Server) — SDK detail

- Official docs: [Node.js SDK reference (server-side)](https://launchdarkly.com/docs/sdk/server-side/node-js)
- Recipe (detect / install): [SDK Recipes](../sdk-recipes.md) (Node.js Server)

**Includes:** Copy-paste onboarding sample below.

```javascript
import * as LaunchDarkly from '@launchdarkly/node-server-sdk';

// Set your LaunchDarkly SDK key.
// This is inlined as example only for onboarding.
// Never hardcode your SDK key in production.
const client = LaunchDarkly.init(process.env.LAUNCHDARKLY_SDK_KEY);

try {
  await client.waitForInitialization(5);
  // initialization succeeded, flag values are now available
} catch (err) {
  // initialization failed or did not complete before timeout
}

client.on('initialized', () => {
  // initialization succeeded, flag values are now available
  const flagValue = client.variation('example-flag-key', false);
  // etc.
});