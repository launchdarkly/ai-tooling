---
title: JavaScript Browser SDK — SDK detail
description: Onboarding sample and links for the LaunchDarkly JavaScript client-side (browser) SDK
---

# JavaScript (Browser) — SDK detail

- Official docs: [JavaScript SDK reference](https://launchdarkly.com/docs/sdk/client-side/javascript)
- Recipe (detect / install): [SDK Recipes](../sdk-recipes.md) (JavaScript Browser)

Use this in an ES module context that supports top-level `await`, or wrap in an `async` function.

**Includes:** Copy-paste onboarding sample below.

```javascript
import { createClient } from 'launchdarkly-js-client-sdk';

// A "context" is a data object representing users, devices, organizations, and
// other entities. You'll need this later, but you can ignore it for now.
const context = {
  kind: 'user',
  key: 'EXAMPLE_CONTEXT_KEY',
};
const client = createClient(process.env.LAUNCHDARKLY_CLIENT_SIDE_ID, context);
client.start();

const { status } = await client.waitForInitialization();

if (status === 'complete') {
  console.log('SDK successfully initialized!');
} else {
  console.error('Initialization failed');
}
```