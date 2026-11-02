# Supplying LaunchDarkly flag state

Some of the check's questions are about flags that already exist: is the
code around the change behind a flag that's still off for real users? Is
there an existing flag this change should reuse? Those are answered
mechanically from each flag's current state in LaunchDarkly.

- **With `LAUNCHDARKLY_API_KEY` set** (a read-only API access token),
  `ld-factory.pyz` reads LaunchDarkly itself. Nothing to do here.
- **Otherwise** `ld-factory.pyz` exits 7 and lists the flags it needs in
  `RUN/launchdarkly-needed.txt`, one `<project>  <key>` per line, with the
  environments to read. Fetch each with whatever LaunchDarkly tools you have
  and write it as below, then run the same command again. It may ask for a
  few more on the next run (a flag's prerequisites, or a flag an answer
  pointed at); repeat until it stops asking.
- **No way to read LaunchDarkly at all:** run again with
  `--no-launchdarkly`. Questions about flag state then come back unclear,
  which sends the result to a person only when it depends on them.

## The project's environments

When the repo's profile doesn't say which environments serve real users
(a profile derived from the repo never does), the check uses the ones
LaunchDarkly marks **critical**: of those, the ones with `prod` in their key
when there are any (a critical environment that isn't, such as a dogfood
instance, is still read but doesn't count as real users), else all of them. With an API key it lists them itself.
Otherwise the first `launchdarkly-needed.txt` asks for them too: list the
project's environments with your LaunchDarkly tools and write
`RUN/launchdarkly/environments.json`, every environment with its key and
whether it's critical:

```json
[{"key": "production", "critical": true},
 {"key": "eu-production", "critical": true},
 {"key": "staging", "critical": false}]
```

Then fetch each flag in every environment marked critical. Without either,
flag state is read in `production` only, and the report says so.

## The file

One file per flag: `RUN/launchdarkly/<project>__<key>.json` (two
underscores), in the shape of LaunchDarkly's REST API
`GET /api/v2/flags/{project}/{key}`. Only these fields are read; include
every environment listed in `launchdarkly-needed.txt` that the flag has:

```json
{
  "key": "new-checkout",
  "archived": false,
  "variations": [{"value": true}, {"value": false}],
  "environments": {
    "production": {
      "on": true,
      "offVariation": 1,
      "fallthrough": {"rollout": {"variations": [
        {"variation": 0, "weight": 10000},
        {"variation": 1, "weight": 90000}]}},
      "rules": [
        {"variation": 0,
         "clauses": [{"op": "segmentMatch", "values": ["internal-staff"], "negate": false}]}
      ],
      "targets": [{"variation": 0, "values": ["user-123"]}],
      "contextTargets": [],
      "prerequisites": [{"key": "checkout-platform", "variation": 0}]
    }
  }
}
```

- **Variations are indexes** into `variations`, everywhere: `offVariation`,
  `fallthrough.variation`, a rule's `variation`, a target's `variation`, a
  prerequisite's `variation`. If your tool reports variation *values* or
  names, convert each to its index.
- **Fallthrough and rules** have either `"variation": <index>` or
  `"rollout": {"variations": [{"variation": <index>, "weight": <w>}]}`, with
  weights out of 100000 (a 10% rollout is 10000).
- **Rules:** keep every clause; `op`, `values` and `negate` are what's read.
  A rule targeting only internal audiences (segments named like `internal`
  or `staff`) counts as not reaching real users.
- **A flag that doesn't exist** in that project:
  `{"key": "<key>", "not_found": true}`. Don't guess at another project.
- **An environment the flag doesn't have:** leave it out.
- Write what the tool returned. Never fill in a field you didn't read: a
  missing field reads as "unknown", which is safe; an invented one is not.

## Where to get it

- **LaunchDarkly's REST API**, if you have a token but it isn't in the
  environment:
  `curl -s -H "Authorization: $TOKEN" <instance>/api/v2/flags/<project>/<key>`,
  with the instance `launchdarkly-needed.txt` names, returns this shape
  already (keep the whole response).
- **A LaunchDarkly MCP server or other tool** that reads a flag's targeting
  per environment: one call per flag and environment, assembled into the
  shape above. Check that the project key you pass is the one the needed
  file names.
