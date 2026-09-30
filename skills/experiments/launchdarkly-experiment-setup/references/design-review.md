# Experiment Design Review

Run this review before `create-experiment`. Report each item as **OK** or **Concern**, give a one-line reason, and suggest a fix for each concern. Don't block on minor concerns. Summarize, let the user decide, and carry the agreed design into Step 3 exactly as reviewed.

## 1. Hypothesis

Template: **"If we <change>, then <primary metric> will <increase/decrease> by at least <minimum detectable effect>, because <reason>."**

- Concern: there's no direction, no expected size, or no reason.
- An expected effect size makes the sample-size estimate in item 6 possible, and makes the stop decision objective.

## 2. Primary metric

- Choose exactly one primary metric. It should be the metric the ship/no-ship decision rests on.
- It must be emitted for the same context kind you randomize on (see item 4).
- Prefer a conversion (binary) metric when the outcome is "did it happen". Use a numeric metric for amounts like revenue or time. Use a percentile metric for latency or other long-tailed values, because means hide tail regressions.
- Use a funnel metric group only when the decision really is about step-through rate.
- Concern: the primary metric is a vanity metric, or is only indirectly affected by the change.

## 3. Guardrail and secondary metrics

- Add one or two guardrails that would stop you from shipping even if the primary metric wins, such as error rate, latency, revenue, or unsubscribes.
- Concern: there are more than about 5 metrics. Each extra metric adds false-positive risk, and makes results harder to read.

## 4. Randomization unit

The unit must match the level where the effect happens, and the level where the metric is recorded.

| Change | Typical unit |
|---|---|
| UI or UX change seen by a person | `user` |
| B2B, pricing, or plan change where teammates should see the same experience | an organization or account context kind |
| Anonymous or pre-login experience | device or anonymous user key |
| Stateless backend or performance change with no user-visible memory | request-level context |

- Concern: the metric is tracked on a different context kind than the one being randomized. For example, randomizing by `user` while the metric fires with an account key produces results that can't be analyzed.
- Concern: one person could see both variations, for example across devices when you randomize by device.

## 5. Treatments and allocation

- Default to two arms, a control (`baseline: true`) and one variation, with an even split.
- Justify every extra arm. Each one spreads the same traffic thinner and lengthens the run.
- Uneven splits such as 90/10 are for limiting risk, not for speed. They make the experiment take longer to reach a result.
- Allocations must sum to 100 across treatments. If you want less than 100% of traffic in the experiment, narrow the targeting rule instead of leaving a gap.

## 6. Sample size and duration

- Estimate the required sample from four inputs: the baseline rate or mean of the primary metric, the minimum detectable effect from item 1, the number of arms, and the daily traffic that reaches the flag rule.
- If you can't estimate it, say so and ask the user for their baseline and traffic. Don't invent them.
- Run for at least one full weekly cycle (7 or more days), even if a result appears sooner, so that weekday and weekend behavior are both represented.
- Agree on the planned duration up front. Don't stop the moment results first look significant.
- If the estimated duration is impractical, suggest a larger minimum detectable effect, fewer arms, a higher-traffic metric, or variance reduction (item 7).

## 7. Variance reduction

- If the primary metric has pre-experiment history for the same units, suggest enabling CUPED (covariate adjustment) where the project supports it. It can shorten the required duration substantially.
- Stratified sampling with a covariate (`covariateId`) helps when a few large segments dominate traffic.

## 8. Exposure and targeting

- Confirm the flag rule serves only the population the hypothesis is about.
- Confirm the flag is on in the target environment, which the API requires before starting.
- Exclude internal, test, and bot traffic where possible.
- If another experiment or rollout targets the same flag or the same users, flag the interaction risk and consider a holdout.

## 9. Decision rule

Write down, before starting:
- what ships if the primary metric wins and the guardrails hold
- what happens if the result is flat or negative (keeping the control is a valid, useful outcome)
- which guardrail movement would trigger an early stop

Put the one-line decision rule in the experiment `description` so it's visible to everyone later.

## 10. Early health checks after starting

- **Sample ratio mismatch:** once traffic arrives, confirm the observed split matches the configured allocation. A large mismatch means assignment or tracking is broken, and results can't be trusted. Stop and fix the setup instead of reading results.
- **Exposure and metric events:** confirm events are arriving for every treatment.
