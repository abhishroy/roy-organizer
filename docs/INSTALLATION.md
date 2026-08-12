# Installation

Requires macOS and Python 3.10+. Run `./install.sh` for a repository-local `.venv`
and launcher. It needs no network or package index. No sudo or shell edits are
needed. Packaging metadata also supports `pipx install .` and `uv tool install .`
when their build dependencies are available.
Run `.venv/bin/roy doctor` afterward. `uninstall.sh` prints the exact local path to
remove and deletes nothing automatically.
