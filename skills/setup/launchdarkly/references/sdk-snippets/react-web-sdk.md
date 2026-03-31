---
title: React Web SDK — SDK detail
description: Root-level React onboarding sample and links for the LaunchDarkly React Web SDK
---

# React (Web) — SDK detail

- Official docs: [React SDK reference](https://launchdarkly.com/docs/sdk/client-side/react) · [React Web SDK reference](https://launchdarkly.com/docs/sdk/client-side/react/react-web)
- Recipe (detect / install): [SDK Recipes](../sdk-recipes.md) (React Web)

**Includes:** Copy-paste onboarding sample below.

```tsx
// Add the code below to the root of your React app.
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { LDProvider } from 'launchdarkly-react-client-sdk';

function App() {
  return <div>Let your feature flags fly!</div>;
}

// A "context" is a data object representing users, devices, organizations, and other entities.
const context = {
  kind: 'user',
  key: 'EXAMPLE_CONTEXT_KEY',
  email: 'user@example.com',
};

// The clientSideID identifies your environment in LaunchDarkly.
// Never commit real credentials; load from env or your build configuration.
createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <LDProvider clientSideID={import.meta.env.VITE_LAUNCHDARKLY_CLIENT_SIDE_ID} context={context}>
      <App />
    </LDProvider>
  </StrictMode>,
);
```

For Create React App, replace `import.meta.env.VITE_LAUNCHDARKLY_CLIENT_SIDE_ID` with `process.env.REACT_APP_LAUNCHDARKLY_CLIENT_SIDE_ID`.