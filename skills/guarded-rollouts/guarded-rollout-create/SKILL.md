---
name: guarded-rollout-create
description: "Configure a guarded rollout: define rollout stages (percentages and soak times), set metric thresholds for error rate, latency, and throughput, and enable automated rollback if thresholds are breached. Use when the user wants to set up or create a guarded rollout, add safety guardrails to a flag rollout, or configure automatic rollback. This skill configures the rollout — use launchdarkly-flag-targeting for simple percentage rollouts without automated monitoring."
license: Apache-2.0
compatibility: Requires LaunchDarkly MCP server with guarded rollout capabilities enabled.
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# Guarded Rollout Configuration

You're using a skill that will guide you through configuring a guarded rollout for a feature flag. Your job is to identify the flag and service, design rollout stages with appropriate soak times, define monitoring thresholds, configure the guarded rollout, and verify the configuration.

If the user hasn't determined baseline metrics for the service, suggest using the [service health check skill](../../observability/o11y-service-health/SKILL.md) first to establish current error rate, latency, and throughput baselines. Accurate baselines are essential for setting meaningful thresholds.

## Prerequisites

- **LaunchDarkly MCP server** with guarded rollout capabilities enabled
- **Required MCP tools:**
  - `create-guarded-rollout` — configure rollout stages, thresholds, and monitoring
  - `get-flag` — fetch flag configuration and current state
  - `get-service-metrics` — establish baseline metrics for the service
- **Optional MCP tools:**
  - `list-services` — discover available services and their identifiers
  - `get-metric-baselines` — retrieve pre-computed baseline statistics for a service

## Core Principles

1. **Define Success Before You Roll Out.** Know what "healthy" looks like before starting. Collect baseline metrics for error rate, latency, and throughput. Without baselines, thresholds are guesses, and guesses lead to either false rollbacks or missed regressions.

2. **Rollback is the Default.** On threshold breach, the system stops or rolls back. Advancing requires all checks passing. The guarded rollout system is biased toward safety — it assumes any anomaly is a problem until proven otherwise.

3. **Soak Time is Non-Negotiable.** Each stage needs enough time and traffic to detect problems. Memory leaks, cache effects, and load-dependent issues can take hours to manifest. Skipping soak time because metrics "look fine" defeats the purpose of guarded rollouts.

4. **Thresholds from Data, Not Guesses.** Derive thresholds from actual baseline metrics, not arbitrary numbers. A threshold of "1% error rate" is meaningless without knowing whether the baseline is 0.01% or 0.9%. Always anchor thresholds to measured baselines.

## Workflow

### Step 1: Identify Flag & Establish Baselines

Determine which flag to roll out and which service it affects. Gather the following information:

- **Flag key** — the identifier for the feature flag (e.g., `new-checkout-flow`)
- **Environment** — the target environment for the rollout (e.g., `production`)
- **Service** — the service that serves this flag and will be monitored

Use `get-flag` to confirm the flag exists and review its current configuration (variations, targeting rules, current rollout percentage).

Use `get-service-metrics` to establish current baselines:

- **Error rate** — the current percentage of requests resulting in errors
- **p50 latency** — median response time
- **p99 latency** — 99th percentile response time
- **Throughput** — requests per unit time

These baselines drive threshold selection in Step 3. If baseline data is unavailable, note this as an edge case and use conservative defaults with wider margins.

### Step 2: Design Rollout Stages

Choose a stage progression pattern based on risk level. See [rollout-stage-patterns.md](references/rollout-stage-patterns.md) for detailed pattern descriptions.

- **Conservative** (1% &rarr; 5% &rarr; 10% &rarr; 25% &rarr; 50% &rarr; 100%) — for payment systems, auth, data pipelines, or any change where failure has outsized impact.
- **Standard** (5% &rarr; 25% &rarr; 50% &rarr; 100%) — for most feature rollouts with moderate risk.
- **Aggressive** (10% &rarr; 50% &rarr; 100%) — for low-risk UI changes, already-validated features, or non-critical systems.

For each stage, define:

- **Percentage** of traffic receiving the new variation
- **Soak time** — minimum duration before advancing to the next stage
- **Total rollout duration** — the cumulative time from start to 100%

Present the proposed stage plan to the user for approval before proceeding. The user may want to adjust percentages, soak times, or add/remove stages based on their knowledge of the service.

### Step 3: Define Monitoring Thresholds

Set thresholds for each monitored metric. Thresholds determine when the system halts or rolls back the rollout. See [rollout-stage-patterns.md](references/rollout-stage-patterns.md) for detailed threshold-setting methodology.

- **Error rate:** Set to baseline + acceptable increase. Example: if baseline error rate is 0.5%, set threshold at 1.0% (baseline + 0.5 percentage points). Include an absolute ceiling as a safety net.
- **Latency p99:** Set to baseline p99 + acceptable increase. Example: if baseline p99 is 400ms, set threshold at 600ms (baseline + 200ms). Consider setting a p50 threshold as well.
- **Throughput:** Set a floor to detect traffic drops. Example: if baseline throughput is 5,000 req/hr, set minimum at 4,000 req/hr (80% of baseline).

Verify that all thresholds are above the natural maximum variation observed in baseline data. Thresholds below natural variation will cause false rollbacks.

Present the proposed thresholds to the user for approval.

### Step 4: Configure & Verify

Use `create-guarded-rollout` to set up the rollout with the designed stages and thresholds.

After configuration, verify every aspect:

- **Correct flag** — the rollout targets the intended flag key
- **Correct environment** — the rollout is configured for the right environment
- **Stages match plan** — percentages and soak times match the approved plan
- **Thresholds match plan** — error rate, latency, and throughput thresholds match the approved values
- **Rollback behavior correct** — automatic rollback is enabled (unless manual rollback was explicitly chosen with justification)

Confirm with the user before activating the guarded rollout. Once activated, the system will begin rolling traffic to the first stage and monitoring metrics.

## Edge Cases

| Scenario | Guidance |
|----------|----------|
| **Flag already has targeting rules** | Guarded rollout interacts with existing targeting rules. Review the flag's current rules with `get-flag` and determine whether the rollout should apply to all users or only those not matched by existing rules. The guarded rollout percentage applies to the fallthrough population (users not matched by any targeting rule). |
| **No baseline data available** | Use conservative thresholds with wider margins. Set error rate threshold at 2%, latency p99 threshold at 2x the team's expected value, and throughput floor at 50% of expected volume. Plan to tighten thresholds after the first stage provides real data. |
| **Service has very low traffic** | Need longer soak times to accumulate enough data points for statistical significance. Consider traffic-based soak criteria (e.g., "advance after 5,000 requests" rather than "advance after 12 hours"). Use the conservative pattern. |
| **Multiple environments need rollout** | Configure each environment separately. Start with the lowest-risk environment (e.g., staging, then production-canary, then production). Do not copy thresholds between environments — each environment has its own baseline. |
| **User wants custom stage progression** | Support custom progressions. Verify that the progression is monotonically increasing, that each stage has a soak time defined, and that the first stage is no higher than 25% (to preserve the "start small" principle). |

## What NOT to Do

- **Don't start a rollout without baseline metrics.** Thresholds without baselines are arbitrary numbers. Measure first, then configure.
- **Don't skip soak times.** Even if metrics look perfect after 30 minutes, the soak time exists to catch slow-burn issues. Respect the minimum.
- **Don't set thresholds without data.** "1% error rate sounds reasonable" is not a valid approach. Derive thresholds from measured baselines using the methodology in the reference documentation.
- **Don't configure rollback to "do nothing."** A guarded rollout that does not roll back on threshold breach is just a regular rollout with extra monitoring. The value of a guarded rollout is automated safety response.
- **Don't roll out to 100% in a single stage.** That is not a guarded rollout. Even the most aggressive pattern uses at least three stages to provide incremental validation.

## References

- [Rollout Stage Patterns Reference](references/rollout-stage-patterns.md) — detailed guidance on stage progressions, soak times, threshold-setting methodology, and common mistakes
- [Service Health Check Skill](../../observability/o11y-service-health/SKILL.md) — use to establish baseline metrics before configuring a guarded rollout
- [Regression Detection Skill](../../observability/o11y-regression-detect/SKILL.md) — use during an active rollout to investigate potential regressions detected by threshold monitoring
