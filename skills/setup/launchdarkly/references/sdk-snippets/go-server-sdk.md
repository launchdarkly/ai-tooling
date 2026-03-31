---
title: Go Server SDK — SDK detail
description: Onboarding sample and links for the LaunchDarkly Go server-side SDK
---

# Go (Server) — SDK detail

- Official docs: [Go SDK reference](https://launchdarkly.com/docs/sdk/server-side/go)
- Recipe (detect / install): [SDK Recipes](../sdk-recipes.md) (Go Server)

**Includes:** Copy-paste onboarding sample below.

```go
package main

import (
	"fmt"
	"os"
	"time"

	ld "github.com/launchdarkly/go-server-sdk/v7"
)

func main() {
	ldClient, _ := ld.MakeClient(os.Getenv("LAUNCHDARKLY_SDK_KEY"), 5*time.Second)
	if ldClient.Initialized() {
		fmt.Printf("SDK successfully initialized!")
	} else {
		fmt.Printf("SDK failed to initialize")
		os.Exit(1)
	}

	// For onboarding purposes only we flush events as soon as
	// possible so we quickly detect your connection.
	// You don't have to do this in practice because events are automatically flushed.
	ldClient.Flush()
}
```