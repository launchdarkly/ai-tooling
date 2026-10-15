# Copy-paste prompt

This is the discoverable, copy-pasteable prompt surfaced in the LaunchDarkly UI.
A user copies it and pastes it into their local coding agent (Claude Code,
Cursor, etc.) with this skill installed. It carries zero assumptions about what
the user already knows.

---

## Prompt (copy everything below)

```
I want to run an experiment (A/B test) in my product using LaunchDarkly, but I'm
not sure where to start — I may not have a hypothesis, a metric, or a flag yet.

Please guide me end to end using the launchdarkly-experiment-guide skill:
1. Look at my codebase and recent git history and tell me what you think my
   product is and what I've been working on lately.
2. Check my connected LaunchDarkly account for flags and metrics I can reuse.
3. Suggest one thing worth experimenting on, and propose a hypothesis and a
   metric for it (with an example) — don't make me come up with them cold.
4. Give me any flag or tracking code I need to add.
5. Draft the full experiment and ask me before creating anything.

Go ahead and start with step 1.
```

---

## Shorter variant

```
Use the launchdarkly-experiment-guide skill to help me set up my first
LaunchDarkly experiment. Start by scanning my codebase to figure out what to
test and suggest a hypothesis and metric — I don't have one yet.
```

## Notes for whoever wires this into the UI

- `PROMPT.md` is a proposed convention (no prior UI-prompt artifact existed in
  this repo). Adjust the format to whatever the UI surface actually renders.
- The prompt intentionally names the skill so description-based activation is
  reliable; drop the name if the UI auto-attaches the skill.
