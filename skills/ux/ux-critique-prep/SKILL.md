---
name: ux-critique-prep
description: Prepare work for a LaunchDarkly design critique session. Use when a designer or PM wants to frame their work for feedback, write a critique brief, or check they've thought through what they need from a session before bringing it to the room.
---

# Critique Preparation

Help the user prepare a critique brief for a LaunchDarkly design critique session.

## Step 1: Collect context

Ask the user these questions. You can ask all at once. If they've already answered some in their initial message, skip those.

1. What are you bringing to critique? (Brief description of the work)
2. What stage is it?
   - Problem framing (rough sketches, concept, written brief)
   - In progress (wireframes, flows, mid-fidelity)
   - Near-final (high-fidelity, pre-handoff)
   - Pre-ship (final implementation)
3. What is the user need or business goal this work is responding to?
4. What specific decisions are you uncertain about, or what feedback are you looking for?
5. What have you already decided and don't want relitigated in this session?

If the user shares a Figma link, use the Figma MCP (`figma_get_file_data` or `figma_get_selection`) to review the actual work before generating the brief. If they share screenshots, analyze those directly.

## Step 2: Preliminary quality scan

Before writing the brief, do a quick check against the six LD quality criteria. For each, note whether it's addressed, partially addressed, has a clear gap, or can't be assessed from what was shared.

| Criterion | What to check |
|---|---|
| Clarity | Can a user understand what this is and what to do without help? Are labels, status, and empty states clear? |
| Utility | Does the flow match how users actually work? Does it solve the real problem? |
| Integrity | Are error states, loading states, empty states, and edge cases handled? |
| Consistency | Does it use LaunchPad components and consistent LD terminology? |
| Accessibility | WCAG 2.1 AA contrast, keyboard nav, focus states, no color-only status signals? |
| Connectedness | Does it connect naturally to what the user does before and after this step? |

If a gap is obvious, flag it in the brief so reviewers know to focus there. If you can't assess a criterion from what was shared, say so. Don't invent findings.

For work built with AI tools (Lovable, v0, Figma Make): pay extra attention to Integrity. AI-generated prototypes typically only show the happy path.

## Step 3: Generate the critique brief

Produce a brief the user can share before the session — in a Figma comment, Slack message, or calendar invite. It should take two minutes to read.

```
## Critique Brief: [Work Name]

**Stage:** [Stage]

**The problem:** [What user need or business goal this is responding to]

**What I'm looking for:** [Specific questions or decisions that need feedback]

**What's already decided:** [Things not up for discussion in this session]

**Known gaps / heads up:** [Any criteria that are incomplete — be honest; this helps reviewers focus]
```

If the "Known gaps" section is empty after the quality scan, say so — it's useful signal.

## What good looks like

A well-prepared critique brief does three things: it tells reviewers what the work is trying to do (so they can evaluate utility), it tells them what the presenter needs (so feedback is targeted), and it names what's already off the table (so the session doesn't relitigate settled decisions).

## Related

- Run `/ux-quality-check` for a full criterion-by-criterion review before generating the brief
- [Critique Engagement and Etiquette](https://launchdarkly.atlassian.net/wiki/spaces/PD/pages/4714659904/Design+Critique+Engagement+and+Etiquette) — stage guide, failure modes, how to give and receive feedback
- [UX Quality Standards](https://launchdarkly.atlassian.net/wiki/spaces/PD/pages/4714201182/LaunchDarkly+UX+Quality+Standards) — full definitions of the six criteria
