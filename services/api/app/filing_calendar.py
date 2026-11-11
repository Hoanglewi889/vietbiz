"""Client profiles and the filing calendar (CR-8).

A company's profile (legal form, industry, VAT period, staff, flat-tax regime) decides which
returns, overviews and payments it owes and when. The calendar is computed on request, never
stored, so a corrected profile corrects every future date at once.

Dates follow the statutory rule that a tax deadline falling on a weekend or Czech public
holiday moves to the next working day (§ 33(4) daňový řád). Insurance advances are shown on
their plain statutory day, because they count as paid only when credited and the insurers do
not publish a shift rule; showing the earlier day is the safe side.

Amounts are minimums for that month with their source and a status: 'official' means read on
the authority's own site (ČSSZ, the health insurer, Finanční správa); 'reported' means a
published secondary source, to be checked against the authority before paying. Unknown years
carry no amount rather than a guess. A change during a year (the July 2026 cut of the minimum
social advance) applies from its month on.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .database import connection
from .tasks import today_prague

INDUSTRIES = ('grocery', 'bistro', 'nails', 'hair', 'tobacco', 'herbal', 'drogerie', 'electronics',
              'textile', 'import', 'online', 'other')

SOURCES = {
    'vat': 'https://www.fakturoid.cz/almanach/dane/danovy-kalendar',
    'income_tax': 'https://www.finance.cz/clanky/62974-priznani-podavame-vcas-a-na-spravny-urad',
    'overviews': 'https://www.pruvodcepodnikanim.cz/clanek/prehledy-o-prijmech-a-vydajich-2026/',
    'social': 'https://www.cssz.gov.cz/platba-a-terminy',
    'health': 'https://www.vzp.cz/platci/informace/osvc/splatnost-a-dalsi-zasady-pro-platbu-pojistneho',
    'flat_tax': 'https://www.fakturaonline.cz/podnikateluv-pruvodce/dane/pausalni-dan/pausalni-dan-2027',
    'eet': 'https://eet.gov.cz/',
}

# Minimum monthly amounts in CZK per year, each with where it was read. Secondary sources only:
# the status says so, and the UI asks to check the official figure before paying.
AMOUNTS = {
    2026: {'social_main': '5720', 'social_secondary': '1574', 'health_main': '3306',
           'flat_tax': {1: '9984', 2: '16745', 3: '27139'},
           'source': 'https://www.pruvodcepodnikanim.cz/clanek/minimalni-zalohy-osvc-2026/',
           # From 1 July 2026 the minimum assessment base for the main activity is 35 % (not 40 %)
           # of the average wage: the minimum social advance is 5 005 Kč (ČSSZ Zpravodaj, June
           # 2026). Band 1 of the flat tax follows (100 + 1.15 × 5 005 + 3 306 = 9 162 Kč).
           'from_month': {7: {'social_main': ('5005', 'official',
                                              'https://www.cssz.gov.cz/documents/20143/2045988/'
                                              '26-06%20Zpr@vodaj%20%C4%8CSSZ%20(%C4%8Derven%202026).pdf/'
                                              '9ea9bf39-2546-f714-28c1-dcbe3ef94f12'),
                              'flat_tax_1': ('9162', 'reported',
                                             'https://www.pruvodcepodnikanim.cz/clanek/pausalni-dan-2027-vyse-zaloh-do-kdy-se-prihlasit/')}}},
    # 2027: the government approved the average wage for 2027 on 21.9.2026 (secondary sources);
    # stays 'reported' until ČSSZ and VZP publish the 2027 minimums themselves.
    2027: {'social_main': '5281', 'social_secondary': '1660', 'health_main': '3488',
           'flat_tax': {1: '9662', 2: '16745', 3: '27139'},
           'source': 'https://www.podnikatel.cz/clanky/na-kolik-v-roce-2027-vzrostou-zalohy-na-socialni-a-zdravotni-pojisteni-osvc/'},
}

# Shops that take payments in person; EET 2.0 applies to cash, card and QR taken on site.
IN_PERSON = set(INDUSTRIES) - {'online'}
EET_START = date(2027, 1, 1)


def easter(year: int) -> date:
    """Gregorian Easter Sunday (anonymous algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def holidays(year: int) -> set[date]:
    """Czech public holidays (zákon č. 245/2000 Sb.), including Good Friday and Easter Monday."""
    fixed = [(1, 1), (5, 1), (5, 8), (7, 5), (7, 6), (9, 28), (10, 28), (11, 17), (12, 24), (12, 25), (12, 26)]
    sunday = easter(year)
    return {date(year, m, d) for m, d in fixed} | {sunday - timedelta(days=2), sunday + timedelta(days=1)}


def working_day(day: date) -> date:
    while day.weekday() >= 5 or day in holidays(day.year):
        day += timedelta(days=1)
    return day


def add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _amount(year, key, band=None, month=1):
    known = AMOUNTS.get(year)
    if not known:
        return None
    value = known['flat_tax'][band] if key == 'flat_tax' else known[key]
    status, source = 'reported', (known['source'] if key != 'flat_tax' or year != 2027 else SOURCES['flat_tax'])
    change_key = f'flat_tax_{band}' if key == 'flat_tax' else key
    for start, changes in sorted(known.get('from_month', {}).items()):
        if month >= start and change_key in changes:
            value, status, source = changes[change_key]
    return {'value': value, 'currency': 'CZK', 'kind': 'minimum' if key != 'flat_tax' else 'fixed',
            'status': status, 'source': source}


def _item(code, due, period, office, source, *, statutory=None, conditional=False, amount=None):
    return {'code': code, 'due_date': due.isoformat(), 'period': period, 'office': office,
            'moved_from': statutory.isoformat() if statutory and statutory != due else None,
            'conditional': conditional, 'amount': amount, 'source': source}


def _tax_day(statutory: date):
    return working_day(statutory), statutory


def deadlines(profile: dict, start: date, end: date) -> list[dict]:
    """Every obligation due within [start, end] for this profile, earliest first."""
    out = []
    osvc, sro = profile['legal_form'] == 'osvc', profile['legal_form'] == 'sro'
    band, vat = profile.get('flat_tax_band'), profile['vat_status']
    adviser = bool(profile['tax_adviser'])
    # Monthly obligations: walk the periods whose deadlines can land in the window.
    period = date(start.year, start.month, 1)
    period = add_months(period, -3)
    while period <= end:
        y, m = period.year, period.month
        label = f'{y}-{m:02d}'
        following = add_months(period, 1)
        if vat in ('monthly', 'quarterly', 'identified'):
            due, statutory = _tax_day(date(following.year, following.month, 25))
            if vat == 'monthly':
                out.append(_item('vat_return', due, label, 'tax_office', SOURCES['vat'], statutory=statutory))
            elif vat == 'identified':
                # An identified person files only for months with an EU acquisition or a received service.
                out.append(_item('vat_return_identified', due, label, 'tax_office', SOURCES['vat'],
                                 statutory=statutory, conditional=True))
            elif m % 3 == 0:
                out.append(_item('vat_return', due, f'{y}-Q{m // 3}', 'tax_office', SOURCES['vat'],
                                 statutory=statutory))
            # Control statement: legal persons monthly; natural persons with their VAT period.
            if vat == 'monthly' or (vat == 'quarterly' and sro):
                out.append(_item('control_statement', due, label, 'tax_office', SOURCES['vat'], statutory=statutory))
            elif vat == 'quarterly' and m % 3 == 0:
                out.append(_item('control_statement', due, f'{y}-Q{m // 3}', 'tax_office', SOURCES['vat'],
                                 statutory=statutory))
        if profile['has_employees']:
            due, statutory = _tax_day(date(following.year, following.month, 20))
            out.append(_item('payroll', due, label, 'payroll', SOURCES['social'], statutory=statutory))
        if osvc and band:
            due, statutory = _tax_day(date(y, m, 20))
            out.append(_item('flat_tax', due, label, 'tax_office', SOURCES['flat_tax'], statutory=statutory,
                             amount=_amount(y, 'flat_tax', band, m)))
        elif osvc:
            main = profile['osvc_activity'] == 'main'
            out.append(_item('social_advance', month_end(y, m), label, 'cssz', SOURCES['social'],
                             conditional=not main,
                             amount=_amount(y, 'social_main' if main else 'social_secondary', month=m)))
            out.append(_item('health_advance', date(following.year, following.month, 8), label, 'health_insurer',
                             SOURCES['health'], conditional=not main,
                             amount=_amount(y, 'health_main', month=m) if main else None))
        period = following
    # Yearly obligations for the tax year before each calendar year in the window.
    for year in range(start.year, end.year + 1):
        tax_year = str(year - 1)
        if osvc:
            # Entering or changing the flat-tax band: notice by 10 January (moved to a working day).
            due, statutory = _tax_day(date(year, 1, 10))
            out.append(_item('flat_tax_notice', due, str(year), 'tax_office', SOURCES['flat_tax'],
                             statutory=statutory, conditional=True))
        if osvc and not band:
            # Every OSVČ has a data box since 2023, so the return is electronic: 1 May, or 1 July
            # with an adviser. ČSSZ counts its month from the statutory day, the insurers from the
            # day the return was actually due.
            statutory = date(year, 7, 1) if adviser else date(year, 5, 1)
            due = working_day(statutory)
            out.append(_item('income_tax_return', due, tax_year, 'tax_office', SOURCES['income_tax'],
                             statutory=statutory))
            social = add_months(statutory, 1)
            out.append(_item('social_overview', working_day(social), tax_year, 'cssz', SOURCES['overviews'],
                             statutory=social))
            health = add_months(due, 1)
            out.append(_item('health_overview', working_day(health), tax_year, 'health_insurer',
                             SOURCES['overviews'], statutory=health))
        if sro:
            statutory = date(year, 7, 1) if adviser else date(year, 5, 1)
            out.append(_item('corporate_tax_return', working_day(statutory), tax_year, 'tax_office',
                             SOURCES['income_tax'], statutory=statutory))
    if profile['industry'] in IN_PERSON:
        out.append(_item('eet_start', EET_START, '2027', 'tax_office', SOURCES['eet'], conditional=True))
    return sorted((i for i in out if start.isoformat() <= i['due_date'] <= end.isoformat()),
                  key=lambda i: (i['due_date'], i['code']))


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    legal_form: Literal['osvc', 'sro']
    industry: Literal[INDUSTRIES]
    vat_status: Literal['none', 'monthly', 'quarterly', 'identified']
    has_employees: bool
    osvc_activity: Literal['main', 'secondary'] | None = None
    flat_tax_band: Literal[1, 2, 3] | None = None
    tax_adviser: bool = False
    health_insurer: str | None = Field(default=None, max_length=80)
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def consistent(self):
        if self.health_insurer is not None:
            self.health_insurer = self.health_insurer.strip() or None
        if self.legal_form == 'osvc' and self.osvc_activity is None:
            raise ValueError('osvc_activity is required for an OSVČ')
        if self.legal_form == 'sro' and (self.osvc_activity or self.health_insurer):
            raise ValueError('osvc_activity and health_insurer apply only to an OSVČ')
        if self.flat_tax_band and (self.legal_form != 'osvc' or self.vat_status != 'none'):
            # § 7a ZDP: the flat-tax regime is closed to VAT payers and identified persons.
            raise ValueError('The flat-tax regime is only for an OSVČ that is not registered for VAT')
        return self


def _profile(db, org_id):
    row = db.execute('SELECT legal_form,industry,vat_status,has_employees,osvc_activity,flat_tax_band,'
                     'tax_adviser,health_insurer,version,updated_at FROM client_profiles WHERE organization_id=?',
                     (org_id,)).fetchone()
    if row is None:
        return None
    profile = dict(row)
    profile['has_employees'] = bool(profile['has_employees'])
    profile['tax_adviser'] = bool(profile['tax_adviser'])
    return profile


def window(days: int):
    start = date.fromisoformat(today_prague())
    return start, start + timedelta(days=days)


def build_router(current_user, authorize, audit):
    router = APIRouter(prefix='/v1', tags=['Client profiles and filing calendar'])
    roles = ('owner', 'accountant')

    @router.get('/organizations/{org_id}/client-profile')
    def get_profile(org_id: str, uid: str = Depends(current_user)):
        with connection() as db:
            authorize(db, uid, org_id, roles)
            return {'profile': _profile(db, org_id)}

    @router.put('/organizations/{org_id}/client-profile')
    def put_profile(org_id: str, body: ProfileIn, uid: str = Depends(current_user)):
        now = datetime.now(timezone.utc).isoformat()
        values = (body.legal_form, body.industry, body.vat_status, int(body.has_employees), body.osvc_activity,
                  body.flat_tax_band, int(body.tax_adviser), body.health_insurer)
        with connection() as db:
            authorize(db, uid, org_id, roles)
            # Lock the company row so two editors cannot both pass the version check.
            db.execute('UPDATE organizations SET id=id WHERE id=?', (org_id,))
            current = _profile(db, org_id)
            if (current['version'] if current else None) != body.expected_version:
                raise HTTPException(409, 'The profile was changed by someone else; reload it')
            if current is None:
                db.execute('INSERT INTO client_profiles(organization_id,legal_form,industry,vat_status,has_employees,'
                           'osvc_activity,flat_tax_band,tax_adviser,health_insurer,version,updated_by,updated_at) '
                           'VALUES(?,?,?,?,?,?,?,?,?,1,?,?)', (org_id, *values, uid, now))
            else:
                db.execute('UPDATE client_profiles SET legal_form=?,industry=?,vat_status=?,has_employees=?,'
                           'osvc_activity=?,flat_tax_band=?,tax_adviser=?,health_insurer=?,version=version+1,'
                           'updated_by=?,updated_at=? WHERE organization_id=?', (*values, uid, now, org_id))
            audit(db, org_id, uid, 'client_profile.updated', None)
            return {'profile': _profile(db, org_id)}

    @router.get('/organizations/{org_id}/deadlines')
    def company_deadlines(org_id: str, days: int = Query(60, ge=1, le=400), uid: str = Depends(current_user)):
        start, end = window(days)
        with connection() as db:
            authorize(db, uid, org_id, roles)
            profile = _profile(db, org_id)
        return {'profile_missing': profile is None, 'from': start.isoformat(), 'to': end.isoformat(),
                'items': deadlines(profile, start, end) if profile else []}

    @router.get('/deadlines')
    def portfolio_deadlines(days: int = Query(30, ge=1, le=400), uid: str = Depends(current_user)):
        """Every company the user keeps books for or owns, one list, earliest first."""
        start, end = window(days)
        with connection() as db:
            companies = db.execute(
                'SELECT o.id, o.name FROM organizations o JOIN memberships m ON m.organization_id=o.id '
                "WHERE m.user_id=? AND m.role IN ('accountant','owner') ORDER BY o.name", (uid,)).fetchall()
            profiles = {c['id']: _profile(db, c['id']) for c in companies}
        items, missing = [], []
        for c in companies:
            profile = profiles[c['id']]
            if profile is None:
                missing.append({'organization_id': c['id'], 'name': c['name']})
                continue
            items += [{**i, 'organization_id': c['id'], 'name': c['name']} for i in deadlines(profile, start, end)]
        items.sort(key=lambda i: (i['due_date'], i['name'].casefold(), i['code']))
        return {'from': start.isoformat(), 'to': end.isoformat(), 'items': items, 'profiles_missing': missing}

    return router
