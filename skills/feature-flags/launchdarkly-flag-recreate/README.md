# LaunchDarkly Flag Recreate

Recreate a misconfigured feature flag when the key or variation type was set incorrectly. Flag keys and variation kinds are immutable after creation — this skill guides the agent through creating a correct replacement, migrating targeting across environments, and archiving the old flag.

## When to Use

- Flag key has a typo
- Flag was created as boolean but should be multivariate (or vice versa)
- Variation values are wrong and can't be corrected

## How It Works

See [SKILL.md](SKILL.md) for the full workflow.
