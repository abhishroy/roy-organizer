# v0.1.0 code audit

The existing flat module layout is retained because it already separates scanning,
classification, inspection, safety, planning, validation, and transactions. Moving
these validated modules into a package would add import and pickle compatibility
risk without improving safety.

Concrete findings:

- `roy.py` is oversized and mixes presentation with command dispatch. New TUI,
  doctor, demo, analytics, and GUI behavior should live in dedicated modules.
- Legacy Phase 1 organizer handlers contain dormant move loops. They remain behind
  `planning_only`; new execution belongs only in the sandbox-restricted executor.
- Configuration loading was duplicated in the CLI and had no schema validation.
  It is now owned by `roy_config.py`.
- `config.yaml` is documentation/reference while `config.json` is the runtime
  source of truth. Both must remain aligned until YAML loading is deliberately added.
- Broad exception handling remains around best-effort filesystem metadata and
  platform commands. Safety-critical validation uses explicit blocked results.
- Scan snapshots use pickle and are local/private. Plans use versioned JSON.
- Execution must never trust scan-time decisions. Validation rechecks mutable state.

No circular dependencies were found in the core modules.
