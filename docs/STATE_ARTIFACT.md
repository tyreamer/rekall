# Rekall State Artifacts

Rekall operates entirely on local, plain-text logs stored in a directory (typically `project-state/`) at the root of your repository. This design ensures that the **project memory lives with the code**.

## "Safe to Commit" Guarantee

Because Rekall artifacts are committed to your repository's version control, **they must never contain secrets, tokens, or PII.**

Rekall enforces strict policies to guarantee that state files are "Safe to Commit":
1. **Typed Pointers Only**: Rekall links to external systems (Jira, GitHub, Notion) via typed pointers (e.g. `artifact_type: github_pr`, `key: 123`) instead of raw APIs containing tokens.
2. **Never Store Secrets**: Rekall will actively reject any records that match common secret signatures (e.g., `sk-`, `ghp_`, `xoxb-`, etc.) and throw a `SECRET_DETECTED` error.
3. **URL Sanitization**: Query parameters on URLs are known vectors for accidental token leakage (e.g., `?access_token=...`). Rekall **strips all query parameters** from URLs saved in `artifact` and `research_item` logs by default. 

**What we store**:
- IDs, Titles, Summaries, and Actionable Notes.
- Tradeoffs, claims, and context.
- Sanitized URLs and Typed Pointers.

**What we NEVER store**:
- API Tokens, Headers (like `Authorization: Bearer ...`).
- Sensitive User Data.
- Full API Response Dumps or HTML bodies.

---

## State Files

A typical project state folder looks like this:

```text
project-state/
  manifest.json         # Index of streams and active segments
  schema-version.txt    # Current schema version
  project.yaml          # Project identity and baseline goals
  envs.yaml             # Running environments (dev, staging, prod)
  access.yaml           # Systems and credentials the agent needs (no secrets)
  streams/
    attempts/             # History of failures/successes
    decisions/            # Architectural choices
    artifacts/            # External PRs, Docs, etc.
    research/             # Notes and claims
    links/                # Graph edges connecting the above
    anchors/              # Intent Checkpointing
```

All event streams are **append-only JSONL files**.

---

## Example Logs

**Attempt** (`attempts.jsonl`)
```json
{"attempt_id": "att-123", "timestamp": "...", "performed_by": {"actor_id": "agent-1"}, "status": "failed", "notes": "Tried X but memory spiked"}
```

**Decision** (`decisions.jsonl`)
```json
{"decision_id": "dec-456", "timestamp": "...", "title": "Use PostgreSQL", "status": "approved", "tradeoffs": ["Heavier than SQLite"]}
```

**Artifact** (`artifacts.jsonl`)
```json
{"artifact_id": "art-789", "type": "artifact", "artifact_type": "github_pr", "ref": {"provider": "github", "key": "42"}}
```

**Link** (`links.jsonl`)
```json
{"edge_id": "edge-1", "type": "link", "from": {"node_type": "attempt", "id": "att-123"}, "to": {"node_type": "decision", "id": "dec-456"}}
```

**Anchor** (`anchors.jsonl`)
```json
{"anchor_id": "anch-1", "type": "anchor", "note": "Paused work. Next step is wiring DB.", "timestamp": "..."}
```

---

## How to use intent checkpointing

1. Save an anchor when leaving a task: `rekall.anchor.save({"note": "wiring DB"})`.
2. Resume later: `rekall.anchor.resume({"anchor_id": "anch-1"})`. This pulls recent activities since the anchor was created.
3. Digest `While You Were Gone`: Use `rekall.digest.while_you_were_gone({"limit": 25})` to see what changed overnight.

---

## Setting up GitHub Decision Trace on PRs

Rekall can automatically post a "Decision Trace" on GitHub Pull Requests, showing the rationale, failures, and evidence behind the architectural decisions in the PR. 

1. Create a GitHub Action workflow file `.github/workflows/decision-trace.yml`:

```yaml
name: "Decision Trace"
on:
  pull_request:
    types: [opened, synchronize, reopened]
permissions:
  contents: read
  pull-requests: write
jobs:
  post-trace:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      - run: pip install rekall-core
      - env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: python path/to/rekall/scripts/post_decision_trace.py
```

2. Make sure you invoke the `post_decision_trace.py` script from the Rekall tools suite, or write your own script that uses the `.trace_graph()` API from `StateStore`.

The resulting trace will parse `artifacts.jsonl` to detect if the current PR matches a known artifact block, and backtrace through the `links.jsonl` graph to surface the driving decision, attempts, and evidence!
