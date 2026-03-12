from pathlib import Path

files_to_delete = [
    "tests/test_hub_sync.py",
    "tests/test_policy.py",
    "tests/test_trace_renderer.py"
]

base_dir = Path("d:/Projects/Rekall")

for relative_path in files_to_delete:
    p = base_dir / relative_path
    if p.exists():
        p.unlink()
        print(f"Deleted {relative_path}")
