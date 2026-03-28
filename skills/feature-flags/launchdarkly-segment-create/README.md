# LaunchDarkly Segment Create Skill

An Agent Skill for creating and managing reusable audience segments in LaunchDarkly, so teams define targeting criteria once and reuse them across multiple feature flags.

## Overview

This skill teaches agents how to:
- Check for existing segments before creating duplicates
- Choose the right segment type: rule-based (attribute matching) vs list-based (explicit keys)
- Create a segment in a specific environment with the right key, name, and tags
- Configure segment membership via targeting rules or individual context targets
- Wire a segment into a feature flag's targeting rules using the `segmentMatch` operator

## Usage

Once installed, the skill activates when you ask about segments:

```
Create a beta-testers segment in staging for users whose email ends in @example.com
```

```
Add the enterprise-accounts segment to the new-dashboard flag so enterprise users get the true variation
```

```
Set up an internal-qa segment in production with these specific user keys: [key1, key2, key3]
```

## Structure

```
launchdarkly-segment-create/
├── SKILL.md
├── README.md
└── references/
    ├── segment-types.md
    └── segment-rule-patterns.md
```

## Related

- [LaunchDarkly Flag Targeting](../launchdarkly-flag-targeting/) — Wire segments into flag targeting rules after creating them
- [LaunchDarkly Flag Create](../launchdarkly-flag-create/) — Create the flags that segments will be wired into
- [LaunchDarkly MCP Server](https://github.com/launchdarkly/mcp-server)
- [LaunchDarkly Segments Docs](https://launchdarkly.com/docs/home/flags/segments)

## License

Apache-2.0
