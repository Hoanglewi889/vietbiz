"""Encryption at rest for stored originals: uploaded documents and bank statement files.

Each original is sealed with AES-256-GCM before it is written (to disk or to the database) and
opened only when an authorised request reads it. The associated data names the record
(`document:<org>:<id>`, `statement:<org>:<id>`), so a sealed file copied onto another record or
another company does not open.

Key: `VIETBIZ_DATA_KEY`, 32 random bytes in base64 (`python -m app.crypto new-key`). Only in
development and test, and only when that variable is unset, a key file is created in the data
directory (`.data-key`, mode 0600) so the prototype runs without setup; a key kept beside the
data protects a stolen backup of the database alone, not a stolen disk. Back the key up apart
from the data: without it the originals cannot be read.

Originals written before this change have no header and are read as they are; run
`python -m app.crypto seal-existing` once to seal them.
"""
from __future__ import annotations

import base64
import os
import secrets
import sys
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b'VBX1'
NONCE = 12


def _data_dir() -> Path:
    return Path(os.getenv('VIETBIZ_DATA_DIR', './.vietbiz-data')).resolve()


def _decode(value: str) -> bytes:
    try:
        raw = base64.urlsafe_b64decode(value.strip() + '=' * (-len(value.strip()) % 4))
    except (ValueError, TypeError):
        raise RuntimeError('VIETBIZ_DATA_KEY is not base64') from None
    if len(raw) != 32:
        raise RuntimeError('VIETBIZ_DATA_KEY must be 32 bytes (base64)')
    return raw


@lru_cache(maxsize=1)
def data_key() -> bytes:
    value = os.getenv('VIETBIZ_DATA_KEY', '')
    if value:
        return _decode(value)
    if os.getenv('VIETBIZ_ENV', 'development').strip().lower() not in {'development', 'test'}:
        raise RuntimeError('VIETBIZ_DATA_KEY is required outside development/test')
    path = _data_dir() / '.data-key'
    path.parent.mkdir(parents=True, exist_ok=True)
    _create_key_file(path)
    return _decode(path.read_text())


def _create_key_file(path: Path) -> None:
    """Publish a fully written key file, once. Codex review, PR #21: the key is written to a
    private temporary file first and then hard-linked into place, so another worker starting
    at the same moment sees either no key file or a complete one, never an empty one."""
    if path.exists():
        return
    temp = path.with_name(f'.data-key.{secrets.token_hex(8)}.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, base64.urlsafe_b64encode(secrets.token_bytes(32)))
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.link(temp, path)  # atomic; fails if another worker published first
    except FileExistsError:
        pass
    finally:
        temp.unlink(missing_ok=True)


def seal(data: bytes, context: str) -> bytes:
    nonce = secrets.token_bytes(NONCE)
    return MAGIC + nonce + AESGCM(data_key()).encrypt(nonce, bytes(data), context.encode())


def is_sealed(blob: bytes) -> bool:
    return bytes(blob[:len(MAGIC)]) == MAGIC


def unseal(blob: bytes, context: str) -> bytes:
    """Open a sealed original; an original stored before encryption is returned as it is."""
    blob = bytes(blob)
    if not is_sealed(blob):
        return blob
    head = len(MAGIC)
    return AESGCM(data_key()).decrypt(blob[head:head + NONCE], blob[head + NONCE:], context.encode())


def document_context(org_id: str, doc_id: str) -> str:
    return f'document:{org_id}:{doc_id}'


def statement_context(org_id: str, import_id: str) -> str:
    return f'statement:{org_id}:{import_id}'


def seal_existing() -> dict:
    """Seal the originals stored before encryption (documents on disk, statements in the DB)."""
    from .database import connection

    counts = {'documents': 0, 'statements': 0}
    with connection() as db:
        for row in db.execute('SELECT id, organization_id, storage_path FROM documents').fetchall():
            path = Path(row['storage_path'])
            if path.is_file() and not is_sealed(path.read_bytes()[:len(MAGIC)]):
                sealed = seal(path.read_bytes(), document_context(row['organization_id'], row['id']))
                temp = path.with_suffix(path.suffix + '.sealing')
                temp.write_bytes(sealed)
                os.replace(temp, path)
                counts['documents'] += 1
        for row in db.execute('SELECT import_id, organization_id, content FROM bank_import_files').fetchall():
            if not is_sealed(row['content']):
                db.execute('UPDATE bank_import_files SET content=? WHERE import_id=?',
                           (seal(row['content'], statement_context(row['organization_id'], row['import_id'])),
                            row['import_id']))
                counts['statements'] += 1
    return counts


if __name__ == '__main__':
    command = sys.argv[1] if len(sys.argv) > 1 else ''
    if command == 'new-key':
        print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
    elif command == 'seal-existing':
        print(seal_existing())
    else:
        print('usage: python -m app.crypto new-key | seal-existing', file=sys.stderr)
        sys.exit(2)
