import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from rekall.core.state_store import StateStore
from rekall.core.trace_renderer import render_decision_trace


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
