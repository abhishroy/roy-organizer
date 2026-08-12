# ROY Organizer

ROY Organizer is a safety-first, local macOS file organizer. It scans configured
folders recursively, builds explainable plans, lets you review every proposed
change, validates files again immediately before execution, records each move,
verifies the result, and supports undo.

ROY is designed for personal, developer, and company-managed Macs. Normal broad
execution remains disabled: real execution is limited to explicit, approved
screenshot workflows.

## ✨ Features

- Recursive scanning across Desktop, Downloads, Documents, Pictures, and Movies
- Rule-based classification with optional local AI suggestions via Ollama
- Safe, persistent planning workflow
- Interactive review before execution
- Protected Git repository and software-project detection
- Company/work-data and developer-configuration protection
- Duplicate candidate detection
- Centralized screenshot organization by capture year and month
- Deterministic, recoverable batch execution
- Durable transaction journaling
- Post-execution filesystem and journal verification
- Collision-safe undo
- Controlled 20-file pilot mode
- Approved screenshot-only production execution

Local AI is optional and disabled by default. ROY does not require cloud inference
and does not upload filenames or file contents.

## 🛡️ Safety Philosophy

ROY never blindly moves files. Every real operation follows:

```text
Scan
→ Review
→ Validation
→ Confirmation
→ Execution
→ Verification
→ Undo (if needed)
```

Before execution, ROY rejects stale plans if any referenced source has disappeared.
Every operation must already be explicitly approved and is validated again directly
before movement. Validation checks source metadata, protected paths, repositories,
work data, symlinks, open-file state, allowed destination roots, and collisions.

ROY never overwrites an existing destination and screenshot modes never delete
files. Successful moves and ROY-created directories are written to a durable local
transaction journal. Verification compares journal state with original and expected
paths. Undo refuses to overwrite a source path that has reappeared and removes only
empty directories that ROY itself recorded creating.

When a screenshot destination already exists, ROY compares stable SHA-256 hashes.
Matching content is reported as `ALREADY_ORGANIZED_DUPLICATE` and left untouched;
different content remains a collision. Screenshot-like Finder aliases are never
deleted during normal organization. The separate cleanup command resolves them via
local metadata and, after exact confirmation, moves only broken or redundant aliases
to a journaled folder in the current user's Trash. ROY never empties Trash.

## 📸 Screenshot Organization

ROY gives screenshots a single organized home:

```text
Pictures/
└── Screenshots/
    ├── 2023/
    ├── 2024/
    ├── 2025/
    └── 2026/
        ├── 2026-01/
        ├── 2026-02/
        └── ...
```

Screenshots may originate anywhere beneath configured Desktop, Downloads,
Documents, Pictures, or Movies roots. ROY detects them recursively and proposes a
Year → Month destination based on the capture date.

Production screenshot execution uses one Run ID with deterministic internal batches
of up to 100 files. Each batch is journaled independently for interruption recovery,
while verification, history, and undo present the operation as one user-facing run.
If an operation is blocked, ROY leaves it untouched, records its reason in a local
retry report, and continues validating later files. A retry never bypasses safety.

## ⌨️ Current Commands

Run commands from the repository virtual environment:

```bash
python roy.py scan                    # refresh local inventory
python roy.py review                  # create or resume an approved plan
python roy.py execute --pilot         # controlled maximum-20 screenshot pilot
python roy.py execute --screenshots   # all approved screenshots in safe batches
python roy.py execute --screenshots --retry-blocked  # retry only previously blocked files
python roy.py cleanup --screenshot-aliases  # review eligible Finder aliases for Trash
python roy.py verify --last           # verify the latest controlled run
python roy.py undo --pilot            # undo the latest pilot batch
python roy.py undo --screenshots      # preview and undo the latest screenshot run
python roy.py history                 # show screenshot-run history
```

Advanced read-only commands include `report`, `protected`, `duplicates --report`,
`score`, `storage`, `status`, and `doctor`. `organize` and legacy broad execution
paths remain blocked while `planning_only=true`.

## 🔄 Typical Workflow

```bash
cd ~/Projects/roy-organizer
source venv/bin/activate

python roy.py scan
python roy.py review
python roy.py execute --screenshots
# Type exactly: EXECUTE SCREENSHOTS

python roy.py verify --last
python roy.py history
```

If the verified result should be reverted:

```bash
python roy.py undo --screenshots
# Review the run, then type exactly: UNDO SCREENSHOTS
python roy.py verify --last
```

Always generate a fresh scan and plan after files have moved or otherwise changed.

## 🧱 Project Structure

- `roy.py` — CLI, review workflow, summaries, and command routing
- `roy_scan.py` — recursive scanner, inventory statistics, and duplicate discovery
- `roy_classify.py` — deterministic file classification and destination proposals
- `roy_inspect.py` — local kubeconfig and repository-archive inspection
- `roy_safety.py` — protected paths, projects, work data, and open-file detection
- `roy_plan.py` — persistent review plans, decisions, filtering, and grouping
- `roy_validate.py` — fail-closed execution-time validation
- `roy_pilot.py` — controlled pilot and run-based screenshot execution, journal,
  verification, history, and undo
- `roy_transactions.py` — legacy transaction primitives for sandboxed workflows
- `roy_executor.py` / `roy_demo.py` — temporary-directory execution and demo
- `roy_tui.py` / `roy_gui.py` — terminal and planning GUI interfaces
- `tests/` — unit, safety, planner, validator, and filesystem integration tests

Generated plans, scan inventories, reports, and transaction logs stay local and are
excluded from Git.

## 🗺️ Roadmap

Completed:

- Screenshot organizer
- Verification
- Undo
- Pilot mode
- Screenshot execution
- Safe execution-time validation

Future:

- Image organization
- Video organization
- Duplicate cleanup
- Background watch mode
- LaunchAgent integration
- Production GUI
- AI semantic organization

ROY remains macOS-focused and intentionally conservative. Classification can be
imperfect, so review and explicit confirmation remain part of the design.

MIT licensed. See [SECURITY.md](SECURITY.md), [PRIVACY.md](PRIVACY.md), and
[CONTRIBUTING.md](CONTRIBUTING.md).
