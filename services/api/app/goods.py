"""Goods lines on purchase invoices and the monthly goods-intake report (CR-9).

Each line keeps what the supplier's invoice says: item code, name, quantity, unit, unit price
(without VAT), VAT rate and line net. A company puts lines into goods groups (beer, spirits,
sweets …); the group chosen once for a supplier's item is remembered in `goods_catalogue` and
reused on that supplier's later invoices ("learned"), never across companies and never over a
manual choice. Lines come from an ISDOC attachment or are entered by hand; nothing is read
from a photo here (that needs an AI service the owner has not approved).

Findings are computed on read, never stored: repeated identical lines, a line whose net is
not quantity × price, and line totals per VAT rate that do not match the invoice's VAT bases.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .archive import supplier_key
from .database import connection

GoodsGroup = Literal['beer', 'wine', 'spirits', 'soft_drinks', 'sweets', 'snacks', 'bakery', 'dairy', 'meat_fish',
                     'fruit_veg', 'frozen', 'dry_goods', 'asian_food', 'tobacco', 'drogerie', 'supplies', 'other']
GROUPS = GoodsGroup.__args__
CENT = Decimal('0.01')
TOLERANCE = Decimal('1.00')  # Kč; a rounding line on a paper invoice stays below this


class LineIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    item_code: str | None = Field(default=None, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    quantity: Decimal = Field(max_digits=14, decimal_places=4)
    unit: str = Field(default='ks', min_length=1, max_length=10)
    unit_price: Decimal = Field(ge=0, max_digits=16, decimal_places=4)
    vat_rate: Literal['0', '10', '12', '15', '21'] | None = None
    net: Decimal | None = Field(default=None, max_digits=16, decimal_places=2)
    goods_group: GoodsGroup | None = None

    @field_validator('item_code', 'name', 'unit', mode='before')
    @classmethod
    def strip(cls, value):
        if isinstance(value, str):
            value = ' '.join(value.split())
            return value or None
        return value

    @field_validator('quantity')
    @classmethod
    def not_zero(cls, value):
        # Negative quantities are returns or credits; zero is a typo.
        if value == 0:
            raise ValueError('quantity must not be zero')
        return value


class LinesIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    lines: list[LineIn] = Field(min_length=1, max_length=500)
    expected_version: int | None = Field(default=None, ge=1)


class GroupIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    goods_group: GoodsGroup


def item_key(code, name):
    """One item = the supplier's code; without a code, the name with spacing and case folded."""
    if code:
        return 'code:' + code.strip().upper()
    return 'name:' + ' '.join(name.casefold().split())


def _plain(value: Decimal) -> str:
    text = format(value.normalize(), 'f')
    return text if '.' not in text else text.rstrip('0').rstrip('.')


def latest_fields(db, org_id, doc_id):
    row = db.execute('SELECT fields FROM document_extractions WHERE organization_id=? AND document_id=? '
                     'ORDER BY version DESC LIMIT 1', (org_id, doc_id)).fetchone()
    return json.loads(row['fields']) if row else None


def _learned(db, org_id, skey, key):
    row = db.execute('SELECT goods_group FROM goods_catalogue WHERE organization_id=? AND supplier_key=? '
                     'AND item_key=?', (org_id, skey, key)).fetchone()
    return row['goods_group'] if row else None


def _remember(db, org_id, uid, skey, key, group, now):
    db.execute('INSERT INTO goods_catalogue(organization_id,supplier_key,item_key,goods_group,updated_by,updated_at) '
               'VALUES(?,?,?,?,?,?) ON CONFLICT(organization_id,supplier_key,item_key) DO UPDATE SET '
               'goods_group=excluded.goods_group,updated_by=excluded.updated_by,updated_at=excluded.updated_at',
               (org_id, skey, key, group, uid, now))


def store_lines(db, org_id, uid, doc_id, lines: list[LineIn], source, expected_version):
    """Replace the document's goods lines. The caller holds the company row lock."""
    fields = latest_fields(db, org_id, doc_id)
    if fields is None:
        raise HTTPException(409, 'Record the invoice data (supplier, number, date) before its goods lines')
    skey = supplier_key(fields) or 'unknown'
    current = db.execute('SELECT version FROM document_line_sets WHERE document_id=? AND organization_id=?',
                         (doc_id, org_id)).fetchone()
    if (current['version'] if current else None) != expected_version:
        raise HTTPException(409, 'The goods lines were changed by someone else; reload them')
    now = datetime.now(timezone.utc).isoformat()
    if current:
        db.execute('DELETE FROM document_lines WHERE document_id=? AND organization_id=?', (doc_id, org_id))
        db.execute('UPDATE document_line_sets SET supplier_key=?,source=?,version=version+1,updated_by=?,'
                   'updated_at=? WHERE document_id=? AND organization_id=?', (skey, source, uid, now, doc_id, org_id))
    else:
        db.execute('INSERT INTO document_line_sets(document_id,organization_id,supplier_key,source,version,'
                   'updated_by,updated_at) VALUES(?,?,?,?,1,?,?)', (doc_id, org_id, skey, source, uid, now))
    keys = [item_key(line.item_code, line.name) for line in lines]
    # Choices made in this set first, so a sibling line of the same item learns them too.
    for line, key in zip(lines, keys):
        if line.goods_group:
            _remember(db, org_id, uid, skey, key, line.goods_group, now)
    for number, (line, key) in enumerate(zip(lines, keys), start=1):
        group, origin = line.goods_group, 'manual' if line.goods_group else None
        if group is None:
            group = _learned(db, org_id, skey, key)
            origin = 'learned' if group else None
        net = line.net if line.net is not None else (line.quantity * line.unit_price).quantize(CENT, ROUND_HALF_UP)
        db.execute('INSERT INTO document_lines(document_id,organization_id,line_no,item_code,item_key,name,quantity,'
                   'unit,unit_price,vat_rate,net,goods_group,group_source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (doc_id, org_id, number, line.item_code, key, line.name, _plain(line.quantity), line.unit,
                    _plain(line.unit_price), line.vat_rate, str(net.quantize(CENT)), group, origin))


def import_goods_lines(db, org_id, uid, doc_id, raw) -> bool:
    """Store ISDOC goods lines inside the upload transaction; unusable lines are skipped whole."""
    if not raw:
        return False
    try:
        lines = [LineIn(**line) for line in raw]
    except ValidationError:
        return False
    store_lines(db, org_id, uid, doc_id, lines, 'isdoc', None)
    return True


def findings(lines, fields):
    out = []
    seen = defaultdict(list)
    for line in lines:
        seen[(line['item_key'], line['quantity'], line['unit_price'])].append(line['line_no'])
        computed = (Decimal(line['quantity']) * Decimal(line['unit_price'])).quantize(CENT, ROUND_HALF_UP)
        if abs(computed - Decimal(line['net'])) > CENT:
            out.append({'code': 'line_net_mismatch', 'lines': [line['line_no']],
                        'detail': {'computed': str(computed), 'stated': line['net']}})
    for numbers in seen.values():
        if len(numbers) > 1:
            out.append({'code': 'duplicate_line', 'lines': numbers, 'detail': {}})
    bases = {}
    for vat in (fields or {}).get('lines') or []:
        if vat.get('rate') is not None and vat.get('base') is not None:
            rate = Decimal(vat['rate'])
            bases[rate] = bases.get(rate, Decimal('0')) + Decimal(vat['base'])
    if bases:
        sums = defaultdict(Decimal)
        for line in lines:
            sums[Decimal(line['vat_rate'] or 0)] += Decimal(line['net'])
        for rate in sorted(set(bases) | set(sums)):
            stated, counted = bases.get(rate, Decimal('0')), sums.get(rate, Decimal('0'))
            if abs(stated - counted) > TOLERANCE:
                out.append({'code': 'rate_total_mismatch', 'lines': [],
                            'detail': {'rate': _plain(rate), 'invoice_base': str(stated.quantize(CENT)),
                                       'lines_net': str(counted.quantize(CENT))}})
    return sorted(out, key=lambda f: (f['code'], f['lines']))


def _lines(db, org_id, doc_id):
    return [dict(r) for r in db.execute(
        'SELECT line_no,item_code,item_key,name,quantity,unit,unit_price,vat_rate,net,goods_group,group_source '
        'FROM document_lines WHERE document_id=? AND organization_id=? ORDER BY line_no', (doc_id, org_id))]


def _payload(db, org_id, doc_id):
    head = db.execute('SELECT supplier_key,source,version,updated_by,updated_at FROM document_line_sets '
                      'WHERE document_id=? AND organization_id=?', (doc_id, org_id)).fetchone()
    lines = _lines(db, org_id, doc_id)
    by_rate = defaultdict(Decimal)
    for line in lines:
        by_rate[line['vat_rate'] or '0'] += Decimal(line['net'])
    return {'version': head['version'] if head else None, 'source': head['source'] if head else None,
            'updated_at': head['updated_at'] if head else None, 'lines': lines,
            'net_by_rate': {rate: str(total.quantize(CENT)) for rate, total in sorted(by_rate.items())},
            'findings': findings(lines, latest_fields(db, org_id, doc_id)) if lines else [],
            'groups': list(GROUPS)}


def build_router(current_user, authorize, audit):
    router = APIRouter(prefix='/v1/organizations/{org_id}', tags=['Goods lines'])
    roles = ('owner', 'accountant')

    def scope(db, uid, org_id, doc_id):
        authorize(db, uid, org_id, roles)
        if not db.execute('SELECT 1 FROM documents WHERE id=? AND organization_id=?', (doc_id, org_id)).fetchone():
            raise HTTPException(404, 'Document not found')

    @router.get('/documents/{doc_id}/lines')
    def read_lines(org_id: str, doc_id: str, uid: str = Depends(current_user)):
        with connection() as db:
            scope(db, uid, org_id, doc_id)
            return _payload(db, org_id, doc_id)

    @router.put('/documents/{doc_id}/lines')
    def save_lines(org_id: str, doc_id: str, body: LinesIn, uid: str = Depends(current_user)):
        with connection() as db:
            scope(db, uid, org_id, doc_id)
            db.execute('UPDATE organizations SET id=id WHERE id=?', (org_id,))
            store_lines(db, org_id, uid, doc_id, body.lines, 'manual', body.expected_version)
            audit(db, org_id, uid, 'document.lines_saved', doc_id)
            return _payload(db, org_id, doc_id)

    @router.put('/documents/{doc_id}/lines/{line_no}/group')
    def set_group(org_id: str, doc_id: str, line_no: int, body: GroupIn, uid: str = Depends(current_user)):
        now = datetime.now(timezone.utc).isoformat()
        with connection() as db:
            scope(db, uid, org_id, doc_id)
            db.execute('UPDATE organizations SET id=id WHERE id=?', (org_id,))
            line = db.execute('SELECT l.item_key, s.supplier_key FROM document_lines l JOIN document_line_sets s '
                              'ON s.document_id=l.document_id WHERE l.document_id=? AND l.organization_id=? '
                              'AND l.line_no=?', (doc_id, org_id, line_no)).fetchone()
            if line is None:
                raise HTTPException(404, 'Line not found')
            db.execute("UPDATE document_lines SET goods_group=?, group_source='manual' WHERE document_id=? "
                       'AND organization_id=? AND line_no=?', (body.goods_group, doc_id, org_id, line_no))
            _remember(db, org_id, uid, line['supplier_key'], line['item_key'], body.goods_group, now)
            # The same supplier's item elsewhere follows, unless a person chose its group there.
            changed = db.execute(
                "UPDATE document_lines SET goods_group=?, group_source='learned' WHERE organization_id=? "
                "AND item_key=? AND (group_source IS NULL OR group_source='learned') AND document_id IN "
                '(SELECT document_id FROM document_line_sets WHERE organization_id=? AND supplier_key=?)',
                (body.goods_group, org_id, line['item_key'], org_id, line['supplier_key'])).rowcount
            audit(db, org_id, uid, 'goods.group_set', doc_id)
            return {**_payload(db, org_id, doc_id), 'also_updated': changed}

    @router.get('/goods')
    def goods_report(org_id: str, month: str | None = Query(None, pattern=r'^\d{4}-(0[1-9]|1[0-2])$'),
                     year: int | None = Query(None, ge=2000, le=2100), uid: str = Depends(current_user)):
        """Goods bought per group and per supplier, by the invoice's supply date (else issue date)."""
        with connection() as db:
            authorize(db, uid, org_id, roles)
            docs = db.execute(
                "SELECT s.document_id, s.supplier_key FROM document_line_sets s JOIN documents d ON d.id=s.document_id "
                "AND d.organization_id=s.organization_id WHERE s.organization_id=? AND d.status<>'rejected'",
                (org_id,)).fetchall()
            heads = {d['document_id']: (d['supplier_key'], latest_fields(db, org_id, d['document_id'])) for d in docs}
            lines = db.execute('SELECT document_id,item_key,item_code,name,quantity,unit,net,goods_group '
                               'FROM document_lines WHERE organization_id=?', (org_id,)).fetchall()
        groups = defaultdict(lambda: {'totals': defaultdict(Decimal), 'quantity': defaultdict(Decimal), 'lines': 0})
        suppliers = defaultdict(lambda: {'name': '', 'totals': defaultdict(Decimal), 'groups': defaultdict(Decimal)})
        items = defaultdict(lambda: {'name': '', 'code': None, 'group': None, 'quantity': defaultdict(Decimal),
                                     'totals': defaultdict(Decimal)})
        months = defaultdict(lambda: defaultdict(Decimal))
        documents = set()
        for line in lines:
            skey, fields = heads.get(line['document_id'], (None, None))
            if fields is None:
                continue
            day = fields.get('supply_date') or fields.get('issue_date') or ''
            if (month and not day.startswith(month)) or (year and not day.startswith(str(year))):
                continue
            currency, net = fields.get('currency') or 'CZK', Decimal(line['net'])
            group = line['goods_group']
            documents.add(line['document_id'])
            g = groups[group]
            g['totals'][currency] += net
            g['quantity'][line['unit']] += Decimal(line['quantity'])
            g['lines'] += 1
            s = suppliers[skey]
            s['name'] = s['name'] or (fields.get('supplier_name') or '').split(',')[0].strip()
            s['totals'][currency] += net
            if currency == 'CZK':
                s['groups'][group or 'none'] += net
            item = items[(skey, line['item_key'])]
            item.update(name=line['name'], code=line['item_code'], group=group)
            item['quantity'][line['unit']] += Decimal(line['quantity'])
            item['totals'][currency] += net
            if currency == 'CZK' and day[:7]:
                months[day[:7]][group or 'none'] += net

        def money(totals):
            return {c: str(v.quantize(CENT)) for c, v in sorted(totals.items())}

        def amounts(values):
            return {u: _plain(v) for u, v in sorted(values.items())}

        czk = lambda totals: totals.get('CZK', Decimal('0'))
        return {
            'month': month, 'year': year, 'documents': len(documents),
            'groups': [{'group': key, 'totals': money(v['totals']), 'quantity': amounts(v['quantity']),
                        'lines': v['lines']}
                       for key, v in sorted(groups.items(), key=lambda kv: (kv[0] is None, -czk(kv[1]['totals'])))],
            'suppliers': [{'key': key, 'name': v['name'], 'totals': money(v['totals']),
                           'groups': {g: str(n.quantize(CENT)) for g, n in sorted(v['groups'].items())}}
                          for key, v in sorted(suppliers.items(), key=lambda kv: -czk(kv[1]['totals']))],
            'top_items': [{'supplier_key': key[0], 'code': v['code'], 'name': v['name'], 'group': v['group'],
                           'quantity': amounts(v['quantity']), 'totals': money(v['totals'])}
                          for key, v in sorted(items.items(), key=lambda kv: -czk(kv[1]['totals']))[:20]],
            'months': {m: {g: str(n.quantize(CENT)) for g, n in sorted(v.items())} for m, v in sorted(months.items())},
            'uncategorised_lines': groups[None]['lines'] if None in groups else 0,
            'groups_available': list(GROUPS),
        }

    return router
