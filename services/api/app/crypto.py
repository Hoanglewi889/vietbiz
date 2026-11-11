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

Key rotation: each sealed original names the key that sealed it (`VBX2` header with a key id,
`VIETBIZ_DATA_KEY_ID`, default `k1`). To rotate, set the new key and a new id, move the old
one to `VIETBIZ_DATA_KEYS_RETIRED` (`id:base64,id:base64`) so existing originals still open,
run `python -m app.crypto reseal`, then drop the retired key. Originals from the first format
(`VBX1`, no key id) open with the current key or any retired one.
"""
from __future__ import annotations

import base64
import os
import secrets
import sys
from functools import lru_cache
from pathlib import Path

import re

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b'VBX2'
LEGACY = b'VBX1'  # first format, no key id
NONCE = 12
KEY_ID = re.compile(r'^[A-Za-z0-9._-]{1,32}$')


class UnknownKey(InvalidTag):
    """The original names a key that is neither the current one nor a retired one."""


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


def _key_id(value: str, name: str) -> str:
    if not KEY_ID.match(value):
        raise RuntimeError(f'{name} must be 1-32 letters, digits, ".", "_" or "-"')
    return value


@lru_cache(maxsize=1)
def keyring() -> tuple[str, dict[str, bytes]]:
    """(current key id, every key that may open an original: current first, then retired)."""
    current = _key_id(os.getenv('VIETBIZ_DATA_KEY_ID', 'k1').strip(), 'VIETBIZ_DATA_KEY_ID')
    keys = {current: data_key()}
    for entry in filter(None, (e.strip() for e in os.getenv('VIETBIZ_DATA_KEYS_RETIRED', '').split(','))):
        kid, _, value = entry.partition(':')
        kid = _key_id(kid.strip(), 'VIETBIZ_DATA_KEYS_RETIRED')
        if kid in keys:
            raise RuntimeError(f'Key id {kid} is listed twice')
        keys[kid] = _decode(value)
    return current, keys


def reset_keys() -> None:
    """Forget the cached keys (after the key settings change; used by tests)."""
    data_key.cache_clear()
    keyring.cache_clear()


def _header(kid: str) -> bytes:
    return MAGIC + bytes([len(kid)]) + kid.encode()


def seal(data: bytes, context: str) -> bytes:
    kid, keys = keyring()
    header, nonce = _header(kid), secrets.token_bytes(NONCE)
    return header + nonce + AESGCM(keys[kid]).encrypt(nonce, bytes(data), header + context.encode())


def is_sealed(blob: bytes) -> bool:
    return bytes(blob[:len(MAGIC)]) in (MAGIC, LEGACY)


def sealed_with(blob: bytes) -> str | None:
    """The key id an original was sealed with; '' for the first format, None if not sealed."""
    blob = bytes(blob)
    if blob.startswith(LEGACY):
        return ''
    if blob.startswith(MAGIC):
        n = blob[len(MAGIC)]
        return blob[len(MAGIC) + 1:len(MAGIC) + 1 + n].decode('ascii', 'replace')
    return None


def unseal(blob: bytes, context: str) -> bytes:
    """Open a sealed original; an original stored before encryption is returned as it is."""
    blob = bytes(blob)
    kid, keys = keyring()
    if blob.startswith(LEGACY):
        head = len(LEGACY)
        for key in keys.values():
            try:
                return AESGCM(key).decrypt(blob[head:head + NONCE], blob[head + NONCE:], context.encode())
            except InvalidTag:
                continue
        raise InvalidTag()
    if not blob.startswith(MAGIC):
        return blob
    used = sealed_with(blob)
    if used not in keys:
        raise UnknownKey()
    header = _header(used)
    if not blob.startswith(header):
        raise InvalidTag()
    rest = blob[len(header):]
    return AESGCM(keys[used]).decrypt(rest[:NONCE], rest[NONCE:], header + context.encode())


def needs_reseal(blob: bytes) -> bool:
    return sealed_with(blob) != keyring()[0]


def document_context(org_id: str, doc_id: str) -> str:
    return f'document:{org_id}:{doc_id}'


def statement_context(org_id: str, import_id: str) -> str:
    return f'statement:{org_id}:{import_id}'


def _rewrite(select) -> dict:
    """Seal again every original for which `select(blob)` is true, with the current key.
    An original that no configured key opens is counted as `unreadable` and left as it is,
    so one bad file does not stop the rest."""
    from .database import connection

    counts = {'documents': 0, 'statements': 0, 'unreadable': 0}
    with connection() as db:
        for row in db.execute('SELECT id, organization_id, storage_path FROM documents').fetchall():
            path = Path(row['storage_path'])
            if not path.is_file():
                continue
            blob, context = path.read_bytes(), document_context(row['organization_id'], row['id'])
            if select(blob):
                try:
                    plain = unseal(blob, context)
                except InvalidTag:
                    counts['unreadable'] += 1
                    continue
                temp = path.with_suffix(path.suffix + '.sealing')
                temp.write_bytes(seal(plain, context))
                os.replace(temp, path)
                counts['documents'] += 1
        for row in db.execute('SELECT import_id, organization_id, content FROM bank_import_files').fetchall():
            blob, context = bytes(row['content']), statement_context(row['organization_id'], row['import_id'])
            if select(blob):
                try:
                    plain = unseal(blob, context)
                except InvalidTag:
                    counts['unreadable'] += 1
                    continue
                db.execute('UPDATE bank_import_files SET content=? WHERE import_id=?',
                           (seal(plain, context), row['import_id']))
                counts['statements'] += 1
    return counts


def seal_existing() -> dict:
    """Seal the originals stored before encryption (documents on disk, statements in the DB)."""
    return _rewrite(lambda blob: not is_sealed(blob))


def reseal() -> dict:
    """After a key rotation: seal every original that is not yet under the current key."""
    return _rewrite(needs_reseal)


if __name__ == '__main__':
    command = sys.argv[1] if len(sys.argv) > 1 else ''
    if command == 'new-key':
        print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
    elif command == 'seal-existing':
        print(seal_existing())
    elif command == 'reseal':
        print(reseal())
    else:
        print('usage: python -m app.crypto new-key | seal-existing | reseal', file=sys.stderr)
        sys.exit(2)
