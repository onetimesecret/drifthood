# Procfile

backend: bash -c 'if source .venv/bin/activate 2>/dev/null; then :; elif source "$HOME/.local/venv3.13/bin/activate" 2>/dev/null; then :; else echo "No Python virtualenv found (.venv or \$HOME/.local/venv3.13). Create one before running." >&2; exit 1; fi; exec python run.py'
frontend: pnpm run dev
