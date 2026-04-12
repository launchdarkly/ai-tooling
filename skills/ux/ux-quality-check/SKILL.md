---
name: ux-quality-check
description: Check design, research, or content work against LaunchDarkly's six quality criteria (Clarity, Utility, Integrity, Consistency, Accessibility, Connectedness). Use when a designer or PM wants to evaluate work before critique, before handoff, or before shipping.
---

# Quality Check

Evaluate work against LaunchDarkly's six quality criteria.

## Step 1: Collect the work

Ask the user to share what they're evaluating. Accept any of these:

- A Figma link → use the Figma MCP to read the file (`figma_get_file_data`, `figma_get_selection`, or `figma_capture_screenshot` for visual review)
- A prototype URL → fetch and analyze
- Screenshots → analyze directly
- A written spec, PRD section, or description → work from that

Also ask: who is the primary audience for this feature? (Developer, admin, PM, business stakeholder — this affects how you evaluate Clarity and Utility in a B2B developer tooling product.)

If no work is shared, ask before proceeding. The review is only as useful as what it's based on.

## Step 2: Evaluate each criterion

Work through each criterion in order. For each, produce a specific finding — name what you observed, not what you felt. Vague findings ("could be clearer") aren't useful. Specific ones are ("the empty state for the environments list has no call to action and no explanation of what to do next").

Use this scale:
- ✓ Addressed
- ⚠ Partial — some evidence but gaps remain
- ✗ Gap — not addressed or clearly failing
- ? Can't assess — not enough information in what was shared

### 1. Clarity
Can a user understand what this is, what it does, and what to do — without being told?

Check: labels are unambiguous and accurate, hierarchy guides the eye to the primary action, status is always visible, empty states explain next steps, error messages name what happened and what to do next.

For developer tooling: precision matters more than warmth. An error message that is vague but friendly is worse than one that is exact but neutral.

### 2. Utility
Does it solve the actual problem the user has?

Check: does the flow match how users actually work, or how the system is internally organized? Are edge cases handled with considered solutions (not "we'll address that later")? Is the correct audience being served — and is it clear which audience is primary?

### 3. Integrity
Does it hold together completely?

Check: are all states designed — empty, loading, error, partial data, unhappy path? Is the spec complete enough for engineering to build from without filling in gaps? No lorem ipsum or "TBD" at handoff.

For AI-assisted work: integrity is the most common failure mode. AI-generated prototypes typically show only the happy path. Explicitly check for error and empty states.

### 4. Consistency
Does it fit the broader LD product?

Check: LaunchPad components used correctly, new patterns introduced only when existing ones don't serve the use case and documented when introduced, terminology consistent with the rest of the product, interactions behave the same as equivalent interactions elsewhere.

Flag: any component that duplicates an existing LaunchPad component, any term used differently than it's used elsewhere in the product.

### 5. Accessibility
Is it usable by the broadest possible audience?

Check: WCAG 2.1 AA contrast across all states and both themes (light/dark), keyboard navigation works, focus states are visible and logical, status is not communicated by color alone, touch targets are appropriately sized, content works without images.

Note: at LD, accessibility is also a business requirement. Enterprise customers evaluate vendor software against accessibility standards.

### 6. Connectedness
Does it reflect the user's workflow, not the product team's structure?

Check: are there contextual paths to adjacent product areas where the user's next step naturally leads? Can users continue their task without returning to global nav to re-orient? Is terminology consistent at the boundaries between product areas?

At LD, the highest-risk seams are: flags → experimentation results, targeting rules → observability metrics, environment configuration → deployment workflows.

## Design principles to apply

The six criteria are the LD evaluation framework. These established principles inform *how* to evaluate against them — use them to ground findings in something more specific than observation.

**Nielsen's 10 usability heuristics** — the primary reference for interaction quality. Cite them directly when relevant. Common violations in LD work:

- Visibility of system status (H1): loading states, operation feedback, flag state indicators — are users always informed?
- Match between system and real world (H2): does terminology map to how users think, or how the code is organized?
- User control and freedom (H3): can users undo, cancel, or exit without consequence?
- Error prevention (H5): does the design prevent errors before they happen, especially for destructive or irreversible operations?
- Recognition over recall (H6): are relevant options visible rather than requiring users to remember them?
- Help users recognize, diagnose, and recover from errors (H9): does the error message name what failed and what to do next?

**Gestalt principles** — apply when evaluating visual hierarchy, grouping, and layout. Proximity and similarity explain whether related elements read as a group. Figure-ground issues explain why a primary action doesn't stand out. Use these when a Clarity finding is visual rather than textual.

**Cognitive load theory** — grounds findings about density, complexity, and progressive disclosure. If a screen requires the user to hold too much in working memory at once, name it as a cognitive load issue rather than a vague "this feels like a lot."

**WCAG 2.1 AA** — cite specific success criteria when flagging accessibility gaps. "Fails 1.4.3 minimum contrast" is more useful than "contrast might be an issue." WCAG applies at every state: default, hover, focus, disabled, error, dark theme.

**Dieter Rams: good design is as little design as possible** — apply as a check against unnecessary complexity, decorative elements, or feature surface area that doesn't serve a clear user need. When work includes elements that don't earn their place, name it.

When a finding can be anchored to a named principle, do so. It makes the finding specific and harder to dismiss as subjective.

## Step 3: Produce the quality review

```
## Quality Review: [Work Name]

**Reviewed against:** LD Six Quality Criteria
**Primary audience:** [Developer / Admin / PM / Other]
**Work reviewed:** [Figma file / prototype / description / screenshots]

| Criterion | Status | Finding |
|---|---|---|
| Clarity | [✓ / ⚠ / ✗ / ?] | [Specific observation] |
| Utility | [✓ / ⚠ / ✗ / ?] | [Specific observation] |
| Integrity | [✓ / ⚠ / ✗ / ?] | [Specific observation] |
| Consistency | [✓ / ⚠ / ✗ / ?] | [Specific observation] |
| Accessibility | [✓ / ⚠ / ✗ / ?] | [Specific observation] |
| Connectedness | [✓ / ⚠ / ✗ / ?] | [Specific observation] |
| Design principles | [✓ / ⚠ / ✗ / ?] | [Any violations of Nielsen heuristics, Gestalt, cognitive load, or Rams — or "No violations identified"] |

**Priority gaps to address:**
1. [Most critical issue — name the criterion and the specific problem]
2. [Second issue]

**Ready for critique?**
[ ] Yes
[ ] Yes, with caveats — [note what reviewers should know]
[ ] Not yet — address gaps first
```

If every criterion is addressed, say so clearly. A clean review is useful information.

## What good findings look like

| Weak finding | Strong finding |
|---|---|
| "Clarity could be better" | "The confirmation modal doesn't tell the user what will happen after they confirm — Clarity gap" |
| "Might have accessibility issues" | "The selected state in the segment table uses color only (blue highlight) with no other visual indicator — fails WCAG 1.4.1 Use of Color" |
| "Feels inconsistent" | "This uses a custom inline date picker that behaves differently from the DatePicker component in LaunchPad — Consistency gap" |
| "Not sure about connectedness" | "After archiving a flag, the user is returned to the flags list with no path to the experimentation results associated with that flag — Connectedness gap" |
| "This screen has too much going on" | "The targeting rules panel shows eight controls simultaneously with no progressive disclosure. This creates high cognitive load and violates Nielsen H8 (aesthetic and minimalist design) — users don't need all of these at once" |

## Related

- Use `/ux-critique-prep` after this check to generate a critique brief using the findings
- [UX Quality Standards](https://launchdarkly.atlassian.net/wiki/spaces/PD/pages/4714201182/LaunchDarkly+UX+Quality+Standards) — full criterion definitions with discipline-specific examples
- [Critique Engagement and Etiquette](https://launchdarkly.atlassian.net/wiki/spaces/PD/pages/4714659904/Design+Critique+Engagement+and+Etiquette) — how to use these findings in a critique session
- [LaunchPad](https://launchdarkly.atlassian.net/wiki/spaces/PD/pages/4607967261/LaunchPad+Contribution+Review+Guide) — for checking component consistency
