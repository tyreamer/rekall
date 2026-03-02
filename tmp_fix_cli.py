with open('src/rekall/cli.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Update init explicitly
code = code.replace(
    'ensure_state_initialized(store_dir, args.json)',
    'ensure_state_initialized(store_dir, args.json, init_mode=True)'
)

# In cmd_serve, there is a call: ensure_state_initialized(base_dir, is_json=True)
# Ensure we don't accidentally initialize inside serve unless it's explicitly allowed.
# "Only rekall init or project.bootstrap should create structure."
# So serve shouldn't.

# Replace store_dir parsing
code = code.replace('Path(getattr(args, "store_dir", "."))', 'resolve_vault_dir(getattr(args, "store_dir", "."))')
code = code.replace('Path(getattr(args, "store_dir", "project-state"))', 'resolve_vault_dir(getattr(args, "store_dir", "project-state"))')
code = code.replace('base_dir = Path(args.store_dir)', 'base_dir = resolve_vault_dir(args.store_dir)')
code = code.replace('store_dir = Path(args.store_dir)', 'store_dir = resolve_vault_dir(args.store_dir)')

# Special case for cmd_validate and cmd_serve where args.store_dir is processed
code = code.replace('args.store_dir = resolved_store\n\n    base_dir = Path(args.store_dir)', 'args.store_dir = resolved_store\n\n    base_dir = resolve_vault_dir(args.store_dir)')

with open('src/rekall/cli.py', 'w', encoding='utf-8') as f:
    f.write(code)
