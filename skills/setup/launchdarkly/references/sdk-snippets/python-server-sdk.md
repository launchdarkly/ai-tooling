---
title: Python Server SDK — SDK detail
description: Onboarding sample and links for the LaunchDarkly Python server-side SDK
---

# Python (Server) — SDK detail

- Official docs: [Python SDK reference](https://launchdarkly.com/docs/sdk/server-side/python)
- Recipe (detect / install): [SDK Recipes](../sdk-recipes.md) (Python Server)

**Includes:** Copy-paste onboarding sample below.

```python
import os
import ldclient
from ldclient import Context
from ldclient.config import Config

if __name__ == '__main__':
    # Set your LaunchDarkly SDK key.
    # This is inlined as example only for onboarding.
    # Never hardcode your SDK key in production.
    ldclient.set_config(Config(os.environ['LAUNCHDARKLY_SDK_KEY']))

    if not ldclient.get().is_initialized():
        print('SDK failed to initialize')
        exit()

    # For onboarding purposes only we flush events as soon as
    # possible so we quickly detect your connection.
    # You don't have to do this in practice because events are automatically flushed.
    ldclient.get().flush()
    print('SDK successfully initialized')
```