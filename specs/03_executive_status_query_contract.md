# Executive Status Query Contract (v0.1)

**Status:** Draft (v0.1)  
**Purpose:** Define the standard questions leaders ask and the **required response format** so any chat agent connected to the Project State Layer can answer consistently, safely, and with evidence.

This contract is **tool-agnostic** (works via MCP, REST, CLI, etc.). It assumes a canonical Project State Layer exists with:
- Work Items (status, blockers, owners, timestamps)
- Attempt Log (append-only)
- Decision Log (append-only)
- Timeline (append-only)
- Environment Map + Access References (pointers only)
- Typed Links to external systems (Jira/GitHub/Notion/Slack/Figma/etc.)

---

## 1) Goals

### 1.1 What “good” looks like
A response is considered **executive-ready** if it:
- Answers the question in 30–90 seconds of reading
- Includes a confidence level
- Can be drilled down via evidence IDs/links
- Does not invent metrics or facts not present in state
- Highlights blockers/risks with clear ownership

### 1.2 What this contract prevents
- “Vibes” status reports with no supporting artifacts
- Overconfident claims
- Hallucinated timelines or made-up metrics
- Endless detail dumps instead of decision-useful summaries

---

## 2) Universal Response Shape (Required)

Every response to a contract query MUST follow this shape:

### 2.1 Required fields
- **Answer (Summary):** 1–3 bullets maximum
- **Confidence:** `low | medium | high`
- **Evidence:** 3–10 evidence references (IDs and/or typed links)
- **Top Follow-ups:** 1–3 suggested follow-up questions (optional but recommended)

### 2.2 Evidence reference format
Evidence MUST reference one or more of:
- WorkItem IDs
- Attempt IDs
- Decision IDs
- Timeline Event IDs
- Typed Links (with type + URL)

**Example evidence list (conceptual):**
- `work_item: WI-2f31...`
- `decision: DEC-91aa...`
- `attempt: ATT-0d2b...`
- `timeline: EVT-7c3a...`
- `link: LNK-logs-prod (type=logs, system=datadog)`

### 2.3 Optional fields (recommended)
- **Drivers:** 2–4 bullets explaining “why” (each tied to evidence)
- **Risks:** top 1–3 risks with mitigation owner (each tied to evidence)
- **Blockers:** ranked list of blockers (age, owner, unblock path)

### 2.4 Hard rules
- MUST NOT claim numbers/metrics unless they exist in state.
- MUST NOT reference secrets. If access is needed, reference AccessRefs only.
- MUST NOT declare “on track” without citing evidence.

---

## 3) Confidence Rules (Required)

Confidence MUST be derived from state freshness and completeness, not gut feel.

### 3.1 Default confidence heuristics
- **High** if:
  - Recent updates exist (work items/timeline) AND
  - No critical blockers are stale AND
  - Decisions for major tradeoffs are recorded
- **Medium** if:
  - Some evidence exists but parts are stale or incomplete
- **Low** if:
  - State is missing, stale, contradictory, or has no recent activity
  - Key decisions/attempts are absent for major unknowns

### 3.2 Evidence for confidence
The response SHOULD include a brief reason for the confidence level (“confidence drivers”), tied to evidence.

---

## 4) Canonical Queries (v0.1)

> The contract defines **intent**, **required outputs**, and **evidence expectations**. Implementations may add synonyms, but these are the canonical forms.

### Q1) “Is this project on track?”
**Intent:** Provide an executive snapshot: status, drivers, confidence.

**Response MUST include:**
- Status: `on_track | at_risk | off_track | paused`
- 2–4 drivers (“why”)
- Top blocker (if any)
- Next milestone (if present)

**Evidence MUST include:**
- 2–5 WorkItems (current)
- 1–2 Timeline events or Decisions related to current direction

**If state lacks explicit status:**
- The system MAY compute a status using recorded blockers + staleness rules, but MUST disclose the heuristic.

---

### Q2) “What’s blocking us right now?”
**Intent:** Identify top blockers and how to unblock.

**Response MUST include:**
- Ranked blockers (top 3–7)
- For each blocker:
  - owner / responsible party
  - age (derived from timestamps)
  - unblock path (what needs to happen next)
  - whether it blocks a milestone

**Evidence MUST include:**
- The blocked WorkItems
- Any Decisions/Attempts that explain the blocker context

---

### Q3) “What changed since <date>?”
**Intent:** Summarize changes across work, decisions, attempts, and risk.

**Response MUST include:**
- 3–7 change bullets (grouped by type: work/decision/attempt/release/risk)
- Explicit date range acknowledged in the answer

**Evidence MUST include:**
- Timeline events in range
- Any referenced WorkItems/Decisions/Attempts in range

---

### Q4) “What’s the plan for the next 7 days?”
**Intent:** Communicate near-term execution plan.

**Response MUST include:**
- 3–7 committed work items (or best approximation)
- Known dependencies/blockers
- One “big risk” for the week

**Evidence MUST include:**
- WorkItems marked high priority or in_progress
- Timeline/milestone references if present

---

### Q5) “What are the top risks and mitigations?”
**Intent:** Provide a risk register snapshot.

**Response MUST include:**
- Top 3–5 risks
- For each:
  - impact statement (plain language)
  - mitigation plan or next step
  - owner

**Evidence MUST include:**
- WorkItems tagged as risk/blocked
- Decisions/Attempts relevant to mitigations

**Rule:** Do not invent risks. If risks are not explicitly tracked, report “not enough recorded risk state” and propose what to capture next.

---

### Q6) “What decisions did we make and why?”
**Intent:** Make tradeoffs transparent.

**Response MUST include:**
- 3–7 most relevant recent decisions (or most impactful if “recent” not specified)
- For each:
  - chosen option
  - primary tradeoff(s)
  - impact (what it changed)

**Evidence MUST include:**
- Decision IDs + any linked WorkItems
- Links to external docs (if referenced)

---

### Q7) “What have we tried that didn’t work?”
**Intent:** Avoid repeating dead ends, show learning velocity.

**Response MUST include:**
- 3–7 failed/negative attempts
- For each:
  - hypothesis
  - action
  - result
  - conclusion (why it failed / what we learned)

**Evidence MUST include:**
- Attempt IDs
- Associated WorkItems/Decisions where relevant

---

### Q8) “What’s the single riskiest assumption right now?”
**Intent:** Surface the one unknown most likely to derail.

**Response MUST include:**
- One assumption, written plainly
- Why it’s risky (impact + uncertainty)
- The next test/attempt to validate it
- Owner

**Evidence MUST include:**
- Attempt or WorkItem that supports why this is currently unvalidated
- Any decision context if it’s a strategic assumption

---

### Q9) “Where is this running, and how do I access it?”
**Intent:** Provide operational truth: environments + access path without secrets.

**Response MUST include:**
- Environments (dev/stage/prod as applicable)
- URLs/endpoints
- Where logs/traces live (typed links)
- Access steps (role/vpn/sso) via AccessRefs

**Evidence MUST include:**
- Environment IDs + associated typed links
- AccessRef IDs only (never secret values)

---

### Q10) “If we paused today, what do we need to resume in 30 minutes?”
**Intent:** “Project continuity” check.

**Response MUST include:**
- What to read first (project goal + current phase)
- The current top 3 work items
- The most important decision(s)
- The most recent critical attempt outcomes
- The operational entry points (where running, where logs are)

**Evidence MUST include:**
- Project goal/constraints section reference
- WorkItem IDs
- Decision IDs
- Attempt IDs
- Environment + AccessRef IDs

---

## 5) Computation Rules (v0.1, Minimal & Defensible)

### 5.1 Status computation (if explicit status absent)
Implementations MAY compute status using a simple heuristic derived from state:
- **off_track** if:
  - ≥1 critical blocker is stale beyond threshold (e.g., 7 days) AND blocks milestone
- **at_risk** if:
  - blockers exist or critical decisions pending
- **on_track** if:
  - active work exists, blockers are not stale, and timeline shows recent progress
- **paused** if:
  - explicit pause recorded in timeline or status flag

**Disclosure requirement:** If computed, the response MUST say so:  
“Status computed from recorded blockers + staleness thresholds.”

### 5.2 Blocker ranking (default)
Rank blockers by:
1) Priority (p0/p1 first)
2) Age (older first)
3) Blast radius (blocks more items/milestones)
4) Owner missing (unowned blockers bubble up)

### 5.3 Freshness checks
If no updates within a configurable window (e.g., 30 days), confidence MUST be **low**.

---

## 6) Safety & Compliance Rules (Required)

### 6.1 No secrets
Never include credentials. Use AccessRefs only.

### 6.2 No hallucinated metrics
If asked for numbers not present in state:
- Respond with what exists
- Provide evidence links
- Recommend recording the missing metric in state going forward

### 6.3 Permission-aware responses
If the querying actor lacks permission to see certain sections:
- Provide a redacted answer
- Explicitly state what was withheld (at a high level)
- Provide a path to request access (without leaking details)

---

## 7) Test Cases (Acceptance Criteria)

A build is compliant with this contract if:

- [ ] For each query Q1–Q10, the agent returns the universal response shape (§2)
- [ ] Each answer includes evidence references
- [ ] Confidence is present and justified by freshness/completeness
- [ ] No secrets are ever included
- [ ] “On track” answers never appear without evidence
- [ ] If data is missing, the agent says so and suggests what to capture

---

## 8) Implementation Notes (Non-Normative)

- This contract is designed to be executed by a chat agent that calls tooling endpoints like:
  - `get_project()`, `list_work_items()`, `get_timeline(since=...)`, `list_decisions(since=...)`, etc.
- Responses should be concise by default with drill-down available via evidence IDs/links.

---

## 9) Versioning
- Contract version: **v0.1**
- Backward compatibility: Implementations SHOULD support previous query forms and map them to the closest canonical query while preserving response shape.