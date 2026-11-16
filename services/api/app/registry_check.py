"""Check a business partner in public Czech registers by IČO (owner decision H, 12.11.2026).

`GET /v1/organizations/{org}/registry-check/{ico}[?account=…]` — owner or accountant — asks:

- ARES (Ministry of Finance): name, registered address, DIČ, whether the subject has ended, and
  which source registers list it (`seznamRegistraci`, e.g. `stavZdrojeDph`, `stavZdrojeCeu`);
- ARES, register of bankrupts (CEÚ, fed by the insolvency register ISIR): proceedings, only when
  ARES says the subject is listed there;
- the VAT register web service of the Financial Administration (ADIS, `rozhraniCRPDPH`): whether a
  VAT payer is unreliable (nespolehlivý plátce) and its published bank accounts. With `account`,
  the answer says whether that account is among them: paying a VAT payer's invoice to an
  account it has not published can make the buyer liable for the VAT (§ 109 zákona o DPH).

What leaves VietBiz: only the IČO (and the DIČ derived from ARES), sent to these public state
registers. Every check is written to the audit log. A register that does not answer is reported
as `unavailable` — never as "all clear". Answers are kept in memory for ten minutes so the same
partner is not asked about again and again (ARES forbids mass automated querying).

Endpoints can be changed with VIETBIZ_ARES_URL and VIETBIZ_ADIS_URL. In tests nothing goes to
the network: a fetcher is injected with `use_fetcher`.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Callable
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException, Query

from .database import connection

ARES_URL = 'https://ares.gov.cz/ekonomicke-subjekty-v-be/rest'
ADIS_URL = 'https://adisrws.mfcr.cz/dpr/axis2/services/rozhraniCRPDPH.rozhraniCRPDPHSOAP'
ADIS_NS = 'http://adis.mfcr.cz/rozhraniCRPDPH/'
MAX_BYTES = 2_000_000
CACHE_SECONDS = 600

Fetch = Callable[[str, bytes | None, dict], bytes]


class Unavailable(Exception):
    """The register did not give a usable answer."""


class NotFound(Exception):
    """The register answered that it does not know the subject."""


def valid_ico(ico: str) -> bool:
    """IČO: eight digits with the mod-11 check digit."""
    if not re.fullmatch(r'\d{8}', ico or ''):
        return False
    total = sum(int(d) * w for d, w in zip(ico[:7], range(8, 1, -1)))
    check = (11 - total % 11) % 10
    return check == int(ico[7])


def _http(url: str, data: bytes | None, headers: dict) -> bytes:
    if os.getenv('VIETBIZ_ENV', 'development').strip().lower() == 'test':
        raise Unavailable('No network in tests')
    try:
        with urlopen(Request(url, data=data, headers=headers), timeout=10) as response:
            body = response.read(MAX_BYTES + 1)
    except Exception as error:  # HTTP errors are sorted out by the callers through the status
        status = getattr(error, 'code', None)
        if status == 404:
            raise NotFound() from None
        raise Unavailable(type(error).__name__) from None
    if len(body) > MAX_BYTES:
        raise Unavailable('Answer too large')
    return body


_fetch: Fetch = _http
_cache: dict[tuple, tuple[float, dict]] = {}
_lock = threading.Lock()


def use_fetcher(fetch: Fetch | None) -> None:
    """Replace the network call (tests); None restores it. Clears the cache."""
    global _fetch
    _fetch = fetch or _http
    with _lock:
        _cache.clear()


def _ares_base() -> str:
    return os.getenv('VIETBIZ_ARES_URL', ARES_URL).rstrip('/')


def _json(url: str) -> dict:
    try:
        data = json.loads(_fetch(url, None, {'Accept': 'application/json', 'User-Agent': 'VietBiz/1.0'}))
    except (ValueError, UnicodeDecodeError):
        raise Unavailable('Not JSON') from None
    if not isinstance(data, dict):
        raise Unavailable('Unexpected answer')
    return data


def ares(ico: str) -> dict:
    data = _json(f'{_ares_base()}/ekonomicke-subjekty/{ico}')
    if str(data.get('ico', '')).zfill(8) != ico:
        raise Unavailable('ARES answered for another subject')
    registrations = data.get('seznamRegistraci') or {}
    return {
        'name': data.get('obchodniJmeno'),
        'address': (data.get('sidlo') or {}).get('textovaAdresa'),
        'dic': data.get('dic'),
        'founded': data.get('datumVzniku'),
        'ended': data.get('datumZaniku'),
        'registrations': {k.removeprefix('stavZdroje').lower(): v for k, v in registrations.items()
                          if k.startswith('stavZdroje')},
        'url': f'https://ares.gov.cz/ekonomicke-subjekty?ico={ico}',
    }


def bankruptcies(ico: str) -> list[dict]:
    data = _json(f'{_ares_base()}/ekonomicke-subjekty-ceu/{ico}')
    records = data.get('zaznamy') if isinstance(data.get('zaznamy'), list) else [data]
    found = []
    for record in records:
        for case in record.get('upadek') or []:
            found.append({'case': case.get('spisZn'), 'type': case.get('typUpadek'), 'action': case.get('akceUpadek'),
                          'date': case.get('datum'), 'court': case.get('soudUpadek'), 'url': case.get('detail')})
    return found


def _account(element) -> str | None:
    standard = element.find(f'{{{ADIS_NS}}}standardniUcet')
    if standard is not None:
        prefix, number, bank = (standard.get('predcisli'), standard.get('cislo'), standard.get('kodBanky'))
        if number and bank:
            return (f'{prefix}-' if prefix else '') + f'{number}/{bank}'
    other = element.find(f'{{{ADIS_NS}}}nestandardniUcet')
    if other is not None and other.get('cislo'):
        return other.get('cislo')
    return None


def vat_status(dic: str) -> dict:
    digits = re.sub(r'^CZ', '', dic.strip().upper())
    if not re.fullmatch(r'\d{8,10}', digits):
        raise Unavailable('Not a Czech DIČ')
    envelope = ('<?xml version="1.0" encoding="UTF-8"?>'
                '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
                f'<soapenv:Body><StatusNespolehlivyPlatceRequest xmlns="{ADIS_NS}"><dic>{digits}</dic>'
                '</StatusNespolehlivyPlatceRequest></soapenv:Body></soapenv:Envelope>').encode()
    raw = _fetch(os.getenv('VIETBIZ_ADIS_URL', ADIS_URL), envelope,
                 {'Content-Type': 'text/xml; charset=utf-8', 'SOAPAction': '', 'User-Agent': 'VietBiz/1.0'})
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise Unavailable('DTD not allowed')
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise Unavailable('Not XML') from None
    status = next((e for e in root.iter(f'{{{ADIS_NS}}}statusPlatceDPH') if e.get('dic') == digits), None)
    if status is None:
        raise Unavailable('No status in the answer')
    flag = status.get('nespolehlivyPlatce')
    if flag == 'NENALEZEN':
        raise NotFound()
    if flag not in ('ANO', 'NE'):
        raise Unavailable('Unknown status')
    accounts = []
    for published in status.iter(f'{{{ADIS_NS}}}ucet'):
        number = _account(published)
        if number:
            accounts.append({'account': number, 'published_since': published.get('datumZverejneni')})
    return {'dic': 'CZ' + digits, 'unreliable': flag == 'ANO',
            'unreliable_since': status.get('datumZverejneniNespolehlivosti'),
            'tax_office': status.get('cisloFu'), 'published_accounts': accounts,
            'url': 'https://adisspr.mfcr.cz/adistc/adis/idpr_pub/dpr_info/dph.faces'}


def _normal_account(value: str) -> str:
    """'000019-0000123457/0800' and '19-123457/0800' are the same account."""
    left, _, bank = re.sub(r'\s+', '', value or '').partition('/')
    prefix, _, number = left.rpartition('-')
    return f"{prefix.lstrip('0') or '0'}-{number.lstrip('0')}/{bank}"


def _part(call, *args) -> dict:
    try:
        return {'status': 'ok', **call(*args)}
    except NotFound:
        return {'status': 'not_found'}
    except Unavailable:
        return {'status': 'unavailable'}


def check(ico: str, account: str | None = None) -> dict:
    """What the public registers say about one IČO. Parts that did not answer say so."""
    key = (ico,)
    now = time.monotonic()
    with _lock:
        cached = _cache.get(key)
    if cached and now - cached[0] < CACHE_SECONDS:
        result = json.loads(json.dumps(cached[1]))
    else:
        company = _part(ares, ico)
        insolvency: dict = {'status': 'unavailable'}
        if company['status'] == 'ok':
            listed = company['registrations'].get('ceu') == 'AKTIVNI'
            insolvency = {'status': 'ok', 'listed': False, 'proceedings': []}
            if listed:
                insolvency = {**_part(lambda i: {'proceedings': bankruptcies(i)}, ico), 'listed': True}
        elif company['status'] == 'not_found':
            insolvency = {'status': 'not_found'}
        vat: dict = {'status': 'not_registered'}
        if company['status'] == 'ok' and company.get('dic'):
            vat = _part(vat_status, company['dic'])
        elif company['status'] == 'unavailable':
            vat = {'status': 'unavailable'}
        result = {'ico': ico, 'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  'company': company, 'insolvency': insolvency, 'vat': vat}
        if company['status'] != 'unavailable' and vat['status'] != 'unavailable':
            with _lock:
                if len(_cache) > 5000:
                    _cache.clear()
                _cache[key] = (now, json.loads(json.dumps(result)))
    result['warnings'] = _warnings(result, account)
    if account:
        published = None
        if result['vat'].get('status') == 'ok':
            wanted = _normal_account(account)
            published = any(_normal_account(a['account']) == wanted for a in result['vat']['published_accounts'])
        result['account'] = {'account': account, 'published': published}
    return result


def _warnings(result: dict, account: str | None) -> list[str]:
    """Codes the web turns into sentences; nothing here is a legal conclusion."""
    codes = []
    company, vat, insolvency = result['company'], result['vat'], result['insolvency']
    if company['status'] == 'not_found':
        codes.append('not_in_ares')
    if company.get('ended'):
        codes.append('subject_ended')
    if insolvency.get('listed'):
        codes.append('insolvency')
    if vat.get('unreliable'):
        codes.append('unreliable_vat_payer')
    if account and vat.get('status') == 'ok':
        wanted = _normal_account(account)
        if not any(_normal_account(a['account']) == wanted for a in vat['published_accounts']):
            codes.append('account_not_published')
    if any(part.get('status') == 'unavailable' for part in (company, vat, insolvency)):
        codes.append('register_unavailable')
    return codes


def build_router(current_user, authorize, audit):
    router = APIRouter(prefix='/v1/organizations/{org_id}')

    @router.get('/registry-check/{ico}')
    def registry_check(org_id: str, ico: str, account: str | None = Query(None, max_length=40),
                       uid: str = Depends(current_user)):
        """A partner's entry in ARES, the register of bankrupts and the VAT register."""
        ico = re.sub(r'\s+', '', ico)
        if not valid_ico(ico):
            raise HTTPException(422, 'Invalid IČO')
        if account is not None and not re.fullmatch(r'[0-9\- /]{2,40}', account):
            raise HTTPException(422, 'Invalid account number')
        with connection() as db:
            authorize(db, uid, org_id, ('owner', 'accountant'))
            audit(db, org_id, uid, 'registry.checked', None)
        return check(ico, account)

    return router
