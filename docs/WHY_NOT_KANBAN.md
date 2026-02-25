# Why Rekall is Not Kanban

**Rekall is a project reality blackboard + ledger, not a board or task manager.**

AI agents don't need another place to drag tickets from "To Do" to "Done." They need a machine-readable, irrefutable source of truth about what the project is, what constraints exist, and what has already failed. Rekall provides the missing state layer that agents and technical leaders actually need.

## The 4 Differentiating Primitives

1. **Attempts**: A typed ledger of what has been tried, the result, and why it failed. Agents learn from past mistakes instead of repeating them.
2. **Decisions**: Explicit records of trade-offs and architectural choices. Context is preserved permanently.
3. **Timeline**: An immutable event log of milestones, commits, and state changes.
4. **Env+Access Pointers**: Typed pointers to where the project is running and how to access it (without storing secrets directly).

## Evidence-First Exec Queries
Status in Rekall is trustworthy because it is derived from evidence. When you ask Rekall what is blocking a project, it doesn't just read a string; it queries the graph of failed attempts and unresolved decisions. This ensures that the "status" actually reflects the reality of the codebase and environment.

## Complements Jira / GitHub / Notion
Rekall **does not replace** your existing task trackers or wikis. Instead, it **links out** to them via typed links. You keep high-level epics in Jira, product requirements in Notion, and code in GitHub. Rekall acts as the local, portable tissue connecting these systems for the agent, standardizing the immediate context required to execute autonomous work.

## When to Use Rekall (and When Not To)

**Use Rekall when:**
- You are operating autonomous AI coding agents (or pair-programming heavily).
- You frequently lose context between sessions or team members.
- You need a portable, local-first artifact that can be committed to Git.

**Do NOT use Rekall when:**
- You just want a visual board to track tasks for a non-technical team.
- You want two-way syncing with Jira or Linear.
- You need deep, human-centric sprint planning mechanics.
