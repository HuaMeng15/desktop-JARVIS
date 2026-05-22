#!/bin/bash
PYTHON_APP="/opt/homebrew/Cellar/python@3.14/3.14.5/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python"
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/venv/bin/activate"
export PYTHONPATH="$("$DIR/venv/bin/python" -c "import site; print(site.getsitepackages()[0])")"
SCRIPT="${1:-$DIR/main.py}"
shift 2>/dev/null
exec "$PYTHON_APP" "$SCRIPT" "$@"
