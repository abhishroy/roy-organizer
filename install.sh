#!/bin/sh
set -eu
[ "$(uname -s)" = "Darwin" ] || { echo "ROY currently supports macOS."; exit 1; }
PYTHON="${PYTHON:-python3}"
"$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3,10))' || { echo "Python 3.10+ required."; exit 1; }
"$PYTHON" -m venv .venv
.venv/bin/python -m compileall -q roy*.py
cat > .venv/bin/roy <<EOF
#!/bin/sh
exec "$(pwd)/.venv/bin/python" "$(pwd)/roy.py" "\$@"
EOF
chmod +x .venv/bin/roy
echo "Installed development environment at $(pwd)/.venv"
echo "Run: $(pwd)/.venv/bin/roy doctor"
echo "No PATH or shell configuration was changed."
