---
name: first-flag
description: "Create a boolean first flag, add evaluation, toggle on/off for end-to-end proof. Parent onboarding Step 6; uses MCP, API, or ldcli; optional flag-create skill."
license: Apache-2.0
compatibility: Requires SDK installed (parent Step 5) and LaunchDarkly project access
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# Create first feature flag

The SDK is connected. Now help the user create their first feature flag and see it work end-to-end.

This skill is nested under [LaunchDarkly onboarding](../SKILL.md); the parent **Step 6** is **first flag**. **Prior:** [Apply code changes](../sdk-install/apply/SKILL.md).

**Optional -- Flag Create skill already installed:** If the **`launchdarkly-flag-create`** skill from [github.com/launchdarkly/ai-tooling](https://github.com/launchdarkly/ai-tooling) is available in the session (install with `npx skills add launchdarkly/ai-tooling --skill launchdarkly-flag-create -y --agent <agent>`), you may use it for **creating the flag** and **choosing evaluation code** that matches the repo. You must still complete **default off -> verify OFF -> toggle on -> verify ON** (Steps 3-5 below). **Do not** require that skill: this page stays the full fallback when it is missing or MCP-only flows conflict with the user's setup.

## Security: Credential handling

**Never substitute literal token values into commands.** Use environment variable references instead:

- Shell commands: `$LAUNCHDARKLY_ACCESS_TOKEN` (expanded by the shell, not visible in `ps` output)
- Set the variable in your session: `export LAUNCHDARKLY_ACCESS_TOKEN=<your-token>`

This prevents tokens from appearing in process lists, shell history, and screen recordings.

## Step 0: Consult SDK flag-key guidance

Before creating the flag or wiring evaluation code, check the [Flag key behavior by SDK](#flag-key-behavior-by-sdk) table below. Some SDKs transform flag keys before exposing them in application code (e.g. the React SDK camelCases kebab-case keys). The flag key you create in LaunchDarkly, the SDK/framework configuration, and the key you reference in code must all align.

- **If the SDK transforms keys** (e.g. React `useFlags()` camelCases `my-first-flag` → `myFirstFlag`): generate evaluation code using the **transformed** key. The flag key in LaunchDarkly stays as-is (kebab-case is conventional).
- **If the SDK preserves keys as-is** (most server-side SDKs): use the exact LaunchDarkly flag key string in code.
- **If the SDK supports both modes** (e.g. React allows disabling camelCase via provider options): decide which mode the project uses (check existing code or provider config), then generate code that matches.

### Flag key behavior by SDK

| SDK | Key transformation | Code key for `my-first-flag` | Notes |
|-----|--------------------|------------------------------|-------|
| React Web (`useFlags()`) | camelCase by default | `myFirstFlag` | `reactOptions: { useCamelCaseFlagKeys: false }` on the provider disables this |
| React Native (`useFlags()`) | camelCase by default | `myFirstFlag` | Same `reactOptions` override available |
| Vue (`useLDFlag()`) | None (pass original key) | `'my-first-flag'` | |
| JavaScript Browser | None | `'my-first-flag'` | |
| Node.js Server | None | `'my-first-flag'` | |
| Python Server | None | `'my-first-flag'` | |
| Go Server | None | `"my-first-flag"` | |
| Java Server | None | `"my-first-flag"` | |
| .NET Server | None | `"my-first-flag"` | |
| Ruby Server | None | `'my-first-flag'` | |
| Swift/iOS | None | `"my-first-flag"` | |
| Android | None | `"my-first-flag"` | |
| Flutter | None | `'my-first-flag'` | |

When wiring the evaluation code in Step 2 below, use the **Code key** column value, not the raw LaunchDarkly key, whenever the SDK applies a transformation.

## Step 1: Create the flag

**REST / curl auth:** Use `$LAUNCHDARKLY_ACCESS_TOKEN` as the `Authorization` header value (LaunchDarkly uses the raw token, no `Bearer` prefix). The shell expands the variable but doesn't log it.

### Via MCP (preferred)

If the LaunchDarkly MCP server is available, use `create-feature-flag` (or the equivalent flag-creation tool your server exposes):

- **Key**: `my-first-flag` (or a name relevant to the user's project)
- **Name**: "My First Flag"
- **Kind**: `boolean`
- **Variations**: `true` / `false`
- **Temporary**: `true`

### Via LaunchDarkly API

```bash
curl -s -X POST \
  "https://app.launchdarkly.com/api/v2/flags/PROJECT_KEY" \
  -H "Authorization: $LAUNCHDARKLY_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My First Flag",
    "key": "my-first-flag",
    "kind": "boolean",
    "variations": [
      {"value": true},
      {"value": false}
    ],
    "temporary": true
  }'
```

### Via ldcli

```bash
ldcli flags create \
  --access-token "$LAUNCHDARKLY_ACCESS_TOKEN" \
  --project PROJECT_KEY \
  --data '{"name": "My First Flag", "key": "my-first-flag", "kind": "boolean", "temporary": true}'
```

After creation, the flag starts with **targeting OFF**, serving the off variation (`false`) to everyone. When the project key is known, link the user to the flag's dashboard page: **`https://app.launchdarkly.com/projects/{projectKey}/flags/my-first-flag`** (substitute the real project key).

## Step 2: Add flag evaluation code

Add code to evaluate the flag in the application. Place this where it makes sense for the user's feature.

### Server-side examples

```javascript
// Node.js (@launchdarkly/node-server-sdk) -- ldClient is your initialized server client after waitForInitialization
const context = { kind: 'user', key: 'example-user-key', name: 'Example User' };
const showFeature = await ldClient.boolVariation('my-first-flag', context, false);

if (showFeature) {
  console.log('Feature is ON');
} else {
  console.log('Feature is OFF');
}
```

```python
# Python (launchdarkly-server-sdk) -- client is ldclient.get() after set_config
from ldclient import Context

context = Context.builder("example-user-key").name("Example User").build()
show_feature = client.variation("my-first-flag", context, False)

if show_feature:
    print("Feature is ON")
else:
    print("Feature is OFF")
```

```go
// Go
context := ldcontext.NewBuilder("example-user-key").Name("Example User").Build()
showFeature, _ := ldClient.BoolVariation("my-first-flag", context, false)

if showFeature {
    fmt.Println("Feature is ON")
} else {
    fmt.Println("Feature is OFF")
}
```

### Client-side examples

```tsx
// React — useFlags() camelCases keys: "my-first-flag" → myFirstFlag (see Step 0 table)
import { useFlags } from 'launchdarkly-react-client-sdk';

function MyComponent() {
  const { myFirstFlag } = useFlags();

  return (
    <div>
      {myFirstFlag ? <p>Feature is ON</p> : <p>Feature is OFF</p>}
    </div>
  );
}
```

The React SDK's `useFlags()` hook camelCases kebab-case flag keys by default, so `my-first-flag` becomes `myFirstFlag`. If the project disables this via `reactOptions: { useCamelCaseFlagKeys: false }` on the provider, use the original key string instead. Always check the project's provider configuration before choosing which form to use — see the [Flag key behavior table](#flag-key-behavior-by-sdk) above.

## Step 3: Verify the default value

With targeting OFF, the flag should evaluate to `false`. Run the application and confirm:

```
Feature is OFF
```

## Step 4: Toggle the flag on

### Via MCP

The LaunchDarkly MCP server exposes **`update-feature-flag`** (JSON Patch), not a tool named `toggle-flag` -- use the tool names your MCP server lists.

**Simplest path:** Prefer **ldcli** or the **LaunchDarkly API** block below when you only need to turn the flag on once.

**If using `update-feature-flag`:** Call it with `projectKey`, `featureFlagKey`, and `PatchWithComment.patch` as a JSON Patch array. Turning the flag **on** for an environment typically uses a `replace` operation on that environment's `on` field (confirm the exact path from `get-feature-flag` for your account if needed):

```json
{
  "projectKey": "PROJECT_KEY",
  "featureFlagKey": "my-first-flag",
  "PatchWithComment": {
    "patch": [
      {
        "op": "replace",
        "path": "/environments/ENVIRONMENT_KEY/on",
        "value": true
      }
    ],
    "comment": "Onboarding: turn on my-first-flag"
  }
}
```

Replace `ENVIRONMENT_KEY` with the environment key for the environment you are targeting (e.g. `test`, `production`).

### Via LaunchDarkly API

```bash
curl -s -X PATCH \
  "https://app.launchdarkly.com/api/v2/flags/PROJECT_KEY/my-first-flag" \
  -H "Authorization: $LAUNCHDARKLY_ACCESS_TOKEN" \
  -H "Content-Type: application/json; domain-model=launchdarkly.semanticpatch" \
  -d '{
    "environmentKey": "ENVIRONMENT_KEY",
    "instructions": [
      {"kind": "turnFlagOn"}
    ]
  }'
```

### Via ldcli

```bash
ldcli flags toggle-on \
  --access-token "$LAUNCHDARKLY_ACCESS_TOKEN" \
  --project PROJECT_KEY \
  --environment ENVIRONMENT_KEY \
  --flag my-first-flag
```

## Step 5: Verify the toggle

After toggling the flag on, the application should now show:

```
Feature is ON
```

For server-side SDKs using streaming (the default), the change should be reflected within seconds. For client-side SDKs, the change appears on the next page load or when the SDK polls for updates.

## Step 6: Add an interactive demo

Now that the flag works, add a **visible, interactive element** so the user can see the flag in action -- not just a console log. This creates a "wow" moment and gives the user a tangible proof point they can show others.

**Choose the right demo based on what you detected:**

| App type | What to add | User experience |
|----------|-------------|-----------------|
| **Frontend (React, Vue, SPA)** | A banner, badge, or button gated by the flag | Toggle flag in dashboard → refresh page → element appears/disappears |
| **Backend API (Node, Python, Go, etc.)** | A `/launchdarkly-demo` endpoint that returns flag state as JSON | `curl` the endpoint → toggle flag → `curl` again → response changes |
| **Full-stack (Next.js SSR, Rails, etc.)** | Both: an API endpoint + a UI element that displays the flag state | Toggle flag → see both API and UI reflect the change |
| **CLI / script** | A `--feature-demo` flag or distinct output mode | Run script → toggle flag → run again → output changes |

### Frontend demo example (React)

Add a component or element that's visually obvious when the flag is on:

```tsx
// Add to an existing page component
import { useFlags } from 'launchdarkly-react-client-sdk';

function FeatureFlagDemo() {
  const { myFirstFlag } = useFlags();

  if (!myFirstFlag) return null;

  return (
    <div style={{
      padding: '12px 20px',
      backgroundColor: '#405BFF',
      color: 'white',
      borderRadius: '8px',
      margin: '16px 0',
      fontWeight: 500
    }}>
      LaunchDarkly is working — this banner is controlled by a feature flag
    </div>
  );
}
```

Place it somewhere visible (e.g., at the top of the main page or in a dashboard/header area).

### Backend demo example (Node.js/Express)

Add an endpoint that returns the flag state:

```javascript
// Add to your Express app (or equivalent for other frameworks)
app.get('/launchdarkly-demo', async (req, res) => {
  const context = { kind: 'user', key: 'demo-user' };
  const flagValue = await ldClient.boolVariation('my-first-flag', context, false);
  
  res.json({
    flag: 'my-first-flag',
    enabled: flagValue,
    message: flagValue 
      ? 'LaunchDarkly is working — the flag is ON'
      : 'LaunchDarkly is working — the flag is OFF'
  });
});
```

Tell the user to test with: `curl http://localhost:PORT/launchdarkly-demo`

### Backend demo example (Python/Flask)

```python
@app.route('/launchdarkly-demo')
def launchdarkly_demo():
    context = Context.builder("demo-user").build()
    flag_value = ld_client.variation("my-first-flag", context, False)
    
    return jsonify({
        "flag": "my-first-flag",
        "enabled": flag_value,
        "message": "LaunchDarkly is working — the flag is ON" if flag_value 
                   else "LaunchDarkly is working — the flag is OFF"
    })
```

### Full-stack demo

For apps with both server and client (e.g., Next.js, Remix, Rails with frontend):

1. Add the API endpoint (backend example above)
2. Add a UI component that either calls the endpoint or uses the client SDK directly
3. The user can verify both paths work

### Guidelines

1. **Match existing patterns** -- use the same routing style, component conventions, and code style as the rest of the app
2. **Make it obvious** -- use color, position, or text that clearly indicates this is the LaunchDarkly demo
3. **Keep it removable** -- add a brief comment like `// LaunchDarkly demo - safe to remove` so the user knows they can delete it later (or keep it as a template)
4. **Don't over-engineer** -- this is a demo, not a production feature; a few lines of code is ideal

### Walk the user through it

After adding the demo element:

1. Tell the user where you added it and how to see it (URL, page location, command)
2. Have them verify it shows the current flag state
3. Ask them to toggle the flag in the dashboard (provide the deep link: `https://app.launchdarkly.com/projects/{projectKey}/flags/my-first-flag`)
4. Have them refresh/re-run to see the change
5. Celebrate the successful integration

## Congratulations

The user has successfully:

1. Installed the LaunchDarkly SDK
2. Connected it to LaunchDarkly
3. Created a feature flag
4. Evaluated it in code
5. Toggled it and seen the result
6. Added an interactive demo they can show others

This is the "proof point" moment -- the user has a working feature flag they can toggle in real-time. The demo element makes it tangible and shareable.

**Encourage the next skill:** Suggest they **install or enable** the **`launchdarkly-flag-create`** skill from [github.com/launchdarkly/ai-tooling](https://github.com/launchdarkly/ai-tooling) (`npx skills add launchdarkly/ai-tooling --skill launchdarkly-flag-create -y --agent <agent>`) so future work -- creating flags that match repo conventions, wrapping features, and verifying wiring -- has a dedicated playbook. Offer to help them add it if they are unsure how.

## Error handling

### Authorization errors

If any step returns a **401** or **403**:

**D9 -- BLOCKING:** Call your structured question tool now.
- question: "I received an authorization error ([specific status code and message]). This requires your action to resolve -- I cannot retry automatically."
- options:
  - "I'll re-authenticate -- run ldcli login or refresh my token"
  - "Let me check my access token and try again"
  - "I don't have an account -- help me sign up"
  - "The project or environment doesn't exist -- help me create one"
- STOP. Do not write the question as text. Do not retry authorization errors automatically -- they always require user action. Do not continue until the user selects an option.

### Other errors

For non-auth errors (flag creation failures, SDK key mismatches, flags returning fallback values, etc.), diagnose the issue using the error output, application logs, and your understanding of the project.

**Next steps to suggest:**

- **Install** **`launchdarkly-flag-create`** from [github.com/launchdarkly/ai-tooling](https://github.com/launchdarkly/ai-tooling) if it is not already available -- this onboarding flow only covers a first boolean flag; that skill guides real-world flag creation aligned with existing code patterns (requires LaunchDarkly MCP per that skill's prerequisites).
- Use **`launchdarkly-flag-targeting`** from the same distribution to set up percentage rollouts and targeting rules
- Read the [LaunchDarkly docs](https://docs.launchdarkly.com) for advanced topics like contexts, experimentation, and metrics

---

**Upon completion, continue with:** [Onboarding summary](../references/1.8-summary.md) and [Editor rules and skills](../references/1.9-editor-rules.md) (default follow-through in the parent onboarding skill -- **not** MCP setup, which is Step 4). For MCP install or troubleshooting, use [mcp-configure](../mcp-configure/SKILL.md) and [MCP Config Templates](../mcp-configure/references/mcp-config-templates.md).
