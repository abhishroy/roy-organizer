# ROY Organizer

> A privacy-first, safety-first Mac file organizer for humans, developers, and
> everyone whose Desktop has quietly become a storage strategy.

ROY helps you tidy files on your Mac without behaving like an overconfident robot
intern. It looks first, explains what it found, asks what you want, and only acts
after you approve the plan.

Today, ROY’s real-file workflow is focused on **screenshots**. It can find them
inside Desktop, Downloads, Documents, Pictures, and Movies—even in nested folders—
and organize them into one clean home:

```text
Pictures/
└── Screenshots/
    ├── 2024/
    ├── 2025/
    └── 2026/
        ├── 2026-01/
        ├── 2026-02/
        └── ...
```

ROY is an **Early Preview for macOS**. It is intentionally cautious. That means
you may occasionally hear, “Nope, I’m not touching that.” This is a feature.

## 👋 What does ROY actually do?

Think of ROY as a careful file butler:

1. **Scan** — ROY looks through the folders you allow.
2. **Explain** — it tells you what each file appears to be and why.
3. **Review** — you choose what should happen. Nothing is selected by default.
4. **Validate** — ROY checks everything again just before a move.
5. **Confirm** — important actions require an exact confirmation phrase.
6. **Execute** — only approved, safe items are moved.
7. **Verify** — ROY confirms that files arrived where expected.
8. **Undo** — if needed, ROY can put a completed screenshot run back.

In short:

```text
Scan → Explain → Review → Validate → Confirm → Move → Verify → Undo
```

No mystery cleanup. No surprise “where did my file go?” treasure hunt.

## ✨ What can it do today?

- Find files recursively, including inside nested folders
- Organize approved screenshots by year and month
- Review a small 20-file pilot before doing a larger screenshot run
- Process large screenshot plans in manageable batches
- Continue past individually blocked files while keeping them untouched
- Detect identical screenshot copies using strong SHA-256 content hashes
- Never overwrite a different file with the same name
- Protect Git repositories and software projects
- Protect work/company files and developer configuration
- Protect AWS, Kubernetes, SSH, Zsh, VS Code, Docker, Terraform, and Homebrew data
- Detect duplicate candidates and repository ZIP files
- Record every successful move in a local transaction journal
- Verify completed screenshot runs
- Undo screenshot runs safely
- Review broken or redundant Finder aliases separately
- Move explicitly approved screenshot aliases to Trash instead of deleting forever
- Restore the latest screenshot-alias cleanup from Trash

Optional local AI suggestions through Ollama exist, but they are **off by default**.
ROY works without AI and does not send filenames or file contents to cloud services.

## 🛡️ ROY’s house rules

ROY never blindly moves files.

- **No overwrite:** if a destination contains different data, ROY blocks the move.
- **Same name is not enough:** identical files are confirmed by content hash.
- **No automatic deletion:** ordinary screenshot organization deletes nothing.
- **Protected means protected:** repositories, work data, developer settings, and
  company security tooling stay out of automatic organization.
- **Open files are treated carefully:** if ROY cannot reliably check whether files
  are open, execution fails closed.
- **Stale plans are rejected:** if files changed or disappeared after review, ROY
  asks for a fresh plan.
- **Everything important is journaled:** verification and undo use local records.

ROY is deliberately the friend who asks, “Are you *sure*?” before helping you move
the sofa through a narrow doorway.

## 🚀 Install ROY on your Mac

You need:

- A Mac
- Python 3.10 or newer
- About five minutes
- No `sudo`
- No need to disable Gatekeeper, SIP, or any Mac security setting

### Option A: download the ZIP — easiest for most people

1. Open the [ROY Organizer GitHub page](https://github.com/abhishroy/roy-organizer).
2. Click the green **Code** button.
3. Click **Download ZIP**.
4. Open the downloaded ZIP. macOS will create a folder named something like
   `roy-organizer-master`.
5. Open **Terminal**. You can find it with Spotlight: press `Command + Space`, type
   `Terminal`, and press Return.
6. Type `cd` followed by one space, then drag the ROY folder from Finder into the
   Terminal window. Press Return. It will look similar to:

   ```bash
   cd ~/Downloads/roy-organizer-master
   ```

7. Run the installer:

   ```bash
   sh install.sh
   ```

8. Ask ROY to check its setup:

   ```bash
   .venv/bin/roy doctor
   ```

The installer creates a private Python environment inside the ROY folder. It does
not edit your shell, PATH, global Python installation, or system files.

### Option B: install with Git — for developers

```bash
git clone https://github.com/abhishroy/roy-organizer.git
cd roy-organizer
sh install.sh
.venv/bin/roy doctor
```

If `doctor` reports that Python is missing or too old, install a current Python from
[python.org](https://www.python.org/downloads/macos/) and run `sh install.sh` again.

## 🧭 Your first safe cleanup, step by step

### Step 1: scan

```bash
.venv/bin/roy scan
```

Scanning is read-only. ROY looks, counts, and takes notes. It does not move files.

### Step 2: review

```bash
.venv/bin/roy review
```

Choose **Screenshots**. When ROY asks for a source, leave it blank to include all
configured folders. Review the summary, approve only what you want, then save the
plan.

### Step 3: try the 20-file pilot

```bash
.venv/bin/roy execute --pilot
```

ROY shows the number of files, total size, source folders, destination, and safety
summary. To proceed, type exactly:

```text
EXECUTE PILOT
```

Typing `y`, `yes`, or “go on then, Roy” will not work. Exact means exact.

### Step 4: verify the result

```bash
.venv/bin/roy verify --last
```

Check that ROY reports a consistent transaction log and no anomalies.

### Step 5: undo the pilot if you want

```bash
.venv/bin/roy undo --pilot
```

### Step 6: organize all approved screenshots

Only do this after you are comfortable with the pilot:

```bash
.venv/bin/roy execute --screenshots
```

Type exactly:

```text
EXECUTE SCREENSHOTS
```

ROY processes the plan in batches. A blocked item stays where it is; later safe
items can continue. Blocked items are written to a local retry list.

Afterward:

```bash
.venv/bin/roy verify --last
.venv/bin/roy history
```

To undo the complete screenshot run:

```bash
.venv/bin/roy undo --screenshots
```

Always scan and create a fresh plan after files have moved or changed.

## 🧹 Optional Finder-alias cleanup

Finder aliases are shortcuts, not screenshots. ROY leaves them alone during normal
screenshot organization.

To review screenshot-like aliases separately:

```bash
.venv/bin/roy cleanup --screenshot-aliases
```

ROY lists every alias and separates them into:

- **Broken:** the target no longer exists
- **Redundant:** the target is already under `Pictures/Screenshots`
- **Retained:** the target is somewhere else or the alias is protected

Eligible aliases move to a ROY folder inside your Mac’s Trash only after you type:

```text
DELETE SCREENSHOT ALIASES
```

ROY does not empty Trash. Restore the latest alias-cleanup run with:

```bash
.venv/bin/roy undo --screenshot-aliases
```

## 🧰 Useful commands

```bash
.venv/bin/roy scan                              # look through configured folders
.venv/bin/roy report                            # show the latest scan summary
.venv/bin/roy review                            # create or resume a plan
.venv/bin/roy execute --pilot                   # move at most 20 approved screenshots
.venv/bin/roy execute --screenshots             # organize all approved screenshots
.venv/bin/roy execute --screenshots --retry-blocked
.venv/bin/roy verify --last                     # verify the latest controlled run
.venv/bin/roy undo --pilot                      # undo the latest pilot
.venv/bin/roy undo --screenshots                # undo the latest screenshot run
.venv/bin/roy cleanup --screenshot-aliases      # review aliases for Trash
.venv/bin/roy undo --screenshot-aliases         # restore latest alias cleanup
.venv/bin/roy history                           # show screenshot-run history
.venv/bin/roy protected                         # explain protected-file counts
.venv/bin/roy storage                           # show read-only storage information
.venv/bin/roy doctor                            # check the ROY setup
```

Broad, unrestricted organization remains disabled. ROY currently permits controlled
real execution only for approved screenshot workflows and explicit alias cleanup.

## 🔒 Privacy

- Scanning happens locally on your Mac.
- No telemetry is enabled by default.
- No cloud account is required.
- Filenames and file contents are not uploaded.
- Reports, inventories, plans, and journals remain local and are excluded from Git.
- Optional Ollama suggestions run locally and remain disabled unless you enable them.

Your files are your business. ROY is here to organize them, not gossip about them.

## 🧑‍💻 For developers and contributors

ROY separates scanning, classification, safety checks, planning, validation,
execution, transaction logging, and undo. The major modules are:

- `roy_scan.py` — recursive scanning and inventory statistics
- `roy_classify.py` — deterministic classification and destinations
- `roy_inspect.py` — kubeconfig and repository-archive inspection
- `roy_safety.py` — developer, project, work, and open-file protection
- `roy_plan.py` — review plans and decisions
- `roy_validate.py` — final execution-time validation
- `roy_pilot.py` — controlled screenshot execution, verification, and undo
- `roy_alias_cleanup.py` — Finder-alias review, Trash workflow, and restoration
- `roy.py` — command-line interface
- `tests/` — unit and temporary-filesystem integration tests

Run the test suite with:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

All filesystem tests use temporary directories. Generated plans, scan inventories,
reports, and transaction logs are local and gitignored.

For a completely synthetic demonstration:

```bash
.venv/bin/roy demo
```

## 🗺️ Roadmap

Completed:

- Screenshot planning and organization
- Pilot mode and batch execution
- Verification, history, and undo
- Collision and changed-file protection
- Hash-confirmed screenshot duplicate detection
- Finder-alias review, Trash workflow, and restore
- Developer and company-managed Mac protection

Still to come:

- Explicit cleanup for hash-confirmed duplicate screenshots
- Image, video, document, and archive organization
- Background watch mode
- LaunchAgent integration
- Production-ready graphical interface
- Optional local AI semantic organization

## ⚠️ Early Preview limitations

- ROY is currently focused on macOS.
- Real execution is deliberately limited to screenshots and explicit alias cleanup.
- Classification is not perfect; human review remains essential.
- Unknown repository origins require manual review.
- The graphical interface is still a preview; the terminal workflow is the most
  complete experience today.

ROY is MIT licensed. See [SECURITY.md](SECURITY.md), [PRIVACY.md](PRIVACY.md),
[CONTRIBUTING.md](CONTRIBUTING.md), and [docs/INSTALLATION.md](docs/INSTALLATION.md).
