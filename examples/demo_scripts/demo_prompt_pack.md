# Demo Prompt Pack (v0.1)

Copy/paste prompts to drive demos with any MCP-capable agent.

---

## A) Director / Manager prompts

### 1) On-track
“Is this project on track? Answer with summary, confidence, and evidence references.”

### 2) Blockers
“What’s blocking us right now? Rank the top 5 blockers and include owner, age, and unblock path. Include evidence references.”

### 3) Changes since last week
“What changed since last week? Group changes by decisions / attempts / work / timeline. Include evidence references.”

### 4) Next 7 days
“What’s the plan for the next 7 days? List the top committed work items and any dependencies. Include evidence references.”

### 5) Decisions
“What decisions did we make recently and why? Include tradeoffs and evidence.”

### 6) Failed attempts
“What have we tried that didn’t work? Summarize the top failed attempts and what we learned. Include evidence.”

### 7) Where it runs + access
“Where is this running and how do I access it? Include environments, URLs, observability links, and AccessRefs (no secrets). Include evidence.”

### 8) Resume in 30
“If we paused today, what do we need to resume in 30 minutes? Include the top 3 work items, key decisions, recent attempts, and where it runs. Include evidence.”

---

## B) Builder prompts

### 1) Find unblocked work
“List the best unblocked work items I can pick up right now. Include why each is unblocked and evidence references.”

### 2) Claim the top item
“Claim the top priority work item for me (use claim/lease) and confirm the lease time.”

### 3) Update status safely
“Update the claimed work item to ‘in_progress’ and add a short progress note. Use optimistic concurrency and explain if there’s a conflict.”

### 4) Record an attempt
“Append an attempt entry for the work item: hypothesis, action taken, result, conclusion, next step. Include an evidence link if relevant.”

### 5) Propose a decision
“Propose a decision related to this work with options considered and tradeoffs. Mark it ‘proposed’ and include evidence links.”

### 6) Generate an executive summary
“Generate an executive ‘on track’ status update using evidence-first rules. Do not invent metrics.”

---

## C) Safety prompts (verify invariants)

### 1) Secret detection check
“I’m going to paste a token. If it looks like a secret, reject it and tell me to store a pointer instead.”

### 2) Conflict simulation
“Try updating a work item with an old expected_version and show me the conflict behavior.”

---

## D) Response shape reminder (for agents)

Every executive answer must include:
- 1–3 summary bullets
- confidence (low/medium/high)
- evidence references (IDs/typed links)
- optional drivers/blockers/risks

---

## E) Positioning reminder (say this out loud)

“Rekall is not Kanban for agents. It’s a project’s living state — work + knowledge + decisions + attempts + operational truth — exposed via MCP so agents and leaders can query it with evidence.”
