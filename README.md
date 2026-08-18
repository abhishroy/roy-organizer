# ROY Organizer

> A private and safe Mac file organizer for humans, developers, and
> everyone whose Desktop has quietly become as messy as my study table with screenshots and files everywhere.

ROY helps you tidy files on your Mac without behaving like an overconfident robot
intern. It looks first, explains what it found, asks what you want, and only acts
after you approve the plan.

Today, ROY’s most established workflow for real files is focused on **screenshots**.
It can find them inside Desktop, Downloads, Documents, Pictures, and Movies. It also
searches nested folders and organizes everything into one clean home:

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

Controlled image execution is also available as an Early Preview. It uses the same
approval, validation, journaling, verification, and undo protections as screenshots.
Other categories remain planning only while they are introduced one at a time.

To prepare an image plan, run `roy review`, choose Images, review the proposals, and
save the plan. Then use `roy execute --images`. ROY requires the exact confirmation
phrase `EXECUTE IMAGES`. Verify with `roy verify --last` and restore the run with
`roy undo --images` if needed.

Images are not dropped into one giant folder. ROY sorts them by useful local
signals and then by year and month:

```text
Pictures/Organized/
├── Camera/2026/2026-08/
├── WhatsApp/2026/2026-08/
├── Travel/Vacation Norway/2026/2026-08/
└── Other/2026/2026-08/
```

Meaningful image folders such as Travel, Vacation, Holiday, Trip, or a configured
destination name are kept as context. Videos use one simple, neutral structure:

```text
Movies/Organized/2026/2026-08/
```

Controlled video execution uses `roy execute --videos`, requires the exact phrase
`EXECUTE VIDEOS`, and can be restored with `roy undo --videos`.

## 👋 What does ROY actually do?

Think of ROY as a careful file butler:

1. **Scan.** ROY looks through the folders you allow.
2. **Explain.** It tells you what each file appears to be and why.
3. **Review.** You choose what should happen. Nothing is selected by default.
4. **Validate.** ROY checks everything again just before a move.
5. **Confirm.** Important actions require an exact confirmation phrase.
6. **Execute.** Only approved, safe items are moved.
7. **Verify.** ROY confirms that files arrived where expected.
8. **Undo.** If needed, ROY can put a completed screenshot run back.

In short:

```text
Scan → Explain → Review → Validate → Confirm → Move → Verify → Undo
```

No mystery cleanup. No surprise “where did my file go?” treasure hunt.

## ✨ What can it do today?

- Find files recursively, including inside nested folders
- Organize approved screenshots by year and month
- Organize approved Camera, WhatsApp, Travel, and Other images by year and month
- Organize approved videos into simple year and month folders
- Review a small pilot with 20 files before doing a larger screenshot run
- Process large screenshot plans in manageable batches
- Continue past individually blocked files while keeping them untouched
- Detect identical screenshot copies using strong SHA-256 content hashes
- Never overwrite a different file with the same name
- Protect Git repositories and software projects
- Protect work and company files as well as developer configuration
- Protect AWS, Kubernetes, SSH, Zsh, VS Code, Docker, Terraform, and Homebrew data
- Detect duplicate candidates and repository ZIP files
- Record every successful move in a local transaction journal
- Verify completed screenshot runs
- Undo screenshot runs safely
- Review broken or redundant Finder aliases separately
- Move explicitly approved screenshot aliases to Trash instead of deleting forever
- Restore the latest screenshot alias cleanup from Trash

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

### Option A: Homebrew

If Homebrew is already installed, this is the quickest route:

```bash
brew install abhishroy/tap/roy-organizer
organizer doctor
```

You can use either `organizer` or `roy`; they are two names for the same careful
file butler. Installation does not scan, move, rename, or delete anything. ROY also
does not run secretly in the background. You decide when it starts.

Start with:

```bash
organizer scan
organizer review
```

ROY will show what it found and ask what you want to organize. Nothing is chosen
for you, because even a helpful butler should not rearrange the house without asking.

You need:

- A Mac
- Python 3.10 or newer
- About five minutes
- No `sudo`
- No need to disable Gatekeeper, SIP, or any Mac security setting

### Option B: download the ZIP

This is the easiest option for most people.

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

### Option C: install with Git

This option is for developers who already use Git.

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

Scanning only reads your files. ROY looks, counts, and takes notes. It does not
move files.

### Step 2: review

```bash
.venv/bin/roy review
```

Choose **Screenshots**. When ROY asks for a source, leave it blank to include all
configured folders. Review the summary, approve only what you want, then save the
plan.

### Step 3: try the pilot with 20 files

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

## 🧹 Optional Finder alias cleanup

Finder aliases are shortcuts, not screenshots. ROY leaves them alone during normal
screenshot organization.

To review aliases with screenshot names separately:

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

ROY does not empty Trash. Restore the latest alias cleanup run with:

```bash
.venv/bin/roy undo --screenshot-aliases
```

## 🧰 Useful commands

```bash
organizer                                      # open ROY
organizer scan                                 # look through your chosen folders
organizer report                               # show what ROY found
organizer review                               # choose and approve suggestions
organizer protected                            # see what ROY refuses to touch
organizer storage                              # see where storage is being used
organizer score                                # show your organization score
organizer doctor                               # check that ROY is ready

organizer execute --pilot                      # try 20 approved screenshots
organizer execute --screenshots                # organize approved screenshots
organizer execute --images                     # organize approved images
organizer execute --videos                     # organize approved videos
organizer execute --screenshots --retry-blocked

organizer verify --last                        # check the latest move
organizer history                              # show earlier ROY runs
organizer undo --pilot                         # restore the latest pilot
organizer undo --screenshots                   # restore a screenshot run
organizer undo --images                        # restore an image run
organizer undo --videos                        # restore a video run

organizer cleanup --screenshot-aliases         # review Finder aliases for Trash
organizer undo --screenshot-aliases            # restore the latest alias cleanup
```

If you installed ROY from source instead of Homebrew, replace `organizer` with
`.venv/bin/roy` in these examples.

Broad, unrestricted organization remains disabled. ROY currently permits controlled
real execution only for approved Screenshots, Images, and Videos, plus explicit
alias cleanup. Installing ROY never enables automatic or scheduled organization.

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

- `roy_scan.py` handles recursive scanning and inventory statistics.
- `roy_classify.py` handles classification and destination suggestions.
- `roy_inspect.py` inspects kubeconfig files and repository archives.
- `roy_safety.py` protects developer, project, work, and open files.
- `roy_plan.py` stores review plans and decisions.
- `roy_validate.py` performs the final checks before execution.
- `roy_pilot.py` controls screenshot execution, verification, and undo.
- `roy_alias_cleanup.py` handles Finder alias review, Trash, and restoration.
- `roy.py` provides the command line interface.
- `tests/` contains unit tests and temporary filesystem integration tests.

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
- Collision protection and checks for files that changed
- Screenshot duplicate detection confirmed by content hash
- Finder alias review, Trash workflow, and restore
- Developer and company managed Mac protection

Still to come:

- Explicit cleanup for duplicate screenshots confirmed by content hash
- Image, video, document, and archive organization
- Background watch mode
- LaunchAgent integration
- Graphical interface ready for everyday use
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
