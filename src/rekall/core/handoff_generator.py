from rekall.core.state_store import StateStore


def generate_boot_brief(store: StateStore) -> str:
    """
    Synthesizes project state to create a 1-2 page boot_brief.md.
    Contains goal, status, blockers, and next steps extracted from the latest project state.
    """
    lines = []

    # Project Goal / Info
    project_id = store.project_config.get("project_id", "Unknown Project")
    repo_url = store.project_config.get("repo_url", "N/A")
    lines.append(f"# Boot Brief: {project_id}")
    lines.append(f"**Repository**: {repo_url}")

    links = store.project_config.get("links", [])
    if links:
        lines.append("")
        lines.append("## Project Links")
        for link in links:
            lines.append(
                f"- **{link.get('type', 'link')}**: [{link.get('label', 'URL')}]({link.get('url', '')})"
            )

    lines.append("")

    lines.append("## Project Goal")
    description = store.project_config.get("description", "No description provided.")
    lines.append(description)
    lines.append("")

    # Status Analysis
    lines.append("## Project Status")

    total = len(store.work_items)
    todo = sum(1 for wi in store.work_items.values() if wi.get("status") == "todo")
    in_progress = sum(
        1 for wi in store.work_items.values() if wi.get("status") == "in_progress"
    )
    done = sum(1 for wi in store.work_items.values() if wi.get("status") == "done")
    blocked = sum(
        1 for wi in store.work_items.values() if wi.get("status") == "blocked"
    )

    lines.append(f"- **Total Work Items**: {total}")
    lines.append(f"- **Done**: {done}")
    lines.append(f"- **In Progress**: {in_progress}")
    lines.append(f"- **Blocked**: {blocked}")
    lines.append(f"- **Todo**: {todo}")
    lines.append("")

    # Blockers
    lines.append("## Blockers & Active Issues")
    blocker_wids = [
        wid for wid, wi in store.work_items.items() if wi.get("status") == "blocked"
    ]
    if blocker_wids:
        for wid in blocker_wids:
            wi = store.work_items[wid]
            title = wi.get("title", "Untitled")
            # Discover what it's blocked by
            deps = wi.get("dependencies", {}).get("blocked_by", [])
            dep_str = f" (*Blocked by*: {', '.join(deps)})" if deps else ""
            ev_links = wi.get("evidence_links", [])
            ev_str = f" [Evidence: {len(ev_links)}]" if ev_links else ""
            lines.append(f"- **{wid}**: {title}{dep_str}{ev_str}")
            for link in ev_links:
                lines.append(f"  - {link.get('type', 'link')}: {link.get('url', '')}")
    else:
        lines.append("*No items are currently marked as blocked.*")
    lines.append("")

    # Active / In Progress
    lines.append("## Active Work")
    active_wids = [
        wid for wid, wi in store.work_items.items() if wi.get("status") == "in_progress"
    ]
    if active_wids:
        for wid in active_wids:
            wi = store.work_items[wid]
            title = wi.get("title", "Untitled")
            owner = wi.get("owner", "Unassigned")
            claim = wi.get("claim", {})
            claimed_by = claim.get("claimed_by", "Nobody") if claim else "Nobody"
            ev_links = wi.get("evidence_links", [])
            ev_str = f" [Evidence: {len(ev_links)}]" if ev_links else ""
            lines.append(
                f"- **{wid}**: {title} (Owner: {owner}, Claimed: {claimed_by}){ev_str}"
            )
            for link in ev_links:
                lines.append(f"  - {link.get('type', 'link')}: {link.get('url', '')}")
    else:
        lines.append("*No items currently in progress.*")
    lines.append("")

    # Next Steps
    lines.append("## Next Steps (Todos)")
    todo_wids = [
        wid for wid, wi in store.work_items.items() if wi.get("status") == "todo"
    ]
    if todo_wids:
        for wid in todo_wids[:10]:  # Top 10 to keep it brief
            wi = store.work_items[wid]
            title = wi.get("title", "Untitled")
            priority = wi.get("priority", "p2")
            lines.append(f"- [{priority.upper()}] **{wid}**: {title}")
        if len(todo_wids) > 10:
            lines.append(f"- *(...and {len(todo_wids) - 10} more items)*")
    else:
        lines.append("*No pending items.*")
    lines.append("")

    return "\n".join(lines)
