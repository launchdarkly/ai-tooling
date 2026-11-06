# Experiment readout templates

Use these at the end of an analysis, after the decision is made. Fill every line from the analysis; leave a line out instead of guessing.

## Slack or doc readout (default)

Short enough to paste into a channel.

```
**<Experiment name>**: <Decision> (<date>)

**Hypothesis:** <the iteration's hypothesis, as written>

**What happened**
- <Primary metric>: <treatment> <went up / went down> <X%> vs <control> (interval <a%> to <b%>). <Higher / Lower> is better, so this is <an improvement / a regression / no clear difference>.
- <Secondary metric>: <same format, one line each; say "no clear difference" when the interval spans zero>

**Decision:** <Ship <treatment> / Keep control / Keep running / Iterate>, because <one sentence>.

**Data:** <N> units per treatment over <D> days, <Bayesian / frequentist>. <Any caveat: short runtime, novelty, mixed treatments, a trade-off the team accepted.>

**Next:** <the rollout plan for the winner, or the follow-up experiment to run>

Full results: <resultsUrl> (download a PDF from the results page to share outside LaunchDarkly)
```

## Stakeholder summary

For leaders and marketing or business partners. Decision first, business terms, no statistics vocabulary (no "p-value," "credible interval," "significant"). Use "we're confident" or "too close to call" instead.

```
**<Experiment name>: <decision in plain words, e.g. "We're shipping the shorter signup form">**

<One sentence on what we tested and why it mattered to the business.>

<One sentence on the result, in the metric's own terms: "About 6% more people finished signing up, with no slowdown in page load.">

<One sentence on what happens next and when.>

Full results (PDF download available): <resultsUrl>
```

## JSON (BI tools, notebooks, other agents)

One object per experiment. Use `null` for anything you didn't check; never invent values. Percentages are numbers (6.2 means 6.2%).

```json
{
  "projectKey": "string",
  "environmentKey": "string",
  "experimentKey": "string",
  "iterationId": "string",
  "analyzedAt": "ISO 8601 UTC",
  "daysRunning": 0,
  "methodology": "bayesian | frequentist",
  "health": {
    "status": "pass | no_data | srm | flag_not_serving | under_counted | mixed_treatments",
    "detail": "string"
  },
  "control": { "treatmentId": "string", "name": "string", "units": 0 },
  "metrics": [
    {
      "metricKey": "string",
      "isPrimary": true,
      "goodDirection": "higher | lower",
      "treatments": [
        {
          "treatmentId": "string",
          "name": "string",
          "units": 0,
          "relativeChangePercent": 0,
          "intervalPercent": [0, 0],
          "probabilityToBeatBaseline": null,
          "pValue": null,
          "verdict": "improvement | regression | no_clear_difference"
        }
      ]
    }
  ],
  "recommendation": "ship | keep_running | keep_control | iterate | dont_ship | investigate",
  "recommendedTreatmentId": null,
  "estimatedDaysRemaining": null,
  "reason": "string",
  "resultsUrl": "string"
}
```

## Writing the lines

- Name the direction in words ("went down 8%") and say whether that is good for this metric. Readers shouldn't have to know which way is better.
- Quote the interval with the estimate in the Slack readout. A point estimate alone overstates certainty.
- For a null result, say what was learned: "The new copy didn't change signups by more than about 3% either way, so we're keeping the current version."
- For a trade-off, state both sides and who accepted it: "Checkout completion rose 4%, page load time rose 6%; the team accepted the slower load for now."
