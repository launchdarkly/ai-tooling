const { test } = require("node:test");
const assert = require("node:assert/strict");

// inline_skill_invocation puts the slash command and the request in one
// message. force_skill_invocation still uses initialPrompt as its own turn.
const { resolveSkillDelivery } = require("../providers/claude-skill-agent-sdk");

const slug = "launchdarkly-experiment-setup";
const request = 'Set up an experiment on flag "checkout-flow".';

test("inline invocation prepends the slash command and leaves initialPrompt unset", () => {
  const delivery = resolveSkillDelivery({
    skillSlug: slug,
    userMessage: request,
    forceSkillInvocation: false,
    inlineSkillInvocation: true,
  });

  assert.equal(delivery.prompt, `/${slug}\n\n${request}`);
  assert.equal(delivery.prompt.startsWith(`/${slug}\n\n`), true);
  assert.equal(delivery.prompt.endsWith(request), true);
  assert.equal(delivery.initialPrompt, undefined);
});

test("inline invocation wins when force_skill_invocation is also set", () => {
  const delivery = resolveSkillDelivery({
    skillSlug: slug,
    userMessage: request,
    forceSkillInvocation: true,
    inlineSkillInvocation: true,
  });

  assert.equal(delivery.prompt, `/${slug}\n\n${request}`);
  assert.equal(delivery.initialPrompt, undefined);
});

test("with inline off, force_skill_invocation still sets initialPrompt and leaves the request unchanged", () => {
  const delivery = resolveSkillDelivery({
    skillSlug: slug,
    userMessage: request,
    forceSkillInvocation: true,
    inlineSkillInvocation: false,
  });

  assert.equal(delivery.prompt, request);
  assert.equal(delivery.initialPrompt, `/${slug}`);
});

test("with both off, the request is sent alone and initialPrompt is unset", () => {
  const delivery = resolveSkillDelivery({
    skillSlug: slug,
    userMessage: request,
    forceSkillInvocation: false,
    inlineSkillInvocation: false,
  });

  assert.equal(delivery.prompt, request);
  assert.equal(delivery.initialPrompt, undefined);
});
