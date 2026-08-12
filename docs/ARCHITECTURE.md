# Architecture

- `roy_scan`: read-only traversal and inventory
- `roy_classify` / `roy_inspect`: deterministic category, kubeconfig, ZIP logic
- `roy_safety`: profiles, protected paths/projects, open-file snapshot
- `roy_plan`: source/category filters, decisions, persistent JSON plans
- `roy_validate`: fail-closed pre-operation checks
- `roy_executor`: `/tmp`-restricted moves and undo records
- `roy_transactions`: legacy transaction compatibility
- `roy_tui` / `roy_gui`: presentation using shared business logic
- `roy_analytics`: explanations, organization score, storage
- `roy_ai`: optional local-only suggestion adapter
- `roy_config`, `roy_doctor`, `roy_demo`, `roy.py`: configuration and interfaces

Real execution is deliberately not wired into the user-root CLI.
