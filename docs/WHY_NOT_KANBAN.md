# Rekall is NOT a Kanban Board for Agents

When engineers first hear about Rekall, the most common reaction is: *"Oh, so it's a Jira/Notion clone built specifically for AI agents."*

**No, it is not.**

Rekall is a **state-first, agent-native project reality blackboard + ledger**. 

## The Problem with "Tasks"
Kanban boards and issue trackers are designed for human coordination. They represent discrete units of effort (Tasks, Tickets) assigned to people. 

AI agents, however, don't need "tickets" to understand what to do; they need **context**, **history**, and **state**.
If an agent fails an attempt to configure a specific environment, Jira doesn't organically capture the *why* or the *what failed*. 

## The Rekall Architecture
Rekall operates entirely differently. It records the irrefutable truth of what the project is, what was decided, what failed, and what is currently happening—all stored as machine-readable YAML and JSONL files within your repository.

- **`project.yaml`**: The constitution. What is this project? What are its boundaries?
- **`work-items.jsonl`**: The ledger. Not just open tasks, but the history of *how* a task evolved, what blocked it, and explicitly defining what "done" means.
- **`attempts.jsonl`**: The scientific journal. What did the agent or human already try that failed? (Prevents infinite agentic looping).
- **`decisions.jsonl`**: The "Why". Explaining architectural trade-offs explicitly so new agents don't second-guess the blueprint.
- **`timeline.jsonl`**: The audit trail.

## Complementary, Not Competitive
Rekall **does not replace** Jira, Notion, GitHub Issues, Slack, or Figma. 

Instead of re-typing specs, Rekall uses **typed links** to bridge into those tools.
```yaml
links:
  - type: PRD
    url: https://notion.so/my-prd
  - type: Figma
    url: https://figma.com/my-designs
```

Rekall acts as the unified, machine-readable brain for your AI agents to consult *before* they act, ensuring they never lose context across sessions, branches, or humans. It's the unifying ledger of project truth.
