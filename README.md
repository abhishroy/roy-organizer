# ROY Organizer

**A privacy-first, safety-first Mac file organizer for humans and developers.**

> **0.1.0 Early Preview:** real-user execution is disabled by default. Use the
> synthetic demo to exercise execute and undo safely.

## What is ROY Organizer?

ROY scans a messy Mac, explains organization suggestions, lets you review every
decision, and validates approved actions immediately before any future move.

`Scan → Explain → Review → Validate → Execute → Undo`

## Why ROY?

ROY is not a blind cleaner. It does not automatically delete or overwrite files.
It understands developer workstations, kubeconfigs, repositories, work data, and
company-managed Macs. Decisions are local, explainable, explicitly approved, and
reversible. Real execution remains unavailable in this Early Preview.

## Features

- Desktop and Downloads review; screenshots, documents, photos, videos, installers
- General versus repository ZIP detection with personal/company/unknown origins
- Exact-hash duplicate candidates and read-only storage analytics
- Zsh, Oh My Zsh, Git, AWS, Kubernetes, SSH, Docker, VS Code, Terraform, Homebrew,
  cloud tooling, AI tooling, projects, and company-security protection
- Explainable proposals, batch review, local plans, deterministic organization score
- Fail-closed open-file state, collisions, source-change checks, transaction metadata
- Sandbox-only execution, undo, doctor, demo, terminal UI, GUI preview
- Optional local Ollama suggestions, off by default; no remote AI

## Developer protection

ROY explicitly protects Zsh, Oh My Zsh, Git, AWS, Kubernetes, SSH, Docker,
Rancher Desktop, OrbStack, VS Code, Terraform, Homebrew, cloud credentials, and AI
development tools. Software-project marker trees are excluded from bulk planning.

## Repository ZIP intelligence

ZIP contents are inspected without extraction or execution. General ZIPs go to
general archive review. Strong repository structure becomes Personal Repository,
Company Repository, or Unknown Repository. Company archives are manual-review only.

## Privacy

Scanning and reports are local. There is no telemetry, cloud requirement, or
filename upload. Private `data/`, `reports/`, and `logs/` are ignored. Optional
Ollama is local-only and disabled by default. See [PRIVACY.md](PRIVACY.md).

## Safety

ROY checks approval, allowed roots, protected sources/destinations, open files,
collisions, size/mtime changes, project membership, and machine profile. It never
silently overwrites. Sandbox moves have metadata-only transaction logs and undo.

## Terminal usage

```bash
roy                  # interactive terminal home
roy scan
roy report
roy review
roy protected
roy duplicates --report
roy score
roy storage
roy status
roy undo             # blocked on real machine in Early Preview
roy doctor
roy demo             # temporary synthetic filesystem only
roy gui              # planning-only Tkinter preview
```

## Installation for developers

```bash
git clone https://github.com/abhishroy/roy-organizer.git
cd roy-organizer
./install.sh
.venv/bin/roy doctor
```

The installer creates only a repository-local virtual environment and launcher,
requires no network or sudo, and does not edit PATH or shell configuration.
Manual packaging alternatives (when build dependencies are available):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
# or: pipx install .
# or: uv tool install .
```

## Non-technical users

The GUI preview supports Scan → choose categories → review → save plan. A future
signed app aims for Download → Open → Scan → Review. Never disable Gatekeeper or SIP.

## Architecture

Scanner → Classifier/Inspectors → Safety Engine → Planner → Validator →
Sandbox Executor → Transactions/Undo, shared by CLI/TUI/GUI. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Sandbox testing

```bash
roy demo
python -m unittest discover -s tests -v
```

The demo generates a fake Mac tree under `/tmp`, moves one synthetic screenshot,
records it, undoes it, verifies original bytes, then removes the temporary tree.

## Limitations

- Early Preview and macOS-focused
- Classification is conservative and imperfect
- Unknown repository origins require review
- Ollama is optional and suggestions are never authoritative
- Real execution remains disabled pending a separately approved pilot

MIT licensed. See [SECURITY.md](SECURITY.md) and [CONTRIBUTING.md](CONTRIBUTING.md).
