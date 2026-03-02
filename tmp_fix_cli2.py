import re

with open('src/rekall/cli.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Make sure we don't apply multiple times
if 'init_mode=True' not in code:
    code = code.replace(
        'ensure_state_initialized(store_dir, args.json)',
        'ensure_state_initialized(store_dir, args.json, init_mode=True)'
    )

    code = code.replace('Path(getattr(args, "store_dir", "."))', 'resolve_vault_dir(getattr(args, "store_dir", "."))')
    code = code.replace('Path(getattr(args, "store_dir", "project-state"))', 'resolve_vault_dir(getattr(args, "store_dir", "project-state"))')
    code = code.replace('base_dir = Path(args.store_dir)', 'base_dir = resolve_vault_dir(args.store_dir)')
    code = code.replace('store_dir = Path(args.store_dir)', 'store_dir = resolve_vault_dir(args.store_dir)')

    code = code.replace('args.store_dir = resolved_store\n\n    base_dir = Path(args.store_dir)', 'args.store_dir = resolved_store\n\n    base_dir = resolve_vault_dir(args.store_dir)')

# Update cmd_serve specifically
code = re.sub(
    r'''    base_dir = resolve_vault_dir\(args.store_dir\)\n    ensure_state_initialized\(base_dir, is_json=True\)\n\n    try:\n        store = StateStore\(base_dir\)\n\n        # Success Criterion: Launch Rekall Dashboard if interactive\n        if sys.stdin.isatty\(\):\n            dashboard_server, port = start_dashboard\(store\)\n            print\(f"\{Theme.ICON_ROCKET\} Rekall Dashboard active at http://127.0.0.1:\{port\}", file=sys.stderr\)\n            print\(f"\{Theme.ICON_INFO\} MCP Server \(stdio\) active and waiting for agent commands...", file=sys.stderr\)\n\n        # Inject store into mcp_server global\n        mcp_server._store = store\n\n        # Launch server loop\n        mcp_server.main\(\)''',
    r'''    base_dir = resolve_vault_dir(args.store_dir)

    try:
        # Success Criterion: Launch Rekall Dashboard if interactive
        if sys.stdin.isatty():
            # If store does not exist, we just skip dashboard or start it later. For now, try initializing if it exists.
            if base_dir.exists() and (base_dir / "manifest.json").exists():
                store = StateStore(base_dir)
                dashboard_server, port = start_dashboard(store)
                print(f"{Theme.ICON_ROCKET} Rekall Dashboard active at http://127.0.0.1:{port}", file=sys.stderr)
            print(f"{Theme.ICON_INFO} MCP Server (stdio) active and waiting for agent commands...", file=sys.stderr)

        # Inject base_dir into mcp_server global so it can lazy init
        mcp_server._base_dir = base_dir

        # Launch server loop
        mcp_server.main()''', code
)

# And cmd_validate mcp wrapper
code = code.replace('args.store_dir = resolved_store\n\n    base_dir = resolve_vault_dir(args.store_dir)\n\n    if not base_dir.exists():', 'args.store_dir = resolved_store\n\n    base_dir = resolve_vault_dir(args.store_dir)\n\n    if not getattr(args, "mcp", False) and not base_dir.exists():')

with open('src/rekall/cli.py', 'w', encoding='utf-8') as f:
    f.write(code)
