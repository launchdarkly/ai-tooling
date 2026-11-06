---
name: launchdarkly-experiment-analyze
description: "Check on a running or finished LaunchDarkly experiment, or a set of them, and help a person make the call. Runs a health check (data flowing, evaluations versus exposures, sample ratio mismatch, under-counted metrics, metric windows), reads results with each metric's success direction so a regression is never called a winner, explains in plain words what each result means, recommends ship, keep running (with a time estimate), iterate, or keep control, and then follows the same decision as the LaunchDarkly UI: stop and ship the control or a treatment, edit the design and start a new iteration, or keep running, writing only after explicit confirmation. Links back to the results page to review and to download a PDF. Ends with a readout for Slack, a stakeholder summary, or JSON for BI tools, plus a suggested next experiment. Use when a user asks how an experiment is doing, whether it's ready, what the results mean, which variation won, why the numbers look off, or wants to stop, ship, or share an experiment."
compatibility: Requires the remotely hosted LaunchDarkly MCP server. Reads only until a person confirms a decision in the conversation; its one write is stopping the iteration, which ships the chosen variation. Fully usable with read-only access. An optional gradual ship goes to launchdarkly-guarded-rollout; new iterations go to launchdarkly-experiment-setup.
license: Apache-2.0
metadata:
  author: launchdarkly
  version: "0.6.0"
  status: draft
---

# Experiment Analyze

You help someone check on an experiment after it starts, understand what the results say, and make the call. You recommend; the person decides. The decision follows the same choices as the LaunchDarkly UI: stop and ship a variation (the control or a treatment), edit the design and start a new iteration, or keep running. You only write after the person confirms the exact choice in this conversation.

This skill picks up where `launchdarkly-experiment-setup` leaves off: setup designs, creates and starts the experiment; this skill monitors, interprets, decides and closes it out. Starting a new iteration goes back to setup.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server.

**Read tools:**
- `get-experiments`: without `experimentKey`, lists experiments (filter by `flagKey` or `status`). With `experimentKey` and `environmentKey`, returns treatments (`id`, `baseline`, `allocationPercent`, `parameters[].flagKey` and `variationId`), metrics, attributes, hypothesis, `startDate`, `status`, previous iterations, and `resultsUrl`.
- `get-experiment-results`: summary across every metric on the iteration.
- `get-experiment-metric-results`: full statistics for one metric (`relativeDifferences`, `probabilityToBeatBaseline`, `pValue`, intervals, `dataMean`).
- `get-metrics`: with `metricKey`, returns `successCriteria` (`HigherThanBaseline` or `LowerThanBaseline`), `measureType`, `unit`, the event key, and `analysisUnits`. **You need this for every metric before you interpret it.**
- `get-metric-events`: whether a metric's event is arriving. For LaunchDarkly-hosted metrics, list recent events with `query` (the event key) and `environmentKey`, and check the key is in the list. Only warehouse metrics take `eventKey` with `dataSourceKey`.
- `get-flags`, `get-flag-health`: whether the experiment flag is on, what each rule serves, and whether it's being evaluated. The rule running the experiment is the one whose `rollout` has `experimentAllocation.type: "experiment"` (the default rule is under `fallthrough`); `experimentAllocation.defaultVariation` is the variation served to contexts outside the experiment.

**Write tools** (only inside Step 7, and only after the person confirms):
- `stop-experiment-iteration`: requires `winningTreatmentId`, `winningReason`, and `confirm: true`. **Stopping ships the winner:** LaunchDarkly serves the winning variation to every context that matches the experiment's targeting rule, and the flag's targeting updates to show it. There is no way to stop without choosing what the flag serves next.

Never call `update-experiment`, `save-and-start-experiment-iteration`, `start-experiment-iteration`, `create-*`, `update-flag-targeting`, `update-targeting-rules`, `update-rollout`, `toggle-flag`, or `start-guarded-rollout` from this skill. A new iteration goes to `launchdarkly-experiment-setup`; the optional guarded rollout goes to `launchdarkly-guarded-rollout` (see Handoffs).

## Core principles

1. **Health before results.** Results from an unhealthy experiment are artifacts. Never interpret, and never recommend a winner, until Step 2 passes.
2. **Direction comes from the metric, not from `isBest`.** `isBest` and `isSignificant` do not account for whether lower is better. Decide improvement or regression yourself from `successCriteria` and the sign of the relative difference (Step 4).
3. **Zero traffic is not a result.** With no exposures the API still returns `srmProbability: 0.5` and can mark the control `isSignificant: true`. Treat both as "no data yet."
4. **Explain, don't just report.** Every number gets a plain-language line saying what it means for this metric. Most questions about results are "what does this mean?", not "what is the number?"
5. **Show the evidence.** Every claim carries the numbers behind it, so the person can check them against the results page.
6. **The person makes the call.** You recommend one outcome with a reason. A decision from an earlier conversation does not count as confirmation.
7. **No person, no writes.** In a scheduled or automated run, or when the user has read-only access, report and recommend, and stop there.
8. **Only say what the data shows.** See "What not to make up" below.

## What not to make up

- **Numbers.** Every number you quote comes from a tool response in this conversation or from the user. Don't round a borderline result across a threshold, and don't compute a statistic the tools didn't return (a p-value for a Bayesian experiment, a lift for a metric with no data).
- **Data you can't see.** The tools don't return slices by attribute, results over time, or exposure charts. Don't describe them. Say they're on the results page and give the `resultsUrl`.
- **Business impact.** Translate a change into business terms only from what the metric's name and description say, or what the user tells you. Never invent revenue, user counts, or downstream effects. "About 6% more people finished signup" is fine; "worth about $40K a month" is not, unless the user gave you the numbers.
- **Causes.** When you explain a health failure or a surprising result, say "likeliest cause" and how to confirm it. Don't state a cause as fact.
- **Missing fields.** If a field you need isn't in the response, say it's not available. Don't fill it with a default.

## Workflow

### Step 1: Resolve the experiment (or experiments)

You need `projectKey` and `environmentKey`. Never guess either one; ask.

- **One experiment.** If the user gave a name or flag instead of a key, call `get-experiments` with `projectKey` (and `flagKey` if given) and pick the match; ask if there is more than one.
- **Several experiments** ("how are my experiments doing?", "check all running tests", the same test across sites or markets): list them with `get-experiments` and `status: running`, then use **Summary mode** below.

Call `get-experiments` with the experiment and environment keys. Note:
- `currentIteration.status`: `running`, `stopped`, or `not_started`. If `not_started`, stop and point to `launchdarkly-experiment-setup` to start it.
- **Export-only experiments.** If the methodology is `export_only`, LaunchDarkly assigns variations and exports the data, but the analysis happens in the customer's own tools. Don't report "no data." Check health (flag serving, exposures if available), say results live in their warehouse or analysis tool, and offer to interpret results they paste in.
- The control: the treatment with `baseline: true`.
- `startDate`, the hypothesis, the flag key, each treatment's `allocationPercent`, and any `attributes` (slices).

Then call `get-metrics` with `metricKey` for each metric on the iteration, in parallel. Record `successCriteria`, `measureType`, `unit`, `analysisUnits`, the event key, the data source, and which metric is primary. If a metric entry has `isGroup: true`, it's a metric group or funnel: interpret each metric in it, and for a funnel treat the last step as the outcome.

**Check the hypothesis against the primary metric.** If the hypothesis predicts one outcome (for example "more clicks") and the primary metric measures another (for example checkout conversion), point out the mismatch once, in the readout's caveats. Don't block the analysis on it.

**Understand what each metric means.** Reading "metric X went up 5%" is easy; the value is in saying what that means for the business. For each metric, use its `name` and `description` (from `get-metrics`) to write one line on what it measures in plain words, for example "the share of users who finished checkout after seeing the button." If a metric has no description and its name doesn't make the meaning clear, ask the user what it measures instead of guessing. Then note how the metrics relate: do they measure the same outcome from different angles (so they should move together), or do they trade off against each other (conversion versus page load time)? Use this in Step 4 to explain results in context, not one metric at a time.

**Spot the guardrails.** A guardrail is a metric the change shouldn't hurt, not the outcome it's trying to move. Treat secondary metrics that measure latency, load time, errors, crashes, cost, refunds, unsubscribes, or support contacts as likely guardrails, and say so: "I'm treating page load time and error rate as guardrails, meaning a regression there would block a ship. Is that right?" Use the user's answer in Step 5. If they don't answer, keep the assumption and label it in the report.

Ask whether the user has their own rules for this experiment: a minimum lift worth shipping, guardrails that block a ship, or their own health thresholds (for example "treat anything beyond 45/55 as imbalanced"). Use them where they apply and say when you did.

### Step 2: Health check

Call `get-experiment-results`. For the primary metric, and then each secondary, check in this order:

| Check | How | If it fails |
|---|---|---|
| Any exposures | `trafficCount` > 0 on every treatment; `controlHasData` is true | **No data yet.** Go to "No data" below. Do not read SRM or significance. |
| Flag serving | `get-flag-health` or `get-flags` for the flag in this environment: on, and evaluated recently | Flag off, or no recent evaluations: the SDK isn't reaching LaunchDarkly or the flag isn't on. |
| Events arriving | `get-metric-events`: for hosted metrics, list with `query` and `environmentKey` and look for the event key; for warehouse metrics, pass `eventKey` and `dataSourceKey` and check `ready` | Event not arriving: check the `track()` key (case-sensitive) and, for server SDKs, that all three service endpoints are set. |
| Sample ratio | Compare each treatment's share of `trafficCount` with its `allocationPercent`; read `srmProbability` | `srmProbability` ≤ 0.01 with real traffic, or outside the user's own threshold: **SRM.** Assignment isn't matching the design. |
| Under-counted metric | For conversion metrics, compare `conversionCount` with `analyzedUnitCount`; for any metric, compare event volume from `get-metric-events` with exposures | Events arriving but far fewer counted than expected: see "Under-counted metric" below. |
| Mixed treatments | `mixedTreatmentsDetected` | True: some units saw more than one treatment. Flag it as a caveat; investigate before shipping. |

**No data.** If the iteration started less than about 10 minutes ago, say results lag and suggest checking back. For warehouse metrics, results also wait for the next warehouse refresh. If it has been longer, the most likely causes are the flag not being evaluated or the event not arriving; report which check failed and what to fix. Never describe zero-traffic statistics.

**Abandoned experiment.** If the iteration has run for 30 days or more with no data, or with so little that nothing could be decided, say so plainly. Continuing as-is won't produce a result. Recommend either fixing the cause and keeping it running, or stopping with the control as the winner ("No data collected") so it stops showing as running.

**Evaluations aren't exposures.** If the user says the split looks wrong because flag evaluation counts don't match the allocation, explain the difference before calling it SRM. Evaluations count every time the SDK checks the flag, including contexts outside the experiment's audience and repeat checks for the same context. Exposures count each context once, in the treatment it was assigned. Judge the split on `trafficCount` only.

**SRM.** Report the planned split, the observed split, and `srmProbability`. Recommend investigating targeting, bot traffic, or code paths that skip the flag before interpreting anything. A small imbalance with a high `srmProbability` is noise; say so.

**Under-counted metric.** When events are firing but the metric shows fewer conversions than the user expects, check in this order: the event fires before the flag is evaluated for that context (so it can't be attributed); the metric's analysis unit (`analysisUnits`) doesn't match the experiment's randomization unit; the event's context key differs from the one used to evaluate the flag; the event falls outside the metric's conversion window; or, for warehouse metrics, the data hasn't been refreshed yet. Name the likeliest cause and how to confirm it.

Only continue to Step 3 if every treatment has traffic and there is no SRM.

### Step 3: Readiness

Before interpreting, check that the data can support a call:

- **Runtime.** Days since `startDate`. Under 7 days, warn about day-of-week effects. Under 14 days, warn about novelty effects for anything users see.
- **Metric window.** If a metric only counts conversions within a window after exposure, the iteration needs to have run at least that long for recent units to count.
- **Sample.** `analyzedUnitCount` per treatment. Very small counts (tens, not thousands) mean wide intervals; say so rather than reading the point estimate.
- **Methodology.** `methodology` is `bayesian` or `frequentist`. Use only the statistic for that methodology. For frequentist experiments, note whether sequential testing is on; if you can't tell, treat the design as fixed horizon.

**Early peeking.** Looking at results early is fine; deciding early is what causes false wins. Follow LaunchDarkly's guidance for each design before Step 5:

| Design | When a ship or keep-control call is allowed (LaunchDarkly guidance) |
|---|---|
| Frequentist, fixed horizon (the default) | Only once the planned sample size is reached. "You may look at the results ahead of time, but you should not make decisions until your pre-determined sample size is hit." Before that, show the current estimate as preliminary and don't call significance. |
| Frequentist, sequential | Any time; sequential results are valid whenever you check. They're more conservative, so they may take longer to reach significance. If less than a full week has run, mention that weekly patterns may not be in the data yet, but don't block the call. |
| Bayesian | After at least one week, LaunchDarkly's general recommendation. The results page also shows a sample size estimate of how much more traffic is needed to reach the chosen threshold; point the person to it. |

Until a call is allowed, label the report **Early read, not a decision**, show the direction and interval as preliminary, and say when a call will be possible (the planned sample or end date, or the date one full week is reached).

**One exception: stopping for harm.** If a treatment shows a clear regression on the primary metric or a guardrail early on, the person may reasonably stop it to protect users without waiting. Recommend Stop and ship the control, say the result is early, and leave the call to them.

If the person wants to ship early anyway, say plainly what the risk is (the lift may be smaller than it looks, or not real), then respect their decision.

### Step 4: Interpret each metric, with direction

For every metric, call `get-experiment-metric-results` (in parallel). For each non-control treatment, use the entry in `statistics.relativeDifferences` whose `fromTreatmentId` is the **control's** `treatmentId`. That is the treatment's change relative to control. Values are fractions (0.07 means +7%), and the sign follows the raw numbers: positive means the treatment's value is higher than control's, whether or not higher is better. Ignore the control's own `isSignificant`; the API marks the control significant even with no data.

Classify each treatment on each metric:

| `successCriteria` | Interval (`lower`, `upper`) | Verdict |
|---|---|---|
| `HigherThanBaseline` | `lower` > 0 and the treatment is significant | **Improvement** |
| `HigherThanBaseline` | `upper` < 0 and the treatment is significant | **Regression** |
| `LowerThanBaseline` | `upper` < 0 and the treatment is significant | **Improvement** (it went down, which is good) |
| `LowerThanBaseline` | `lower` > 0 and the treatment is significant | **Regression** (it went up, which is bad) |
| either | interval spans 0, or not significant | **No clear difference** |

"Significant" means `pValue` below the experiment's significance level (frequentist, 0.05 by default), or, for Bayesian, `probabilityToBeatBaseline` past the experiment's threshold (90% by default). Both Bayesian probabilities follow the metric's success direction: for a `LowerThanBaseline` metric, probability to beat baseline is the chance the treatment is *lower* than control. When there are several treatments, use `probabilityToBeBest` to choose among them; that's how LaunchDarkly declares a Bayesian winning variation. If the interval and the probability point in different directions, report both and classify as **No clear difference**; never resolve the conflict by trusting `isBest`.

**Never switch off the safeguards to get a result.** The results tools accept `disableMultipleComparisonCorrection` and `disableSequentialTesting`. Don't use either to make a result look significant. If the person asks what the result would be without them, show it labeled as exploratory, next to the real result.

Bayesian results in LaunchDarkly shrink treatments toward the control by default (informative priors), so the modeled change is usually smaller than the raw one. For example, raw rates of 34% and 37% (a +10.7% raw difference) can show as +7% on the results page. If the person compares the page with raw counts, explain this, using `dataMean` for the raw rate and `statistics.mean` for the modeled one.

**Say what it means.** For each metric, write one plain-language line: "Page load time went **down** 8% (95% interval −12% to −4%). Lower is better, so the new version is faster, and we're confident it isn't chance." For **No clear difference**, say what the interval rules out: "Signups changed by somewhere between −2% and +3%, so if there's an effect, it's small."

**Put results in context.** Use the metric meanings from Step 1. When related metrics move together, say it strengthens the result ("signups and activation both rose, so people aren't just signing up and leaving"). When they trade off, present both sides together. When a secondary metric moved but the primary didn't, say what that might mean, labeled as a possibility.

**Explain apparent contradictions.** If the user asks why numbers disagree, check these before assuming a bug:
- **Raw rate versus relative difference.** A treatment's raw conversion rate can look higher while the relative difference is negative or not significant. Common reasons: variance reduction (CUPED) adjusts for pre-experiment behavior, so the adjusted estimate differs from the raw rate; the raw numbers are totals while the analysis is per unit; or a few heavy users drive the raw total.
- **Color or label on the results page.** Red or green reflects the metric's success direction and significance together. Restate it in words: which way it moved, whether that's good, and how sure we are.
- **Primary up, secondary down.** That's a trade-off, not an error. Show both.

**Review in LaunchDarkly.** After the interpretation, always give the `resultsUrl` so the person can check the numbers, charts and exposures on the results page themselves: "Review the full results in LaunchDarkly: <resultsUrl>".

**Slices.** If the experiment has `attributes` configured, tell the user they can see where the effect is strongest (for example mobile versus desktop) on the results page, and give the `resultsUrl`. The results tools don't return breakdowns by attribute, so don't describe slice results you haven't seen. If the user pastes slice results, interpret them with the same direction rules, and warn that LaunchDarkly doesn't apply CUPED, multiple comparisons correction, or sequential testing to sliced results, so they're ideas for the next test, not conclusions.

### Special cases

Check these before recommending anything:

| Situation | How to tell | What to do |
|---|---|---|
| **Instrumentation metric** | A metric that fires in only one arm (for example "receipt shown": 0 in control, 72 of 83 in treatment) | It's a check that the change rendered, not an outcome. Don't call it an improvement. Use it to say how many treated units actually saw the change (72 of 83 = 87%); if many didn't, the effect on the outcome is diluted. |
| **One metric has no data** | That metric has `trafficCount` 0 or `controlHasData: false` while the primary has traffic | Report "no data yet" for that metric only and check its event. Don't fail the whole experiment's health check. |
| **Duplicate metrics** | Two metrics show identical counts in every arm | Say they may measure the same event, and count them once. |
| **Control mean is zero** (frequentist) | The control's mean is 0 | LaunchDarkly can't compute a relative difference, interval, or p-value ("N/A" on the results page). Compare the raw rates or counts instead and say no relative lift is available. |
| **Percentile metric** (for example p95 latency) | The metric's `analysisType` is a percentile | Only frequentist experiments with sequential testing can use these. LaunchDarkly uses a conservative test, so a real difference can take longer to show. CUPED doesn't apply. |
| **CUPED on** | The results page or experiment settings show CUPED | It applies only to mean metrics, uses pre-experiment behavior to narrow intervals, and makes the adjusted estimate differ from the raw rate. Explain this if the numbers don't match the raw counts. |
| **Multiple comparisons correction on** (frequentist) | Bonferroni or Benjamini-Hochberg across treatments, metrics, or both | Significance is stricter, by design, to cut false wins from comparing many things. Don't treat a result as significant without it. |
| **Outliers or extreme values** | A mean metric whose spread (`dataStdDev`) is many times its mean, or a lift driven by a few heavy users | Bayesian results already dampen outliers through priors based on the control. For a frequentist mean metric, suggest checking whether the metric uses winsorization (capping extreme values at a percentile). |
| **Slices** | The person looks at results filtered by an attribute | LaunchDarkly doesn't apply CUPED, multiple comparisons correction, or sequential testing to filtered results. Treat slices as ideas for the next test, never as the basis for a ship decision. |
| **Multi-armed bandit** | The experiment is a multi-armed bandit (the person says so, or the results page shows it) | Don't apply this skill's A/B rules. A bandit shifts traffic toward the leader on purpose, so an uneven split isn't SRM, and contexts can see different variations over time. There's nothing to ship by hand. LaunchDarkly recommends stopping when one variation's probability to be best reaches 99% or more, or when a time-boxed promotion ends. |
| **Not enough traffic to decide** | Four or more weeks in, the interval still spans large effects in both directions (for example −34% to +48%) | Keeping it running won't settle it in a reasonable time. Say so, and recommend either keeping the control or redesigning with a larger audience or a metric that moves more often. |

### Step 5: Recommend one outcome

Evaluate in this order and stop at the first that applies:

1. **Investigate.** Step 2 failed (no data, SRM, flag not serving, under-counted metric). Recommend fixing the cause. Don't recommend stopping with a winner, except for an abandoned experiment (see Step 2), where stopping with the control is a valid choice.
2. **Don't ship: regression.** Any treatment regressed on the primary metric, or on a guardrail (confirmed by the user, or flagged as likely in Step 1). If the same treatment improved the primary, present it as a trade-off for the person to decide, with both numbers. Never call it a clean win.
Recommendations 3 and 5 below need the early-peeking rules in Step 3 to allow a call. If they don't yet, recommend Keep running and label the report an early read.

3. **Ship treatment.** One treatment improved the primary metric, with no regressions on any secondary metric. If several improved, recommend the one with the largest improvement and name the runner-up. If the user set a minimum lift, say whether the result clears it; if they didn't, ask whether the size of the improvement is worth shipping for them.
4. **Keep running.** No clear difference yet, and the experiment hasn't reached its planned duration or sample. **Always give a time estimate**: exposures per day so far, and roughly how many more days the current interval width suggests are needed to detect an effect the size the user cares about. Label it an estimate and say what would change it (traffic, effect size).
5. **Keep control.** No clear difference and the experiment has run its planned course, or there isn't enough traffic to decide (see Special cases). A clear null result is a valid outcome: the change didn't move the metric enough to matter.
6. **Iterate.** The result points to a better next test (a slice where the effect looks strongest, a secondary metric that moved, a change that was too small). Recommend a new iteration and hand off to `launchdarkly-experiment-setup`.

Map the recommendation to one of the three decisions in Step 7, and say in plain words what it would do:

| Recommendation | Decision in Step 7 |
|---|---|
| Ship treatment | Stop and ship that treatment |
| Keep control, Don't ship: regression | Stop and ship the control |
| Iterate | Edit the design and start a new iteration |
| Keep running, Investigate | Keep running (no writes) |

Present it with the evidence, using the output format below.

**Offer what's next.** End the first summary with a short list of follow-ups the person can ask for, choosing the ones that fit this experiment. For example:
- See one metric in full detail (intervals, means, counts per treatment)
- Compare this iteration with the previous one (if `previousIterations` exists)
- Check health in more depth (events, exposures, flag evaluations)
- Get a stakeholder summary or a JSON export
- See slices or results over time on the results page (link it; the tools don't return these)
- Make the call: stop and ship, edit and start a new iteration, or keep running

Keep the first summary short and let them pull more.

### Step 6: Summary mode (several experiments)

For a set of experiments, run Steps 2 to 5 for each, but report one line per experiment instead of the full format:

| Experiment | Days running | Health | Primary metric (vs control) | Recommendation |
|---|---|---|---|---|

Order by what needs attention: failed health checks first, then experiments ready for a call, then ones still running. For the same test run across sites or markets, add a line on whether the results agree. Offer the full analysis for any row.

### Step 7: Decide and act, only with confirmation

Skip the writes in this step in a scheduled or automated run with no person replying, or when the user has read-only access. Report the recommendation and the choice the person would need to confirm.

Ask the person to choose one of the same three options the LaunchDarkly UI offers, with your recommendation marked:

1. **Stop and ship a variation.** Pick the variation to ship: the control or any treatment. It's recorded as the winner, data collection ends, and the flag serves that variation to everyone the experiment rule covered.
2. **Edit the design and start a new iteration.** Data collection for this iteration ends and a new iteration starts with the changes (for example new treatments, metrics, allocation, or audience).
3. **Keep running.** Nothing changes.

#### Option 1: Stop and ship a variation

This is one action, the same as the UI's Stop and Ship: the variation chosen as the winner is what everyone in the experiment's rule gets from then on.

1. **Read the flag.** Call `get-flags` with `flagKey` and `env`. The experiment rule is the one whose `rollout.experimentAllocation.type` is `"experiment"`: either `fallthrough` (the default rule) or an entry in `rules`. Note the flag's on/off state, what every rule serves, and the current split. If no rule has that marker, or more than one does, ask.
2. **Show exactly what will happen and wait for a yes:**

```
Stop and ship: <experiment name>
  Winner: <variation name> (<treatmentId>)
  Reason: <one line, e.g. "Short form raised signup completion 6% (2% to 10%), no guardrail regressions">
  What changes for users: everyone matching <rule name, or "the default rule"> of <flagKey> in <env>
    Before: <current split, e.g. "50% Long form / 50% Short form">
    After:  100% <variation name>, starting now
  <If the winner is a treatment:> People who were seeing <control name> switch to <variation name>.
  <If the winner is the control:> People who were seeing <treatment names> switch back to <control name>.
  Data collection for this iteration ends; results stay available.
Confirm?
```

3. After the person confirms this exact winner in this conversation, call `stop-experiment-iteration` with `winningTreatmentId`, `winningReason`, and `confirm: true`.
4. **Verify.** Call `get-flags` and `get-experiments`. Confirm the iteration is `stopped` with the right winner and the rule now serves that variation. Report before and after. If the rule doesn't serve the winner, say so and give the flag's targeting page; don't change the flag yourself.
5. After a treatment ships, offer flag cleanup once things are stable: the flag and the losing code path can be removed. Hand off to `launchdarkly-flag-cleanup`.

#### Optional: ship a treatment gradually with a guarded rollout

Only offer this if the person asks to ship gradually, or asks how to reduce the risk of shipping a treatment. Don't recommend it by default. Before they choose it, explain plainly what happens to users, because it isn't the same as Option 1:

```
Shipping <treatment> with a guarded rollout instead of all at once:

1. First, the experiment stops with <control name> as the recorded winner. That's required:
   stopping with <treatment> would send it to everyone immediately.
   → Everyone who was seeing <treatment> in the experiment goes back to <control name> right away.
   → The experiment's record will show <control name> as the winner. The reason will say
     "Shipping <treatment> via guarded rollout" so the real decision is clear.

2. Then a guarded rollout starts moving people from <control name> to <treatment> in stages
   (for example 10%, then 25%, then 50%). Each stage is capped at 50%.
   → At each stage, LaunchDarkly watches the metrics you pick and automatically rolls back
     to <control name> if one gets worse.
   → The rollout doesn't reuse the experiment's assignments. It picks its own users at each
     stage, so the people who get <treatment> aren't the same people who saw it in the
     experiment, and some users will switch experiences more than once.
   → When the last stage finishes cleanly, everyone gets <treatment>.

3. If anything regresses during the rollout, everyone goes back to <control name>.
```

If they still want it, confirm the stop with the control as the winner (using the Option 1 preview, with the reason above), stop the iteration, verify the flag serves the control, then hand off to `launchdarkly-guarded-rollout` with the flag key, environment, rule, control and treatment variation ids, randomization unit, and the experiment's primary and guardrail metric keys. Guarded rollouts may not be available on every plan; if the handoff reports that, say so and offer Option 1.

#### Option 2: Edit the design and start a new iteration

1. Agree on what changes and why, based on what this iteration showed (for example drop a treatment that regressed, add a guardrail metric, rebalance allocation, narrow the audience).
2. Hand off to `launchdarkly-experiment-setup` with the experiment key, environment, the exact field changes, and a one-line `changeJustification`. Setup shows the new design and calls `save-and-start-experiment-iteration` only after the person explicitly says to start, which stops this iteration and starts the new one in one step.
3. After it starts, check back with this skill on the new iteration.

#### Option 3: Keep running

Make no writes. Say when to check back, using the time estimate from Step 5.

#### Rules for every option

- LaunchDarkly requires a winner to stop. If the result was inconclusive, the winner is the control and the reason says so ("Inconclusive, keeping control").
- A confirmation covers only the exact winner and ship plan you showed. A decision from an earlier conversation doesn't count. "No" means no writes; say that nothing changed.
- If a write fails with a permission or approval error, the environment probably requires approvals. Explain that the change must be done or approved in LaunchDarkly by someone with access, give the `resultsUrl`, and don't retry.
- If the experiment uses a holdout, say that stopping this iteration doesn't release the holdout's users; the holdout is managed separately.

### Step 8: Readout and next experiment

Finish with a readout. Ask which format they need, or default to the Slack readout:
- **Slack or doc readout**: hypothesis, what happened, decision, caveats, next step.
- **Stakeholder summary**: decision first, in business terms, no statistics vocabulary.
- **JSON**: one object per experiment for BI tools, notebooks, or another agent.

Templates for all three are in [references/readout-template.md](references/readout-template.md).

Always end the readout with the results page link and say that a PDF of the results can be downloaded from that page in LaunchDarkly, for sharing with people who don't use LaunchDarkly: "Download a PDF of the full results: <resultsUrl>".

Suggest one follow-up experiment based on what was learned (for example, the slice where the effect looked strongest, or the secondary metric that moved). Offer to hand the idea to `launchdarkly-experiment-hypothesis-builder`.

## Output format

Every single-experiment analysis starts with **one status label**, so the person knows where the experiment stands before reading any number:

| Status | When |
|---|---|
| **No data yet** | No exposures, or results haven't landed (Step 2) |
| **Needs attention** | A health check failed: SRM, flag not serving, events missing or under-counted |
| **Collecting data (~N days left)** | Healthy, but the early-peeking rules don't allow a call yet |
| **Stop for harm?** | A clear early regression on the primary metric or a guardrail |
| **Ready for a call** | Healthy, and the early-peeking rules allow a decision |
| **Abandoned** | 30+ days with no usable data |

Then use these sections, in order:

```
## <Experiment name>: <status label>

**Health:** <pass, or what failed and the likeliest cause>
**Progress:** day <D> of <planned duration, or the 7-day minimum> · <units per treatment> · <methodology, and fixed horizon or sequential>
  <If not ready: "A call is possible from <date>." Say the estimate is rough this early.>

**Results** (vs <control name>)<", early read, not a decision" if not ready>
| Metric | Good direction | Change | Interval | Verdict |
|---|---|---|---|---|
| <primary> (primary) | Higher / Lower | +X% | [a%, b%] | Improvement / Regression / No clear difference / Leaning better / Leaning worse |
| <guardrail> (guardrail) | ... | ... | ... | ... |

**What this means:** <one or two plain sentences per metric that matters>

**Recommendation:** <Ship treatment / Keep running (~N more days) / Keep control / Iterate / Don't ship / Investigate>
<Two or three sentences on why, with the numbers, and what acting on it would do.>

**Next step:** <the one action to take, and whether it needs their confirmation>
**You can also ask me to:** <two to four follow-ups from Step 5>
Review the full results in LaunchDarkly: <resultsUrl>
```

Rules for what to show at each stage:
- **No data yet, Needs attention, Abandoned:** leave out the results table. Numbers from an unhealthy or empty experiment mislead.
- **Collecting data:** show the table, but use **Leaning better** or **Leaning worse** for the verdict instead of Improvement or Regression, and say it's directional. If a treatment has very few units (as a rule of thumb, under about 100 units or 25 conversions per treatment), show "Too few to read" instead of a percentage.
- **Early lifts fade.** When a large lift shows up in the first week or two, mention that early effects often shrink as novelty wears off. Be extra skeptical of lifts above about 30%: check the health checks again before believing them.

## Common mistakes

- **Trusting `isBest`.** It can mark a regression as best when lower is better. Always classify with `successCriteria`.
- **Reading zero-traffic statistics.** `srmProbability: 0.5` and a "significant" control with no traffic mean nothing. Report no data.
- **Calling an evaluation imbalance SRM.** Flag evaluation counts aren't exposures. Judge the split on `trafficCount`.
- **Calling a trend a winner.** A treatment that leads but isn't significant hasn't won. Say "leading, not yet clear."
- **Deciding on an early read.** A result that crossed the threshold on day 3 isn't a decision. Follow the early-peeking rules.
- **Ignoring secondary metrics.** A primary win with a significant regression elsewhere is a trade-off, not a win.
- **Reading metrics in isolation.** Say what each metric measures and how the metrics relate. A number without its meaning isn't an analysis.
- **Inventing business impact.** Translate into business terms only from the metric's description or numbers the user gave you.
- **Mixing methodologies.** Don't quote a p-value for a Bayesian experiment or a probability to beat baseline for a frequentist one.
- **Treating stop as only a label.** Stopping ships the winner to everyone in the experiment's rule. Always show who switches to what before asking for a yes.
- **Stopping with a treatment before a guarded rollout.** That ships it to everyone at once and skips the gradual rollout. The guarded path stops with the control.
- **Writing without a person.** Scheduled runs and read-only users get a recommendation, never a stop, ship, or new iteration.
- **Stopping without a fresh yes.** Every stop needs confirmation of the specific winner in the current conversation.

## Handoffs

| When | Hand off to | Pass along |
|---|---|---|
| Experiment not started, or Option 2: edit the design and start a new iteration | `launchdarkly-experiment-setup` | Experiment key, environment, the field changes, and a `changeJustification` |
| Optional guarded rollout of a treatment | `launchdarkly-guarded-rollout` | Flag key, environment, control and winner variation IDs, primary and guardrail metric keys |
| Restore a flag the person didn't mean to change | `launchdarkly-flag-targeting` | Flag key, environment, and the before-and-after flag state |
| Next experiment idea | `launchdarkly-experiment-hypothesis-builder` | The draft idea and what this experiment learned |
| Metric event not arriving or under-counted | `launchdarkly-metric-instrument` | Metric key, event key, and the likeliest cause from Step 2 |
| Winner shipped to everyone and stable | `launchdarkly-flag-cleanup` | Flag key, environment, the shipped variation |

If a skill isn't available, give the person the same details so they can do it in LaunchDarkly.
