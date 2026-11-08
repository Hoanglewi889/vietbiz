"""Reconcile the originals folder with the documents table. Dry-run unless --apply.

Usage (from services/api):  python -m app.maintenance [--apply]

- committed row + `.<id>.part` + no final file  -> rename to the final name (promote)
- `.<id>.part` with no row, older than an hour  -> delete (only with --apply)
- final file with no row                        -> report only; a human decides

This module deliberately does not import app.main, so it runs without OIDC settings.
"""
from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .database import connection

STALE_AFTER = timedelta(hours=1)


def default_files_root() -> Path:
    return Path(os.getenv('VIETBIZ_DATA_DIR', './.vietbiz-data')).resolve() / 'originals'


def reconcile(files_root: Path | None = None, apply: bool = False, min_age: timedelta = STALE_AFTER, now=None):
    root = (files_root or default_files_root()).resolve()
    now = now or datetime.now(UTC)
    report = {'promoted': [], 'stale_partials': [], 'unreferenced': []}
    if not root.is_dir():
        return report
    with connection() as c:
        rows = {r['id']: (r['organization_id'], r['storage_path'])
                for r in c.execute('SELECT id,organization_id,storage_path FROM documents').fetchall()}
    for org_dir in sorted(root.iterdir()):
        if org_dir.is_symlink() or not org_dir.is_dir():
            continue
        org_real = org_dir.resolve()
        for path in sorted(org_dir.iterdir()):
            if path.is_symlink() or not path.is_file():
                continue
            old_enough = now - datetime.fromtimestamp(path.stat().st_mtime, UTC) > min_age
            if path.name.startswith('.') and path.name.endswith('.part'):
                did = path.name[1:-len('.part')]
                if did in rows:
                    org_id, storage_path = rows[did]
                    dest = Path(storage_path)
                    if (org_id == org_dir.name and dest.parent.resolve() == org_real
                            and dest.name.startswith(did + '.') and not dest.exists()):
                        report['promoted'].append(str(path))
                        if apply:
                            os.replace(path, dest)
                elif old_enough:
                    report['stale_partials'].append(str(path))
                    if apply:
                        path.unlink()
            elif path.stem not in rows and old_enough:
                report['unreferenced'].append(str(path))
    return report


def main(argv=None) -> int:
    apply = '--apply' in (argv if argv is not None else sys.argv[1:])
    result = reconcile(apply=apply)
    for kind, paths in result.items():
        for item in paths:
            print(f'{kind}\t{item}')
    print(('applied' if apply else 'dry-run') + ': ' + ', '.join(f'{k}={len(v)}' for k, v in result.items()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
