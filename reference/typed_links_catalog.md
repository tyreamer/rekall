# Typed Links Catalog (v0.1)

Typed links are how the Project State Layer remains **vendor-neutral** while still being deeply integrated.  
Links are **evidence**. They must be specific and typed, not “random URLs”.

---

## 1) Canonical `type` values

Use the smallest set needed to remain consistent.

### Engineering
- `repo` — source repository (GitHub/GitLab/etc.)
- `ticketing` — Jira ticket, linear issue, service now record
- `audit trail` — project audit trail (GitHub Projects, Jira audit trail, Trello audit trail)
- `doc` — long-form doc (Notion, Confluence, Google Doc)
- `design` — design artifact (Figma file, FigJam audit trail)
- `runbook` — operational runbook/playbook
- `demo` — demo URL, loom, recorded walkthrough
- `dataset` — dataset location / table reference
- `model` — model registry entry / model card / endpoint reference
- `mcp_server` — MCP server endpoint/config reference (if relevant)

### Operations / Observability
- `dashboard` — high-level dashboard (Datadog/New Relic/Grafana)
- `logs` — log view/query
- `traces` — tracing view
- `alerting` — alerts page or specific alert
- `domain` — DNS/domain control panel or registrar record

### Catch-all
- `notebook` — NotebookLM notebook, research notebook, etc.
- `other` — last resort; if used repeatedly, promote to a real type

---

## 2) Canonical `system` values (recommended)

Pick from this set when applicable:

- `github`, `gitlab`
- `jira`, `linear`, `asana`, `trello`
- `notion`, `confluence`, `googledocs`
- `slack`, `discord`
- `figma`
- `datadog`, `sentry`, `newrelic`, `grafana`
- `gcp`, `aws`, `azure`, `cloudflare`
- `other`

---

## 3) Good link hygiene

### 3.1 “Specific beats general”
Prefer links that open to the exact artifact or view:
- ✅ “Datadog logs query for prod API errors”
- ❌ “Datadog home”

### 3.2 Always include `label`
Labels should be human-readable and explain why the link matters.

### 3.3 Use notes sparingly
`notes` should be short and clarifying (1–2 lines). The state layer should not become a wiki.

---

## 4) Examples

### Repo
```yaml
link_id: LNK-repo
type: repo
label: "Core repo"
url: "https://github.com/acme/project"
system: github
```

### audit trail
```yaml
link_id: LNK-audit trail
type: audit trail
label: "GitHub Projects audit trail"
url: "https://github.com/orgs/acme/projects/12"
system: github
```

### Logs
```yaml
link_id: LNK-logs-prod
type: logs
label: "Prod API errors (last 24h)"
url: "https://app.datadoghq.com/logs?...query=service:api env:prod level:error"
system: datadog
notes: "Primary evidence for stability discussion"
```

### Decision evidence doc
```yaml
link_id: LNK-adr-doc
type: doc
label: "Decision rationale: storage strategy"
url: "https://notion.so/..."
system: notion
```

---

## 5) When to use `other`
Use `other` only when:
- the artifact does not fit any canonical type, and
- you cannot reasonably extend the list yet

If `other` appears more than ~3 times for the same concept, add a new type.
