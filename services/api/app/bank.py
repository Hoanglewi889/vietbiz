"""Bank statements and payment matching (CR-11).

A statement file (GPC/ABO, the fixed-width format Czech banks export, or a bank CSV) is read
locally; nothing connects to a bank. Movements are stored once even when statements overlap.

Money in is matched to an issued invoice automatically only when the variable symbol is the
invoice's and the amount is the whole remaining balance or part of it (a partial payment).
An overpayment, a payment without a variable symbol or in another currency is left for a
person. Money out is matched by hand to a received document, with suggestions by amount.
A movement can also be marked as needing no document (a bank fee, a transfer between own
accounts). Findings on read: a possible duplicate payment (same direction, amount of at least
100 Kč and counter-account within three days).
"""
from __future__ import annotations

import csv
import io
import json
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .database import connection
from .tasks import today_prague

MAX_FILE = 2 * 1024 * 1024
MAX_ROWS = 5000
CENT = Decimal('0.01')
DUPLICATE_FLOOR = Decimal('100')
DUPLICATE_DAYS = 3
GPC_CURRENCY = {'0203': 'CZK', '0978': 'EUR', '0840': 'USD'}


class StatementError(ValueError):
    pass


# --- parsing --------------------------------------------------------------------------------

def _gpc_date(text):
    text = text.strip()
    if not text or text == '000000':
        return None
    try:
        return datetime.strptime(text, '%d%m%y').date().isoformat()
    except ValueError:
        return None


def _digits(text):
    text = text.strip().lstrip('0')
    return text or None


def parse_gpc(raw: bytes):
    """GPC (ABO) statement: 074 header and 075 movement records, 128 characters each.

    Layout per the Fio GPC description: 075 = account (4–19), counter-account (20–35),
    document number (36–48), amount in haléře (49–60), accounting code (61: 1 debit,
    2 credit, 4 storno of debit, 5 storno of credit), VS (62–71), bank code + KS (72–81),
    SS (82–91), short name (98–117), currency (119–122), date (123–128, DDMMYY).
    """
    text = raw.decode('cp1250', errors='replace')
    rows, statement_date = [], None
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        line = line.ljust(128)
        kind = line[:3]
        if kind == '074':
            statement_date = _gpc_date(line[108:114])
            continue
        if kind != '075':
            continue  # 076/078/079 carry extra text; not needed for matching
        try:
            amount = Decimal(int(line[48:60])) / 100
        except ValueError:
            raise StatementError(f'line {number}: amount is not a number') from None
        code = line[60]
        if code not in '1245':
            raise StatementError(f'line {number}: unknown accounting code {code!r}')
        # Debit and a storno of a credit take money out; credit and a storno of a debit bring it in.
        sign = -1 if code in '15' else 1
        bank_code = line[71:75].strip()
        counter = _digits(line[19:35])
        booked = _gpc_date(line[122:128]) or statement_date
        if booked is None:
            raise StatementError(f'line {number}: no booking date')
        rows.append({
            'account': _digits(line[3:19]), 'bank_ref': _digits(line[35:48]), 'booked_on': booked,
            'amount': (amount * sign).quantize(CENT), 'currency': GPC_CURRENCY.get(line[118:122], line[118:122]),
            'vs': _digits(line[61:71]), 'ks': _digits(line[75:81]), 'ss': _digits(line[81:91]),
            'counter_account': f'{counter}/{bank_code}' if counter and bank_code else counter,
            'counter_name': line[97:117].strip() or None, 'message': None,
        })
    return rows


def _fold(text):
    plain = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode()
    return ' '.join(plain.casefold().replace('"', '').split())


COLUMNS = {
    'booked_on': ('datum', 'datum zauctovani', 'datum pohybu', 'datum provedeni', 'date', 'booking date'),
    'amount': ('objem', 'castka', 'castka v mene uctu', 'amount', 'suma'),
    'currency': ('mena', 'currency'),
    'vs': ('vs', 'variabilni symbol', 'variable symbol'),
    'ks': ('ks', 'konstantni symbol', 'constant symbol'),
    'ss': ('ss', 'specificky symbol', 'specific symbol'),
    'counter_account': ('protiucet', 'cislo protiuctu', 'counter account', 'ucet protistrany'),
    'counter_bank': ('kod banky', 'banka protiuctu', 'kod banky protiuctu', 'bank code'),
    'counter_name': ('nazev protiuctu', 'nazev protistrany', 'protistrana', 'counterparty', 'nazev uctu protistrany'),
    'message': ('zprava pro prijemce', 'zprava', 'poznamka', 'popis', 'message', 'uziv. identifikace'),
    'bank_ref': ('id pohybu', 'id transakce', 'reference', 'transaction id'),
}


def _csv_amount(text):
    value = (text or '').replace('\xa0', '').replace(' ', '')
    if ',' in value and '.' in value:
        value = value.replace('.', '').replace(',', '.') if value.rfind(',') > value.rfind('.') else value.replace(',', '')
    else:
        value = value.replace(',', '.')
    try:
        return Decimal(value).quantize(CENT)
    except InvalidOperation:
        return None


def _csv_date(text):
    text = (text or '').strip()
    for pattern in ('%d.%m.%Y', '%Y-%m-%d', '%d.%m.%y', '%d/%m/%Y'):
        try:
            return datetime.strptime(text.split(' ')[0], pattern).date().isoformat()
        except ValueError:
            continue
    return None


def parse_csv(raw: bytes):
    """A bank CSV export: the header row is found by its column names (Czech or English)."""
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('cp1250', errors='replace')
    sample = text[:4096]
    delimiter = ';' if sample.count(';') >= sample.count(',') else ','
    table = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    header_at, mapping = None, {}
    for index, row in enumerate(table[:30]):
        names = [_fold(cell) for cell in row]
        found = {key: names.index(alias) for key, aliases in COLUMNS.items() for alias in aliases if alias in names}
        if 'booked_on' in found and 'amount' in found:
            header_at, mapping = index, found
            break
    if header_at is None:
        raise StatementError('no header row with a date and an amount column')
    rows = []
    for number, row in enumerate(table[header_at + 1:], start=header_at + 2):
        if not any(cell.strip() for cell in row):
            continue

        def cell(key):
            position = mapping.get(key)
            value = row[position].strip() if position is not None and position < len(row) else ''
            return value or None

        booked, amount = _csv_date(cell('booked_on')), _csv_amount(cell('amount'))
        if booked is None or amount is None:
            raise StatementError(f'line {number}: date or amount not readable')
        counter, bank = cell('counter_account'), cell('counter_bank')
        rows.append({
            'account': None, 'bank_ref': cell('bank_ref'), 'booked_on': booked, 'amount': amount,
            'currency': (cell('currency') or 'CZK').upper()[:3],
            'vs': (cell('vs') or '').lstrip('0') or None, 'ks': cell('ks'), 'ss': cell('ss'),
            'counter_account': f'{counter}/{bank}' if counter and bank and '/' not in counter else counter,
            'counter_name': cell('counter_name'), 'message': cell('message'),
        })
    return rows


def parse_statement(filename: str, raw: bytes):
    if raw.lstrip()[:3] == b'074':
        return 'gpc', parse_gpc(raw)
    return 'csv', parse_csv(raw)


# --- payments and matching ------------------------------------------------------------------

def _vs(row):
    return f"{row['series_year']}{row['sequence']:04d}"


def payments_for(db, org_id, invoice_ids=None):
    """Matched money per issued invoice: {id: {'paid', 'remaining', 'state'}}."""
    rows = db.execute("SELECT id, totals FROM issued_invoices WHERE organization_id=? AND status='issued'",
                      (org_id,)).fetchall()
    paid = defaultdict(Decimal)
    for tx in db.execute("SELECT issued_invoice_id, amount FROM bank_transactions WHERE organization_id=? "
                         "AND status='matched' AND issued_invoice_id IS NOT NULL", (org_id,)):
        paid[tx['issued_invoice_id']] += Decimal(tx['amount'])
    out = {}
    for row in rows:
        if invoice_ids is not None and row['id'] not in invoice_ids:
            continue
        total = Decimal(json.loads(row['totals'])['total'])
        got = paid[row['id']]
        state = 'unpaid' if got == 0 else 'paid' if got == total else 'overpaid' if got > total else 'partial'
        out[row['id']] = {'paid': str(got.quantize(CENT)), 'remaining': str(max(total - got, Decimal('0')).quantize(CENT)),
                          'state': state}
    return out


def auto_match(db, org_id, uid, now):
    """Match unmatched CZK credits whose VS is an issued invoice's, for at most its remainder."""
    invoices = {_vs(r): r for r in db.execute(
        "SELECT id, series_year, sequence, totals FROM issued_invoices WHERE organization_id=? AND status='issued'",
        (org_id,))}
    matched = 0
    for tx in db.execute("SELECT id, amount, vs FROM bank_transactions WHERE organization_id=? AND status='unmatched' "
                         "AND currency='CZK' AND vs IS NOT NULL ORDER BY booked_on, id", (org_id,)).fetchall():
        amount = Decimal(tx['amount'])
        invoice = invoices.get(tx['vs'])
        if amount <= 0 or invoice is None:
            continue
        remaining = Decimal(payments_for(db, org_id, {invoice['id']})[invoice['id']]['remaining'])
        if amount > remaining:
            continue  # an overpayment is a person's call
        db.execute("UPDATE bank_transactions SET status='matched', issued_invoice_id=?, matched_by='auto', "
                   'version=version+1, updated_by=?, updated_at=? WHERE id=? AND organization_id=?',
                   (invoice['id'], uid, now, tx['id'], org_id))
        matched += 1
    return matched


def _dedupe_key(row):
    if row['bank_ref']:
        parts = (row['account'] or '', 'ref', row['bank_ref'], str(row['amount']), row['booked_on'])
    else:
        parts = (row['account'] or '', row['booked_on'], str(row['amount']), row['vs'] or '',
                 row['counter_account'] or '', row['counter_name'] or '', row['message'] or '')
    return sha256('|'.join(parts).encode()).hexdigest()


def duplicate_flags(rows):
    """Possible duplicate payments: same direction and amount (≥ 100) and counterparty, ≤ 3 days apart."""
    groups = defaultdict(list)
    for row in rows:
        amount = Decimal(row['amount'])
        party = row['counter_account'] or (row['counter_name'] or '').casefold()
        if abs(amount) >= DUPLICATE_FLOOR and party:
            groups[(amount, row['currency'], party)].append(row)
    flagged = defaultdict(list)
    for members in groups.values():
        members.sort(key=lambda r: r['booked_on'])
        for a, b in zip(members, members[1:]):
            if (date.fromisoformat(b['booked_on']) - date.fromisoformat(a['booked_on'])).days <= DUPLICATE_DAYS:
                flagged[a['id']].append(b['id'])
                flagged[b['id']].append(a['id'])
    return flagged


COLUMNS_OUT = ('id,account,bank_ref,booked_on,amount,currency,vs,ks,ss,counter_account,counter_name,message,'
               'status,issued_invoice_id,document_id,matched_by,note,version,updated_at')


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=1)
    issued_invoice_id: str | None = Field(default=None, max_length=64)
    document_id: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=300)


class MatchIn(Decision):
    @model_validator(mode='after')
    def one_target(self):
        if bool(self.issued_invoice_id) == bool(self.document_id):
            raise ValueError('match either an issued invoice or a received document')
        return self


def build_router(current_user, authorize, audit):
    router = APIRouter(prefix='/v1/organizations/{org_id}/bank', tags=['Bank statements'])
    roles = ('owner', 'accountant')

    @router.post('/imports', status_code=201)
    async def import_statement(org_id: str, file: UploadFile = File(...), uid: str = Depends(current_user)):
        with connection() as db:
            authorize(db, uid, org_id, roles)
        raw = await file.read(MAX_FILE + 1)
        if len(raw) > MAX_FILE:
            raise HTTPException(413, 'Statement larger than 2 MB')
        if not raw.strip():
            raise HTTPException(422, 'Empty statement')
        try:
            fmt, rows = parse_statement(file.filename or '', raw)
        except StatementError as error:
            raise HTTPException(422, {'code': 'statement_unreadable', 'reason': str(error)}) from None
        if len(rows) > MAX_ROWS:
            raise HTTPException(422, {'code': 'statement_too_long', 'reason': f'more than {MAX_ROWS} movements'})
        digest, now = sha256(raw).hexdigest(), datetime.now(timezone.utc).isoformat()
        with connection() as db:
            authorize(db, uid, org_id, roles)
            db.execute('UPDATE organizations SET id=id WHERE id=?', (org_id,))
            if db.execute('SELECT 1 FROM bank_imports WHERE organization_id=? AND sha256=?', (org_id, digest)).fetchone():
                raise HTTPException(409, {'code': 'statement_already_imported'})
            import_id = str(uuid4())
            db.execute('INSERT INTO bank_imports(id,organization_id,filename,format,sha256,rows,imported_by,imported_at) '
                       'VALUES(?,?,?,?,?,?,?,?)',
                       (import_id, org_id, (file.filename or 'statement')[:200], fmt, digest, len(rows), uid, now))
            added = 0
            for row in rows:
                inserted = db.execute(
                    'INSERT INTO bank_transactions(id,organization_id,import_id,account,bank_ref,booked_on,amount,'
                    'currency,vs,ks,ss,counter_account,counter_name,message,dedupe_key,status,version,updated_by,'
                    "updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'unmatched',1,?,?) "
                    'ON CONFLICT(organization_id,dedupe_key) DO NOTHING',
                    (str(uuid4()), org_id, import_id, row['account'], row['bank_ref'], row['booked_on'],
                     str(row['amount']), row['currency'], row['vs'], row['ks'], row['ss'], row['counter_account'],
                     row['counter_name'], (row['message'] or None) and row['message'][:300], _dedupe_key(row), uid, now))
                added += inserted.rowcount
            matched = auto_match(db, org_id, uid, now)
            audit(db, org_id, uid, 'bank.statement_imported', None)
            return {'import_id': import_id, 'format': fmt, 'rows': len(rows), 'added': added,
                    'already_known': len(rows) - added, 'auto_matched': matched}

    @router.get('/transactions')
    def transactions(org_id: str, status: str | None = Query(None, pattern='^(unmatched|matched|ignored)$'),
                     uid: str = Depends(current_user)):
        with connection() as db:
            authorize(db, uid, org_id, roles)
            rows = [dict(r) for r in db.execute(f'SELECT {COLUMNS_OUT} FROM bank_transactions WHERE organization_id=? '
                                                'ORDER BY booked_on DESC, id', (org_id,))]
            invoices = {r['id']: r for r in db.execute(
                "SELECT id, number, series_year, sequence, content, totals FROM issued_invoices "
                "WHERE organization_id=? AND status='issued'", (org_id,))}
            payments = payments_for(db, org_id)
            documents = {}
            for r in db.execute(
                    'SELECT e.document_id, e.fields FROM document_extractions e WHERE e.organization_id=? AND '
                    'e.version=(SELECT MAX(version) FROM document_extractions x WHERE x.document_id=e.document_id '
                    'AND x.organization_id=e.organization_id)', (org_id,)):
                documents[r['document_id']] = json.loads(r['fields'])
        duplicates = duplicate_flags(rows)
        taken_docs = {r['document_id'] for r in rows if r['document_id']}
        out = []
        for row in rows:
            if status and row['status'] != status:
                continue
            row['possible_duplicate_of'] = duplicates.get(row['id'], [])
            amount = Decimal(row['amount'])
            row['suggestions'] = []
            if row['status'] == 'unmatched':
                if amount > 0:
                    for iid, inv in invoices.items():
                        due = Decimal(payments[iid]['remaining'])
                        if due > 0 and (row['vs'] == _vs(inv) or amount == due):
                            row['suggestions'].append({'issued_invoice_id': iid, 'number': inv['number'],
                                                       'customer': json.loads(inv['content'])['customer_name'],
                                                       'remaining': str(due)})
                else:
                    for did, fields in documents.items():
                        if did not in taken_docs and fields.get('total') and Decimal(fields['total']) == -amount:
                            row['suggestions'].append({'document_id': did,
                                                       'supplier': (fields.get('supplier_name') or '').split(',')[0],
                                                       'number': fields.get('document_number'),
                                                       'issue_date': fields.get('issue_date')})
                row['suggestions'] = row['suggestions'][:5]
            if row['issued_invoice_id'] in invoices:
                row['invoice_number'] = invoices[row['issued_invoice_id']]['number']
            out.append(row)
        counts = defaultdict(int)
        for row in rows:
            counts[row['status']] += 1
        return {'items': out, 'counts': dict(counts)}

    def load(db, org_id, tx_id, expected):
        row = db.execute('SELECT id, amount, currency, status, version FROM bank_transactions WHERE id=? '
                         'AND organization_id=?', (tx_id, org_id)).fetchone()
        if row is None:
            raise HTTPException(404, 'Bank movement not found')
        if row['version'] != expected:
            raise HTTPException(409, 'The movement was changed by someone else; reload it')
        return row

    @router.post('/transactions/{tx_id}/match')
    def match(org_id: str, tx_id: str, body: MatchIn, uid: str = Depends(current_user)):
        now = datetime.now(timezone.utc).isoformat()
        with connection() as db:
            authorize(db, uid, org_id, roles)
            db.execute('UPDATE organizations SET id=id WHERE id=?', (org_id,))
            tx = load(db, org_id, tx_id, body.expected_version)
            amount = Decimal(tx['amount'])
            if body.issued_invoice_id:
                if amount <= 0:
                    raise HTTPException(422, 'Only money in can pay an issued invoice')
                if not db.execute("SELECT 1 FROM issued_invoices WHERE id=? AND organization_id=? AND status='issued'",
                                  (body.issued_invoice_id, org_id)).fetchone():
                    raise HTTPException(404, 'Invoice not found')
            else:
                if amount >= 0:
                    raise HTTPException(422, 'Only money out can pay a received document')
                if not db.execute('SELECT 1 FROM documents WHERE id=? AND organization_id=?',
                                  (body.document_id, org_id)).fetchone():
                    raise HTTPException(404, 'Document not found')
            db.execute("UPDATE bank_transactions SET status='matched', issued_invoice_id=?, document_id=?, "
                       "matched_by='manual', note=?, version=version+1, updated_by=?, updated_at=? "
                       'WHERE id=? AND organization_id=?',
                       (body.issued_invoice_id, body.document_id, body.note, uid, now, tx_id, org_id))
            audit(db, org_id, uid, 'bank.matched', body.document_id)
            return dict(db.execute(f'SELECT {COLUMNS_OUT} FROM bank_transactions WHERE id=?', (tx_id,)).fetchone())

    @router.post('/transactions/{tx_id}/ignore')
    def ignore(org_id: str, tx_id: str, body: Decision, uid: str = Depends(current_user)):
        now = datetime.now(timezone.utc).isoformat()
        with connection() as db:
            authorize(db, uid, org_id, roles)
            load(db, org_id, tx_id, body.expected_version)
            db.execute("UPDATE bank_transactions SET status='ignored', issued_invoice_id=NULL, document_id=NULL, "
                       'matched_by=NULL, note=?, version=version+1, updated_by=?, updated_at=? '
                       'WHERE id=? AND organization_id=?', (body.note, uid, now, tx_id, org_id))
            audit(db, org_id, uid, 'bank.ignored', None)
            return dict(db.execute(f'SELECT {COLUMNS_OUT} FROM bank_transactions WHERE id=?', (tx_id,)).fetchone())

    @router.post('/transactions/{tx_id}/unmatch')
    def unmatch(org_id: str, tx_id: str, body: Decision, uid: str = Depends(current_user)):
        now = datetime.now(timezone.utc).isoformat()
        with connection() as db:
            authorize(db, uid, org_id, roles)
            load(db, org_id, tx_id, body.expected_version)
            db.execute("UPDATE bank_transactions SET status='unmatched', issued_invoice_id=NULL, document_id=NULL, "
                       'matched_by=NULL, note=NULL, version=version+1, updated_by=?, updated_at=? '
                       'WHERE id=? AND organization_id=?', (uid, now, tx_id, org_id))
            audit(db, org_id, uid, 'bank.unmatched', None)
            return dict(db.execute(f'SELECT {COLUMNS_OUT} FROM bank_transactions WHERE id=?', (tx_id,)).fetchone())

    return router


def overdue(db, org_id, today=None):
    """Issued invoices past their due date with money still owed, grouped by customer."""
    today = today or today_prague()
    payments = payments_for(db, org_id)
    groups = defaultdict(list)
    for row in db.execute("SELECT id, number, series_year, sequence, content, totals FROM issued_invoices "
                          "WHERE organization_id=? AND status='issued'", (org_id,)):
        content = json.loads(row['content'])
        due, pay = content['due_date'], payments[row['id']]
        if due >= today or Decimal(pay['remaining']) <= 0:
            continue
        days = (date.fromisoformat(today) - date.fromisoformat(due)).days
        key = (content.get('customer_ico') or content['customer_name'].casefold())
        groups[key].append({'id': row['id'], 'number': row['number'], 'variable_symbol': _vs(row),
                            'due_date': due, 'days_overdue': days, 'total': json.loads(row['totals'])['total'],
                            'remaining': pay['remaining'], 'state': pay['state'],
                            'customer_name': content['customer_name'], 'payment_method': content['payment_method']})
    out = []
    for invoices in groups.values():
        invoices.sort(key=lambda i: i['due_date'])
        oldest = max(i['days_overdue'] for i in invoices)
        # Daturo-style steps: a reminder after 3 days, a second after 14, a last one after 30.
        stage = 'last' if oldest >= 30 else 'second' if oldest >= 14 else 'first' if oldest >= 3 else 'friendly'
        out.append({'customer_name': invoices[0]['customer_name'], 'invoices': invoices, 'stage': stage,
                    'days_overdue': oldest,
                    'remaining': str(sum((Decimal(i['remaining']) for i in invoices), Decimal('0')).quantize(CENT))})
    return sorted(out, key=lambda g: -g['days_overdue'])

