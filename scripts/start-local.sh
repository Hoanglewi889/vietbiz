#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
project_dir="$PWD"
python3 -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ required"'
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r services/api/requirements.txt
export VIETBIZ_ENV=development
export VIETBIZ_AUTH_MODE=demo
# Always use this dedicated demo directory, not an inherited database URL.
export VIETBIZ_DATA_DIR="$project_dir/.vietbiz-demo"
unset VIETBIZ_DATABASE_URL
cd services/api
"$project_dir/.venv/bin/python" -m alembic upgrade head
printf '\nVietBiz: http://127.0.0.1:8000/workspace/\nUse the sample-data button. Stop with Ctrl+C.\n\n'
exec "$project_dir/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
