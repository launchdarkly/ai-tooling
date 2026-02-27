---
name: aiconfig-projects
description: "Set up LaunchDarkly projects for your application. Helps you create projects, retrieve SDK keys, and understand how projects organize your AI Configs and feature flags."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "1.0.0-experimental"
---

# LaunchDarkly Projects Setup

You're using a skill that will guide you through setting up a LaunchDarkly project. Your job is to understand what projects are, create one that fits the use case, retrieve the SDK keys, and verify the setup.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment.

**Required MCP tools:**
- `create-project` -- create a new LaunchDarkly project
- `get-project` -- retrieve a project with its environments and SDK keys

## What Are Projects?

Projects are LaunchDarkly's top-level organizational containers that hold:
- All your AI Configs
- Feature flags and segments
- Multiple environments (Production and Test created by default)

Think of projects as separate applications, services, or teams that need their own isolated set of configurations.

## Workflow

### Step 1: Assess the Situation

Determine the right approach based on your use case:

| Scenario | Approach |
|----------|----------|
| New application, no LaunchDarkly integration | Create a new project |
| Existing LaunchDarkly usage | Use `get-project` to check if the right project exists |
| Multiple services/microservices | Create a project per service |
| Multi-region or multi-tenant | Create a project per region/tenant |

### Step 2: Create or Retrieve the Project

**New project** -- Use `create-project` with:
- `name` -- human-readable name
- `key` -- unique identifier (lowercase, hyphens, must start with a letter)
- Optional: `tags` for organization

**Existing project** -- Use `get-project` to retrieve it and its SDK keys.

### Step 3: Retrieve SDK Keys

The response from `create-project` or `get-project` includes environments with SDK keys. Each environment has:
- `sdkKey` -- for server-side SDKs
- `mobileKey` -- for mobile/client-side SDKs

Store these keys following your codebase's secrets management pattern (environment variables, secrets manager, etc.).

### Step 4: Verify

Use `get-project` to confirm:
1. Project exists with the correct name and key
2. Environments are present (Production, Test at minimum)
3. SDK keys are available

**Report results:**
- Project exists and has environments
- SDK keys are present
- Provide next steps (create AI Configs, set up SDK integration)

## Project Key Best Practices

Project keys must follow these rules:
- Lowercase letters and hyphens only
- Must start with a letter
- No underscores, dots, or uppercase

Good examples: `support-ai`, `chat-bot-v2`, `internal-tools`

**Naming recommendations:**
- Keep keys short but descriptive
- Use team/service/purpose as naming scheme
- Be consistent across your organization

## Common Organization Patterns

**By Team:**
- `platform-ai`, `customer-ai`, `internal-ai`

**By Application/Service:**
- `mobile-ai`, `web-ai`, `api-ai`

**By Region/Deployment:**
- `ai-us`, `ai-eu`, `ai-apac`

## Edge Cases

| Situation | Action |
|-----------|--------|
| Project already exists (409) | Use `get-project` to retrieve existing |
| Need multiple projects | Create separately for each service/region/team |
| Token lacks permissions | Check that the MCP server has `projects:write` permission |

## What NOT to Do

- Don't create projects without understanding the use case first
- Don't commit SDK keys to version control
- Don't use production SDK keys in test/development environments
- Don't create duplicate projects unnecessarily

## Next Steps

After setting up projects:
1. **Create AI Configs** -- Use the `aiconfig-create` skill
2. **Configure targeting** -- Use flag targeting skills
3. **Set up SDK integration** -- Use the SDK keys in your application

## Related Skills

- `aiconfig-create` -- Create AI Configs in projects
- `aiconfig-variations` -- Manage config variations
