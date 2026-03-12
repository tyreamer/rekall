# Rekall Skill Examples

## Example 1: Session Start
Assistant: I am starting a new session. First, I will initialize Rekall and get a brief.
Tool Call: `rekall.init(goal="Implement user authentication")`
Tool Call: `rekall.brief()`
Assistant Response: "Based on the brief, the project is in alpha phase with a goal of implementing user authentication. There are no current blockers, but the previous attempt to use JWT failed due to library version mismatch. I will proceed with OAuth2 as decided previously."

## Example 2: Recording a Decision
Assistant: I need to decide on the database schema.
Tool Call: `rekall.record(type="decision", data={"title": "Use SQLite", "rationale": "Local-first requirements", "tradeoffs": "Limited concurrency"})`
Assistant Response: "I have recorded the decision to use SQLite. I will now create the initial migrations."

## Example 3: Checkpointing and Verifying
Assistant: I have finished the migration scripts. I will now verify and checkpoint.
Tool Call: `rekall.verify()`
Tool Call: `rekall.checkpoint(title="Completed migrations", type="milestone", git_commit="auto")`
Assistant Response: "Verification passed and I have checkpointed the progress. The project is now on track for the next phase."
