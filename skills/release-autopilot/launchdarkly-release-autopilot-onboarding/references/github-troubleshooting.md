# GitHub still not connected after "Done"

The connect link acts on whatever LaunchDarkly session the browser has. This connection is signed in as the member from Step 1 (`get-member-self`). If the browser is signed in to a different LaunchDarkly account, or as a different member, the user installs or authorizes the App there, and this connection still sees nothing.

Check the causes in this order. Stop at the first that applies.

1. **Different LaunchDarkly account or member in the browser.** SKILL.md Step 3 asks about this first. An install made from the other account stays there; that account's admin can remove it if it was a mistake.
2. **Different LaunchDarkly instance.** The browser is on another instance (for example EU or federal) than this connection. Give the link with the instance this connection uses.
3. **Authorized with the wrong GitHub account** (`flow=authorize` remains). The GitHub account they authorized cannot see the organization's install. They reconnect with a GitHub account that is a member of that organization.
4. **Installed on a different GitHub organization.** The App is now installed, but not on the organization that owns their repo. See the repo-owner check in Step 4.

If none applies, say what you checked and stop. Do not retry the link more than once without a change.
