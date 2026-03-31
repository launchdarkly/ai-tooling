---
title: React Native Client SDK — SDK detail
description: Onboarding sample and links for the LaunchDarkly React Native SDK
---

# React Native — SDK detail

- Official docs: [React Native SDK reference](https://launchdarkly.com/docs/sdk/client-side/react/react-native)
- Recipe (detect / install): [SDK Recipes](../sdk-recipes.md) (React Native)

**Includes:** Copy-paste onboarding sample below.

```tsx
import { useEffect } from 'react';
import {
  AutoEnvAttributes,
  LDProvider,
  ReactNativeLDClient,
} from '@launchdarkly/react-native-client-sdk';

const ldClient = new ReactNativeLDClient(
  process.env.EXPO_PUBLIC_LAUNCHDARKLY_MOBILE_KEY!,
  AutoEnvAttributes.Enabled,
  {
    debug: true,
    applicationInfo: {
      id: 'ld-rn-test-app',
      version: '0.0.1',
    },
  },
);

// A "context" is a data object representing users, devices, organizations, and other entities.
const context = { kind: 'user', key: 'EXAMPLE_CONTEXT_KEY' };

const App = () => {
  useEffect(() => {
    ldClient.identify(context);
  }, []);

  return (
    <LDProvider client={ldClient}>
      <YourComponent />
    </LDProvider>
  );
};

export default App;
```

If you are not using Expo env vars, inject the mobile key from your native config or another secrets mechanism instead of `process.env.EXPO_PUBLIC_LAUNCHDARKLY_MOBILE_KEY`.