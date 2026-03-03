from rekall.core.trace_renderer import render_decision_trace


def test_render_decision_trace():
    graph_result: dict = {
        "bundles": {
            "decision": [
                {
                    "title": "Use PostgreSQL",
                    "tradeoffs": ["Heavier than SQLite", "More operational overhead"],
                    "notes": "We need relational data",
                }
            ],
            "attempts": [
                {
                    "title": "Try SQLite",
                    "status": "failed",
                    "notes": "SQLite couldn't handle concurrent writes well enough",
                },
                {
                    "title": "Setup basic local PG",
                    "status": "success",
                    "notes": "Works perfectly",
                },
            ],
            "artifacts": [
                {
                    "title": "Benchmark Report",
                    "ref": {"provider": "notion", "url": "https://notion.so/bench"},
                }
            ],
            "research": [
                {
                    "title": "DB concurrent writes comparison",
                    "claims": ["PG handles it better", "SQLite locks entire file"],
                }
            ],
        }
    }

    markdown = render_decision_trace(graph_result)

    assert "## Rekall Decision Trace" in markdown
    assert "**Decision**: Use PostgreSQL" in markdown
    assert "We need relational data" in markdown
    assert "Heavier than SQLite" in markdown
    assert "More operational overhead" in markdown

    assert "### Provenance" in markdown
    assert " ├── ❌ Attempt: SQLite couldn't handle concurrent writes well " in markdown
    assert " ├── ✅ Attempt: Works perfectly" in markdown
    assert " ├── 📄 Artifact: Benchmark Report" in markdown
    assert " ├── 🔍 Research: DB concurrent writes comparison" in markdown

    assert "### Linked Attempts" in markdown
    assert (
        "- ❌ **Failed**: SQLite couldn't handle concurrent writes well enough"
        in markdown
    )
    assert "- ✅ **Success**: Works perfectly" in markdown

    assert "### Logged Evidence" in markdown
    assert "[Benchmark Report](https://notion.so/bench)" in markdown

    assert "PG handles it better" in markdown
    assert "SQLite locks entire file" in markdown

    assert "Generated from git-portable Rekall state" in markdown


def test_render_decision_trace_empty():
    graph_result: dict = {}
    markdown = render_decision_trace(graph_result)
    assert markdown == "No decision found in trace."
