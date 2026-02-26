import json
from typing import Dict, Any

def render_decision_trace(graph_result: Dict[str, Any]) -> str:
    """Renders a Markdown trace from the output of graph.trace"""
    bundles = graph_result.get("bundles", {})
    decisions = bundles.get("decision", [])
    attempts = bundles.get("attempts", [])
    artifacts = bundles.get("artifacts", [])
    research = bundles.get("research", [])
    
    if not decisions:
        return "No decision found in trace."
        
    decision = decisions[0] # Root is usually the decision
    title = decision.get("title", "Untitled Decision")
    tradeoffs = decision.get("tradeoffs", [])
    note = decision.get("notes", decision.get("rationale", ""))
    
    lines = []
    lines.append("## Rekall Decision Trace")
    lines.append("")
    lines.append(f"**Decision**: {title}")
    if note:
        lines.append(f"> {note}")
    
    if tradeoffs:
        lines.append("")
        lines.append("**Tradeoffs**:")
        for t in tradeoffs:
            if isinstance(t, dict):
                lines.append(f"- {t.get('description', json.dumps(t))}")
            else:
                lines.append(f"- {t}")

    lines.append("")
    
    # ASCII tree / Bullet graph
    lines.append("### Provenance")
    lines.append("```text")
    lines.append(f"Decision: {title}")
    
    for a in attempts:
        att_title = a.get("notes", a.get("title", "Unnamed Attempt"))[:60]
        status_marker = "\u274c" if a.get("status") == "failed" else "\u2705"
        lines.append(f" \u251c\u2500\u2500 {status_marker} Attempt: {att_title}")
        
    for a in artifacts:
        ref = a.get("ref", {})
        provider = ref.get("provider", "")
        key = ref.get("key", "")
        art_title = a.get("title", f"{provider} {key}".strip() or "Artifact")
        lines.append(f" \u251c\u2500\u2500 \ud83d\udcc4 Artifact: {art_title}")
        
    for r in research:
        r_title = r.get("title", "Research Note")
        lines.append(f" \u251c\u2500\u2500 \ud83d\udd0d Research: {r_title}")
        
    if not attempts and not artifacts and not research:
        lines.append(" \u2514\u2500\u2500 (No linked attempts or evidence)")
        
    lines.append("```")
    lines.append("")
    
    # Details section
    if attempts:
        lines.append("### Linked Attempts")
        for a in attempts:
            att_title = a.get("notes", a.get("title", "Unnamed Attempt"))
            if a.get("status") == "failed":
                lines.append(f"- \u274c **Failed**: {att_title}")
            else:
                lines.append(f"- \u2705 **Success**: {att_title}")
    
    if artifacts or research:
        lines.append("")
        lines.append("### Logged Evidence")
        for a in artifacts:
            ref = a.get("ref", {})
            provider = ref.get("provider", "")
            key = ref.get("key", "")
            url = ref.get("url", "")
            art_title = a.get("title", f"{provider} {key}".strip() or "Artifact")
            link = f"[{art_title}]({url})" if url else art_title
            lines.append(f"- \ud83d\udcc4 {link}")
            
        for r in research:
            r_title = r.get("title", "Research Note")
            claims = r.get("claims", [])
            lines.append(f"- \ud83d\udd0d **{r_title}**")
            for c in claims:
                lines.append(f"  - {c}")

    lines.append("")
    lines.append("---")
    lines.append("<sub>Generated from git-portable Rekall state (safe-to-commit).</sub>")
    
    return "\n".join(lines)
