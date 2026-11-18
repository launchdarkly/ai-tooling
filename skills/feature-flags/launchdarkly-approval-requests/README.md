# LaunchDarkly Approval Requests Skill

An Agent Skill for taking flag, segment, and AgentControl Config changes through LaunchDarkly approvals.

## Overview

This skill teaches agents how to:
- Create an approval request with reviewers the user named, or an approval integration's fields
- Hand the review to a person and wait instead of polling
- Read a request's review decision and change status, including the reviewer's reason for a decline
- Apply a request only after it is approved, and confirm the change

The agent never approves or declines a request.

## Installation (Local)

Place this skill directory where your agent client loads skills.

## Prerequisites

- The remotely hosted LaunchDarkly MCP server
