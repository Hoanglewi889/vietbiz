"""Daily cash close, leakage signals and weekly cash flow (CR-12).

The close compares what is in the till with what should be there:
    expected = opening float + cash income − cash expenses of that day (CZK, cashbook, not voided)
    difference = counted − expected   (negative = cash missing)
The expected amount is stored as it was when the cash was counted, so a later change to the
cashbook shows up as "changed since the close" instead of silently moving the difference.

Leakage signals for a month: days with cash sales but no close, the sum of shortages and
surpluses, and cash or card expenses above a threshold without a document. Weekly cash flow
takes cash and card from the cashbook; bank money comes from imported statements for weeks
that have them (CR-11), otherwise from the cashbook's bank entries, never both.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .database import connection
from .tasks import today_prague

Amount = Annotated[str, Field(pattern=r'^\d{1,9}(\.\d{1,2})?$')]
CENT = Decimal('0.01')
MONTH = r'^\d{4}-(0[1-9]|1[0-2])$'
UNDOCUMENTED_FROM = Decimal('500')


def _money(value):
    return str(Decimal(value).quantize(CENT, ROUND_HALF_UP))


class CloseIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    opening_float: Amount
    counted_cash: Amount
    note: str | None = Field(default=None, max_length=300)
    expected_version: int | None = Field(default=None, ge=1)


def cash_movements(db, org_id, first, last):
    """CZK cash income and expenses per day from the cashbook (voided entries left out)."""
    out = defaultdict(lambda: {'income': Decimal('0'), 'expense': Decimal('0')})
    for row in db.execute("SELECT entry_date, kind, amount FROM cashbook_entries WHERE organization_id=? "
                          "AND method='cash' AND currency='CZK' AND voided_at IS NULL AND entry_date >= ? "
                          'AND entry_date <= ?', (org_id, first, last)):
        out[row['entry_date']][row['kind']] += Decimal(row['amount'])
    return out


def expected_cash(db, org_id, day, opening):
    moves = cash_movements(db, org_id, day, day)[day]
    return Decimal(opening) + moves['income'] - moves['expense']


def _close(row):
    return dict(row) if row else None


CLOSE_COLUMNS = 'id,close_date,opening_float,counted_cash,expected_cash,difference,note,version,closed_by,closed_at'


def build_router(current_user, authorize, audit):
    router = APIRouter(prefix='/v1/organizations/{org_id}', tags=['Cash control'])
    roles = ('owner', 'accountant')

    @router.put('/cash-closes/{close_date}')
    def close_day(org_id: str, close_date: date, body: CloseIn, uid: str = Depends(current_user)):
        if close_date > date.fromisoformat(today_prague()):
            raise HTTPException(422, 'A day is closed once it has happened')
        now, day = datetime.now(timezone.utc).isoformat(), close_date.isoformat()
        with connection() as db:
            authorize(db, uid, org_id, roles)
            expected = expected_cash(db, org_id, day, body.opening_float)
            difference = Decimal(body.counted_cash) - expected
            values = (_money(body.opening_float), _money(body.counted_cash), _money(expected), _money(difference),
                      body.note)
            if body.expected_version is None:
                inserted = db.execute(
                    'INSERT INTO cash_closes(id,organization_id,close_date,opening_float,counted_cash,expected_cash,'
                    'difference,note,version,closed_by,closed_at) VALUES(?,?,?,?,?,?,?,?,1,?,?) '
                    'ON CONFLICT(organization_id,close_date) DO NOTHING',
                    (str(uuid4()), org_id, day, *values, uid, now)).rowcount
                if inserted != 1:
                    raise HTTPException(409, 'This day is already closed; reload to recount it')
            else:
                # A recount names the version it replaces; the check and the write are one statement.
                changed = db.execute(
                    'UPDATE cash_closes SET opening_float=?, counted_cash=?, expected_cash=?, difference=?, note=?, '
                    'version=version+1, closed_by=?, closed_at=? WHERE organization_id=? AND close_date=? AND version=?',
                    (*values, uid, now, org_id, day, body.expected_version)).rowcount
                if changed != 1:
                    raise HTTPException(409, 'The close was changed by someone else; reload it')
            audit(db, org_id, uid, 'cash.closed', None)
            return _close(db.execute(f'SELECT {CLOSE_COLUMNS} FROM cash_closes WHERE organization_id=? AND close_date=?',
                                     (org_id, day)).fetchone())

    @router.get('/cash-control')
    def cash_control(org_id: str, month: str = Query(pattern=MONTH), uid: str = Depends(current_user)):
        first = month + '-01'
        last = (date.fromisoformat(first).replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        today = today_prague()
        with connection() as db:
            authorize(db, uid, org_id, roles)
            moves = cash_movements(db, org_id, first, last.isoformat())
            closes = {r['close_date']: dict(r) for r in db.execute(
                f'SELECT {CLOSE_COLUMNS} FROM cash_closes WHERE organization_id=? AND close_date >= ? AND close_date <= ?',
                (org_id, first, last.isoformat()))}
            previous = db.execute('SELECT close_date, counted_cash FROM cash_closes WHERE organization_id=? '
                                  'AND close_date <= ? ORDER BY close_date DESC LIMIT 1', (org_id, today)).fetchone()
            undocumented = [dict(r) for r in db.execute(
                "SELECT id, entry_date, amount, method, category, counterparty, description FROM cashbook_entries "
                "WHERE organization_id=? AND kind='expense' AND method IN ('cash','card') AND currency='CZK' "
                'AND document_id IS NULL AND voided_at IS NULL AND entry_date >= ? AND entry_date <= ? '
                'ORDER BY entry_date', (org_id, first, last.isoformat()))
                if Decimal(r['amount']) >= UNDOCUMENTED_FROM]
        days, shortage, surplus, missing = [], Decimal('0'), Decimal('0'), []
        for day in sorted(set(moves) | set(closes)):
            move, close = moves.get(day, {'income': Decimal('0'), 'expense': Decimal('0')}), closes.get(day)
            item = {'date': day, 'cash_income': _money(move['income']), 'cash_expense': _money(move['expense']),
                    'close': close, 'changed_since_close': False}
            if close:
                now_expected = Decimal(close['opening_float']) + move['income'] - move['expense']
                item['changed_since_close'] = now_expected != Decimal(close['expected_cash'])
                diff = Decimal(close['difference'])
                shortage += min(diff, Decimal('0'))
                surplus += max(diff, Decimal('0'))
            elif move['income'] > 0 and day < today:
                missing.append(day)  # cash was taken that day and nobody counted the till
            days.append(item)
        return {
            'month': month, 'days': days,
            'totals': {'shortage': _money(shortage), 'surplus': _money(surplus), 'closed_days': len(closes),
                       'days_without_close': missing},
            'undocumented_expenses': undocumented, 'undocumented_from': _money(UNDOCUMENTED_FROM),
            'suggested_opening_float': previous['counted_cash'] if previous else None,
            'suggested_from': previous['close_date'] if previous else None,
        }

    @router.get('/cash-flow')
    def cash_flow(org_id: str, weeks: int = Query(8, ge=1, le=26), uid: str = Depends(current_user)):
        today = date.fromisoformat(today_prague())
        monday = today - timedelta(days=today.weekday())
        start = monday - timedelta(weeks=weeks - 1)
        with connection() as db:
            authorize(db, uid, org_id, roles)
            book = db.execute("SELECT entry_date, kind, method, amount FROM cashbook_entries WHERE organization_id=? "
                              "AND currency='CZK' AND voided_at IS NULL AND entry_date >= ? AND entry_date <= ?",
                              (org_id, start.isoformat(), today.isoformat())).fetchall()
            bank = db.execute("SELECT booked_on, amount FROM bank_transactions WHERE organization_id=? "
                              "AND currency='CZK' AND booked_on >= ? AND booked_on <= ?",
                              (org_id, start.isoformat(), today.isoformat())).fetchall()

        def week_of(iso):
            day = date.fromisoformat(iso)
            return (day - timedelta(days=day.weekday())).isoformat()

        rows = {(start + timedelta(weeks=i)).isoformat(): {
            'cash_in': Decimal('0'), 'cash_out': Decimal('0'), 'card_in': Decimal('0'), 'card_out': Decimal('0'),
            'book_bank_in': Decimal('0'), 'book_bank_out': Decimal('0'), 'stmt_in': Decimal('0'),
            'stmt_out': Decimal('0'), 'stmt': False} for i in range(weeks)}
        for row in book:
            w = rows[week_of(row['entry_date'])]
            prefix = {'cash': 'cash', 'card': 'card', 'bank': 'book_bank'}[row['method']]
            w[f"{prefix}_{'in' if row['kind'] == 'income' else 'out'}"] += Decimal(row['amount'])
        for row in bank:
            w = rows[week_of(row['booked_on'])]
            amount = Decimal(row['amount'])
            w['stmt'] = True
            w['stmt_in' if amount > 0 else 'stmt_out'] += abs(amount)
        out = []
        for week, w in rows.items():
            bank_in, bank_out = (w['stmt_in'], w['stmt_out']) if w['stmt'] else (w['book_bank_in'], w['book_bank_out'])
            money_in = w['cash_in'] + w['card_in'] + bank_in
            money_out = w['cash_out'] + w['card_out'] + bank_out
            out.append({'week_start': week, 'bank_source': 'statement' if w['stmt'] else 'cashbook',
                        'cash': {'in': _money(w['cash_in']), 'out': _money(w['cash_out'])},
                        'card': {'in': _money(w['card_in']), 'out': _money(w['card_out'])},
                        'bank': {'in': _money(bank_in), 'out': _money(bank_out)},
                        'in': _money(money_in), 'out': _money(money_out), 'net': _money(money_in - money_out)})
        return {'weeks': out, 'currency': 'CZK'}

    return router
