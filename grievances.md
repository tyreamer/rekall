# Top Recurring App Dev Grievances with AI Agents

## Top 5 "Must-Fix Next" Items

1. **Amnesia in New Sessions & Handoff Dumps**  
   *The problem:* Agents "forget" context between sessions, or are handed raw text dumps that lack structured relationships.  
   *What to ship next:* `rekall init` scaffolding to establish a persistent `<project>-state` folder for any new agent session, plus `rekall handoff` to synthesize the `boot_brief.md` graph.

2. **Repeating Failed Experiments (Context Rot)**  
   *The problem:* Models overwrite valid optimizations or endlessly try identical failed solutions because the context window flush causes "context rot."  
   *What to ship next:* An `attempts.jsonl` log and a `rekall attempts append` CLI hook, forcing the agent to fetch past attempt hypotheses before generating code.

3. **Missing "Why" Behind AI Code (Architectural Drift)**  
   *The problem:* Agents solve the task but silently break architectural invariants, offering no decision log for human reviewers or future agents.  
   *What to ship next:* A read-only `decisions.jsonl` that enforces invariants and a `rekall propose-decision` tool so agents log architectural shifts.

4. **Agents Stepping On Each Other (Resource Contention)**  
   *The problem:* Background multi-agent setups (e.g. Cursor background agents or custom MAS) mutate the same files or trigger duplicate actions.  
   *What to ship next:* A `rekall claim <item_id> --ttl 5m` file-locking mechanism for true mutual exclusion.

5. **Where Is It and What Is The Password? (Hardcoded Secrets)**  
   *The problem:* Access credentials inevitably leak into prompt histories, logs, or agent memory when they attempt to interact with live environments.  
   *What to ship next:* An `Env+Access pointers` JSON schema that injects environment maps by reference (not value) into the agent's context.

---

## Ranked List of Grievances (Top 16)

| Rank | Grievance | Quote Snippet (Source) | Who | Freq | Severity | Root Cause | Rekall Fit | What to Ship Next | "Kanban" Risk? |
|--|--|--|--|--|--|--|--|--|--|
| 1 | **Amnesia in New Sessions** | "agents often 'wake up with amnesia' at the start of a new session" ([Medium](https://medium.com/)) | Solo / Small Team | High | High | Context windows clear when the session is closed, destroying all processed knowledge. | **State Artifact** | `rekall init ./project-state` | No (pure filesystem persistence) |
| 2 | **Repeating Failed Experiments** | "Context Rot where they forget past requirements... leading to overwriting valid data" ([parallel.ai](https://parallel.ai/)) | Solo Builder | High | High | Agents lack an immutable historical ledger of failed coding attempts. | **Attempts** | `rekall attempts list` | No (this is a scientific engineering log) |
| 3 | **Handoffs Are Raw Dumps** | "transferring context as a one-time data dump... fails to preserve relationships" ([xtrace.ai](https://xtrace.ai/)) | Enterprise | Med | High | Handoffs push unstructured chat history instead of queryable state graphs. | **Timeline / Links** | `rekall handoff --target next-agent` | No |
| 4 | **Agents Stepping On Each Other** | "conflicts can occur when AI agents have competing goals or vie for shared resources" ([milvus.io](https://milvus.io/)) | Small Team | High | High | No mutual exclusion or atomic file locks exist for standard coding agents. | **Claim-Lease** | `rekall claim <target> --ttl 5m` | Yes (if we treat claims like Jira assignment) |
| 5 | **Missing The "Why" (No Decision Log)** | "aim to capture the rationale and choices made by AI agents... not just the 'what'" ([addyosmani.com](https://addyosmani.com/)) | Small Team | High | Med | Agents output raw diffs without documenting the architectural trade-offs made. | **Decisions** | `rekall propose-decision` | No (architectural documentation) |
| 6 | **Credentials Leaked in Agent Memory** | "leakage of AI agent credentials... often categorised under Non-Human Identity exposure" ([threatngsecurity.com](https://threatngsecurity.com/)) | Enterprise | Med | High | API keys and secrets are fed as raw strings into the LLM context and logs. | **Env+Access Pointers** | Local `.env` reference schema | No |
| 7 | **What Changed? (Audit Trails)** | "trace the contributing factors when operational workflows... encounter anomalies" ([servicenow.com](https://servicenow.com/)) | Enterprise | High | High | No chronological audit log exists detailing which agent mutated what state. | **Timeline** | Immutable `timeline.jsonl` | No |
| 8 | **Duplicating High-Impact Actions** | "high-impact actions, such as sending emails... are processed only once" ([Medium](https://medium.com/)) | Enterprise | Med | High | MAS setups lack shared idempotency keys for tracking transaction events. | **Attempts (Idempotency)** | Add `idempotency_key` field to Attempt | No |
| 9 | **Lost Dependencies & Related Docs** | "preserve the structured relationships between different pieces of information" ([xtrace.ai](https://xtrace.ai/)) | Small Team | Med | Med | Agents see isolated text files, not a graph of code-to-design relationships. | **Typed Links** | Defined cross-tool Link schema | Yes (could feel like generic 'relates to' tickets) |
| 10 | **Reverting Valid Optimizations** | "prevent undoing optimizations or repeating tasks" ([hvpandya.com](https://hvpandya.com/)) | Solo / Small Team | High | High | Unrecorded architectural constraints get wiped out during "bug fix" loop. | **Decisions (Invariants)** | Exposing `invariants` during boot | No |
| 11 | **No "Executive Summary" for Humans** | "a 'speed win' by automating tasks... [but humans left reading console logs]" ([upgradewithsom.com](https://upgradewithsom.com/)) | Solo Builder | Med | Med | AI iterates 100 times in background; human has to scroll terminal to see progress. | **Exec Query** | `rekall status --concise` | Yes (if formatted exactly like an Agile sprint report) |
| 12 | **MCP JSON Schema Mismatch** | "data provided by an AI agent... doesn't conform to the InputSchema" ([merge.dev](https://merge.dev/)) | Solo Builder | High | Med | Agents silently hallucinate parameters when executing tools via MCP. | **Validate / Import** | `rekall validate --strict` | No |
| 13 | **Endless Execution Crashes** | "crashes... preventing the need to re-execute expensive LLM calls" ([pydantic.dev](https://pydantic.dev/)) | Enterprise | Med | High | Workflows lack durable checkpointing if the underlying Python process halts. | **State Artifact** | Checkpointing / Export tools | No |
| 14 | **The Sync Gap (Figma vs Code)** | "Context window... alone does not provide the persistence and structure" ([xtrace.ai](https://xtrace.ai/)) | Small Team | Med | Med | The context window is flat; bridging a Figma component to a React component requires structured pointers. | **Typed Links** | `rekall link <file> <figma_id>` | Yes |
| 15 | **Tool Execution Dropped Silently** | "failures are distinct from protocol-level errors and indicate... issue arose during processing" ([dev.to](https://dev.to/)) | Solo Builder | Med | High | The agent sends the call but loses context before recording the failure logic. | **Attempts** | MCP tool wrapper logging | No |
| 16 | **Agent Silos (Cursor + Claude + Autogen)** | "transfer of context... between agents or across different sessions" ([github.io](https://github.io/)) | Small Team | High | Med | Users juggle Cursor for IDE, Claude Code for CLI, and Autogen for backend, with no shared brain folder. | **Validate / Import** | `rekall import --merge` | No |
