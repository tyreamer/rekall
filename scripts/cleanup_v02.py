from pathlib import Path

files_to_delete = [
    "src/rekall/core/hub_sync.py",
    "src/rekall/core/handoff_generator.py",
    "src/rekall/core/trace_renderer.py",
    "src/rekall/core/policy.py",
    "src/rekall/server/dashboard.py"
]

base_dir = Path("d:/Projects/Rekall")

for relative_path in files_to_delete:
    p = base_dir / relative_path
    if p.exists():
        p.unlink()
        print(f"Deleted {relative_path}")
    else:
        print(f"Not found (already deleted?): {relative_path}")
