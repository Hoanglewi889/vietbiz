"""VAT registration threshold tracker for companies that are not VAT payers (CR-10).

From 1 January 2025 turnover is counted per calendar year (§ 6 ZDPH): above 2 000 000 Kč the
business becomes a payer from 1 January of the next year; above 2 536 500 Kč from the day
after the amount is exceeded. The registration application is due within 10 working days.

The app can only estimate turnover from what it holds: issued invoices by supply date, plus
cash and card sales in the cashbook. Bank income in the cashbook is shown but not added,
because it is usually the payment of an issued invoice already counted. EUR amounts are
listed apart and not converted. The accountant confirms the figure; this is an early warning.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query

from .database import connection
from .tasks import today_prague

NEXT_YEAR = Decimal('2000000')
IMMEDIATE = Decimal('2536500')
WATCH_SHARE = Decimal('0.75')
SOURCE = 'https://financnisprava.gov.cz/assets/cs/prilohy/d-seznam-dani/11977_25_Informace_ke_zmenam_v_platcovstv2025.pdf'
CENT = Decimal('0.01')


def is_vat_payer(db, org_id):
    """None when unknown (no profile at all), else whether the company is a VAT payer."""
    profile = db.execute('SELECT vat_status FROM client_profiles WHERE organization_id=?', (org_id,)).fetchone()
    if profile:
        return profile['vat_status'] in ('monthly', 'quarterly')
    billing = db.execute('SELECT vat_payer FROM billing_profiles WHERE organization_id=?', (org_id,)).fetchone()
    return bool(billing['vat_payer']) if billing else None


def estimate(db, org_id, year: int):
    invoiced = Decimal('0')
    for row in db.execute("SELECT content, totals FROM issued_invoices WHERE organization_id=? AND status='issued'",
                          (org_id,)):
        content, totals = json.loads(row['content']), json.loads(row['totals'])
        if content['supply_date'].startswith(str(year)):
            invoiced += Decimal(totals['total'])
    counter, bank, eur = Decimal('0'), Decimal('0'), Decimal('0')
    for row in db.execute(
            "SELECT amount, currency, method FROM cashbook_entries WHERE organization_id=? AND kind='income' "
            "AND category IN ('sales','services') AND voided_at IS NULL AND entry_date >= ? AND entry_date <= ?",
            (org_id, f'{year}-01-01', f'{year}-12-31')):
        amount = Decimal(row['amount'])
        if row['currency'] != 'CZK':
            eur += amount
        elif row['method'] == 'bank':
            bank += amount
        else:
            counter += amount
    total = invoiced + counter
    status = ('over_immediate' if total > IMMEDIATE else 'over_next_year' if total > NEXT_YEAR
              else 'watch' if total >= NEXT_YEAR * WATCH_SHARE else 'ok')
    return {'year': year, 'invoiced': str(invoiced.quantize(CENT)), 'cash_and_card_sales': str(counter.quantize(CENT)),
            'bank_income_not_added': str(bank.quantize(CENT)), 'eur_income_not_added': str(eur.quantize(CENT)),
            'estimate': str(total.quantize(CENT)), 'share': str((total / NEXT_YEAR).quantize(Decimal('0.001'))),
            'status': status, 'thresholds': {'next_year': str(NEXT_YEAR), 'immediate': str(IMMEDIATE)},
            'source': SOURCE}


def build_router(current_user, authorize):
    router = APIRouter(prefix='/v1/organizations/{org_id}', tags=['VAT threshold'])

    @router.get('/vat-threshold')
    def vat_threshold(org_id: str, year: int | None = Query(None, ge=2025, le=2100), uid: str = Depends(current_user)):
        with connection() as db:
            authorize(db, uid, org_id, ('owner', 'accountant'))
            payer = is_vat_payer(db, org_id)
            body = estimate(db, org_id, year or date.fromisoformat(today_prague()).year)
        # A payer has nothing to track; unknown status still gets the estimate, flagged as such.
        return {**body, 'vat_payer': payer, 'applies': payer is not True}

    return router
