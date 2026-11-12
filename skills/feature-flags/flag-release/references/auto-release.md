# Auto-release: automated rollout configs & release plans

This is the mechanism behind the "release" half of the skill. The goal: once the PR
merges and the guarding flag starts evaluating, the change rolls out **on its own**,
the way the team has decided changes should roll out in each environment — no human toggling a flag.

## The pieces

- **Flag** — the boolean gate you created (OFF everywhere). Nothing happens to users until a release turns it on.
- **Environment release plan** — a reusable recipe for one environment: phases, rollout steps, and metrics. Each environment has at most one **default** release plan, and auto-release uses it. A plan with metrics is guarded, so a regression on a metric can roll the release back. A plan without metrics is progressive.
- **Flag release plan** — an optional project-level recipe that says, per environment, whether a flag releases immediately or with a named environment release plan. A project can have one default flag release plan. Read and manage these with the [`launchdarkly-flag-release-plans`](../../../release-autopilot/launchdarkly-flag-release-plans/SKILL.md) skill.
- **Automated rollout config** — the per-flag, per-PR record (created by `create-automated-rollout-config`) that ties the flag to the merge and says, per environment, whether to release immediately or with the environment's release plan (`releaseType: "policy"`).

## Immediate vs `policy`

`create-automated-rollout-config` takes an `environments` array; each entry has an
`environmentKey` and, for a release-plan release, `releaseType: "policy"`. `releaseType` accepts only
`override` and `policy`; there is no `simple`. The value name `policy` is historical: it means "release with this environment's default release plan".

- **Immediate** (`{ environmentKey }`, no `releaseType` or `override`): serve `true` in that environment once the flag begins evaluating — the same trigger `policy` waits for, just with no plan and no steps. Use it for dev/staging environments you want fully enabled without ceremony.

- **`policy`** (`{ environmentKey, releaseType: "policy" }`): not a hold — it never waits for a date or a sign-off. Wait until the PR merges and the flag begins evaluating, then start the environment's default release plan — progressive or guarded — automatically. Use it for production and any environment where you want a governed, monitored rollout with the safety net the team already defined.

A typical plan: `staging → immediate`, `production → policy`.

An operator can also pin a rollout with `releaseType: "override"` and an `override` object whose
`releaseMethod` is `immediate`, `progressive`, or `guarded`. Progressive and guarded need `stages`
(`allocation` and `durationMillis`, allocations strictly increasing; guarded caps each stage at
`50000` and needs `metricKeys` or `metricGroupKeys`). Never combine `override` with `policy`.

## Preview before you propose

Always call `get-environment-release-plans` (with `projectKey` and `environmentKey`) for each environment before you recommend `policy` for it, so you and the user know what `policy` will do. The default plans do not depend on the flag, so the preview works before the flag exists too.

- The plan with `default: true` is the plan `policy` starts. Show its name, rollout steps (`progressiveRelease.phases[].steps`, allocations per 100,000), advancement mode, and metrics.
- `progressiveRelease.metrics` keyed by metric key makes the plan **guarded**. Empty metrics make it **progressive**: say so, because nothing rolls it back automatically.
- Auto-release starts the plan on the flag's default rule. That needs a plan with one phase for everyone (only the randomization unit clause). A default plan with several phases, or with a phase that targets an audience, fails to start. Tell the user before you record it.
- If a flag release plan applies (the user names one, or the project has a default), read it with `launchdarkly-flag-release-plans`. For each environment it lists, it says either `isImmediate` or an `environmentReleasePlanKey`. Use that choice for the environment, below the human's intent.

### No default release plan

If no plan in an environment is marked default, auto-release cannot run there. There is no fallback. Do not record that environment as `policy`. Instead:

1. Tell the user that the environment has no default release plan, so auto-release can't run there until one exists.
2. Point them to [`launchdarkly-release-autopilot-onboarding`](../../../release-autopilot/launchdarkly-release-autopilot-onboarding/SKILL.md), which offers starter plans, or to the environment's release plan settings in LaunchDarkly.
3. Hold the environment (leave it out of the call), or record it as immediate if the user asks for that.

An environment that has only incomplete plans has no usable default either: an incomplete plan can't start a release or become the default.

**A guarded release is only as good as its metrics.** If a `policy` env's default plan is **guarded**, check that its metrics are relevant to this change — a guarded rollout with no meaningful metric guards nothing. Watch for the **net-new path** case (from `should-flag-change`'s output, if present): when the flag-off control renders nothing, feature-specific before/after comparisons are "one-armed" and can't detect a regression, so a guarded release must lean on existing global/service metrics. If the plan's metrics can't compare treatment vs. control for this change, say so and recommend an immediate release for that env (or point the user at metric setup) rather than presenting a guarded rollout that can't actually guard.

## Precedence

For each environment, precedence is:

**human release intent → explicit override → flag release plan → environment's default release plan**

If none of these applies, the environment has no release: hold it and say why.

A human's stated intent — captured before recording (release now / hold / `notBefore` / segment /
prerequisite) — sits *above* every plan: if the user said "hold until August," you don't register a
config that releases that env on merge, no matter what the plan would do. Below intent, an operator override
wins over the plans, a flag release plan's choice for the environment wins over the environment's default,
and the default release plan applies when nothing above it does. You generally don't set
overrides from this skill; you rely on the default release plan, which is why previewing it matters.

**Fail closed.** Intent is honored or explicitly held — never silently dropped. If you can't
express a piece of intent through the available tools (e.g. a `notBefore` date the rollout config
can't encode), leave the flag OFF for that env and report it as held with the reason, rather than
registering a release that ignores the constraint. An unclear intent should *prevent* a release,
never cause one.

## Registering the config

Call `create-automated-rollout-config` in the implement phase:

```json
{
  "projectKey": "default",
  "flagKey": "new-checkout-flow",
  "environments": [
    { "environmentKey": "staging" },
    { "environmentKey": "production", "releaseType": "policy" }
  ],
  "repoFullName": "acme/storefront",
  "prNumber": 482
}
```

The guarding flag must already exist. Provide the PR reference (`repoFullName` + `prNumber`,
or `prUrl`) so the rollout is bound to the right merge. The call returns `created`,
`config_id`, and the normalized per-environment plan — record `config_id` in your report.

The call can return warnings with the codes `missing_policy` or `incomplete_policy`. These codes come from an older release model, not from the release plans. Show them to the user as they are, but base the per-environment plan on the default release plans you read.

### Releasing with a plan that is not the default

The MCP tool can't name an environment release plan, so a `policy` entry always starts the environment's default. When a flag release plan (or the user) picks another environment release plan for an environment, offer these options:

- Release with the default plan through the MCP tool, and say which plan that is.
- Hold the environment.
- Record the whole config through the REST API, which takes `environmentReleasePlanKey` on a `policy` environment.

For the REST API, give the user this command to run in their own terminal. They set `LD_API_TOKEN` in their shell first. Never ask for the token in the chat, and never read or print it yourself.

```bash
curl -sS -X POST "https://app.launchdarkly.com/api/v2/projects/default/automated-rollout-configs" \
  -H "Authorization: $LD_API_TOKEN" \
  -H "LD-API-Version: beta" \
  -H "Content-Type: application/json" \
  -d '{
    "flagKey": "new-checkout-flow",
    "repoFullName": "acme/storefront",
    "prNumber": 482,
    "environments": [
      { "environmentKey": "staging", "desiredReleaseType": "policy" },
      { "environmentKey": "production", "desiredReleaseType": "policy", "environmentReleasePlanKey": "guarded-prod" }
    ]
  }'
```

The REST field is `desiredReleaseType`, not `releaseType`. The same RELEASE/HOLD rule applies: a held environment is left out of the body. The response has the config `id`; ask the user for it so you can report it.

## Coupling to a parent flag (prerequisites)

When the change depends on another feature that isn't live yet, don't leave the ordering as a
human note — make it structural with a LaunchDarkly **prerequisite**. The dependent flag lists
the parent as a prerequisite (parent must serve its "on" variation) so the dependent can be
turned on safely: while the parent is off, the dependent stays effectively off; when the parent
releases, the dependent goes live in lockstep. This is native LaunchDarkly behavior, so it's the
right way to express "this must not go live before X." Set it via the MCP surface if it exposes
prerequisite editing; if it doesn't, report the required prerequisite as a manual step and do not
register a rollout that could release this flag ahead of its parent.

## Relationship to guarded rollouts

When a `policy` environment's default release plan is **guarded**, the merge triggers the
same kind of progressive, metric-monitored rollout described in the
[`launchdarkly-guarded-rollout`](../../launchdarkly-guarded-rollout/SKILL.md) skill — the
difference is that here it's driven automatically by the release plan on merge, rather than started
by hand. If a change needs a *bespoke* rollout that no release plan expresses, record that environment
as immediate here and drive the guarded rollout manually with that skill after merge.
