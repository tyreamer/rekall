import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict

from rekall.core.state_store import StateStore


def render_decision_trace(graph_result: Dict[str, Any]) -> str:
    """Renders a Markdown trace from the output of graph.trace"""
    bundles = graph_result.get("bundles", {})
    decisions = bundles.get("decision", [])
    attempts = bundles.get("attempts", [])
    artifacts = bundles.get("artifacts", [])
    research = bundles.get("research", [])

    if not decisions:
        return "No decision found in trace."

    decision = decisions[0]  # Root is usually the decision
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
        lines.append(f" \u251c\u2500\u2500 \U0001f4c4 Artifact: {art_title}")

    for r in research:
        r_title = r.get("title", "Research Note")
        lines.append(f" \u251c\u2500\u2500 \U0001f50d Research: {r_title}")

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
            lines.append(f"- \U0001f4c4 {link}")

        for r in research:
            r_title = r.get("title", "Research Note")
            claims = r.get("claims", [])
            lines.append(f"- \U0001f50d **{r_title}**")
            for c in claims:
                lines.append(f"  - {c}")

    lines.append("")
    lines.append("---")
    lines.append(
        "<sub>Generated from git-portable Rekall state (safe-to-commit).</sub>"
    )

    return "\n".join(lines)


def find_relevant_decision(store: StateStore, pr_number: str) -> str:
    artifacts = store._load_jsonl("artifacts.jsonl")
    pr_artifact = next(
        (
            a
            for a in artifacts
            if a.get("artifact_type") == "github_pr"
            and str(a.get("ref", {}).get("key")) == str(pr_number)
        ),
        None,
    )

    if pr_artifact:
        links = store._load_jsonl("links.jsonl")
        for link in links:
            u = link.get("from", {})
            v = link.get("to", {})
            if (
                u.get("node_type") == "artifact"
                and u.get("id") == pr_artifact["artifact_id"]
            ) or (
                v.get("node_type") == "artifact"
                and v.get("id") == pr_artifact["artifact_id"]
            ):
                if u.get("node_type") == "decision":
                    return u.get("id")
                if v.get("node_type") == "decision":
                    return v.get("id")

    decisions = store._load_jsonl("decisions.jsonl")
    approved = [d for d in decisions if d.get("status") == "approved"]
    if approved:
        approved.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return approved[0].get("decision_id")

    return None


def post_comment(token: str, repo: str, pr_number: str, body: str):
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            comments = json.loads(resp.read().decode())
    except Exception as e:
        print(f"Failed to fetch comments: {e}")
        comments = []

    comment_id = None
    for c in comments:
        if "<!-- REKALL_DECISION_TRACE -->" in c.get("body", ""):
            comment_id = c.get("id")
            break

    payload = json.dumps({"body": "<!-- REKALL_DECISION_TRACE -->\n" + body}).encode(
        "utf-8"
    )

    if comment_id:
        update_url = f"https://api.github.com/repos/{repo}/issues/comments/{comment_id}"
        req = urllib.request.Request(
            update_url, data=payload, headers=headers, method="PATCH"
        )
        print(f"Updating existing comment {comment_id}")
    else:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        print(f"Posting new comment to PR {pr_number}")

    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Success: {resp.status}")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"Failed to post comment: {e.status} {e.reason}\n{error_body}")


def main():
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    event_path = os.environ.get("GITHUB_EVENT_PATH")

    if not all([token, repo, event_path]):
        print("Missing required environment variables for GitHub action.")
        sys.exit(0)

    with open(event_path, "r") as f:
        event_data = json.load(f)

    pr_number = str(event_data.get("pull_request", {}).get("number"))
    if not pr_number or pr_number == "None":
        print("Not a pull request event.")
        sys.exit(0)

    state_dir = None
    for p in [Path("project-state")]:
        if (p / "manifest.json").exists():
            state_dir = p
            break

    if not state_dir:
        print("No rekall state directory found.")
        sys.exit(0)

    store = StateStore(state_dir)
    decision_id = find_relevant_decision(store, pr_number)

    if not decision_id:
        print("No relevant decision found.")
        sys.exit(0)

    graph = store.trace_graph({"node_type": "decision", "id": decision_id}, depth=2)
    markdown = render_decision_trace(graph)

    post_comment(token, repo, pr_number, markdown)


if __name__ == "__main__":
    main()
