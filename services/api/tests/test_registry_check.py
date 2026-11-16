"""Partner check in ARES, the register of bankrupts and the VAT register (decision H).
Synthetic IČO/DIČ and answers only; nothing goes to the network."""
import json
from urllib.parse import urlparse

import pytest

from app import registry_check as rc
from app.web_security import SENSITIVE
from test_api import c, h
from test_archive import company


def ico(seed: str) -> str:
    """A synthetic IČO with a valid check digit."""
    total = sum(int(d) * w for d, w in zip(seed, range(8, 1, -1)))
    return seed + str((11 - total % 11) % 10)


PAYER, SMALL, BANKRUPT, UNRELIABLE, GHOST = (ico(s) for s in ('9100001', '9100002', '9100003', '9100004', '9100005'))


def ares_answer(number, dic=None, ceu='NEEXISTUJICI', ended=None):
    body = {'ico': number, 'obchodniJmeno': f'Synteticka firma {number} s.r.o.',
            'sidlo': {'textovaAdresa': 'Testovací 1, 110 00 Praha 1'}, 'datumVzniku': '2015-01-01',
            'seznamRegistraci': {'stavZdrojeDph': 'AKTIVNI' if dic else 'NEEXISTUJICI', 'stavZdrojeCeu': ceu,
                                 'stavZdrojeRes': 'AKTIVNI'}}
    if dic:
        body['dic'] = dic
    if ended:
        body['datumZaniku'] = ended
    return json.dumps(body).encode()


def adis_answer(digits, flag='NE', accounts=()):
    rows = ''.join(f'<ucet datumZverejneni="2020-01-01"><standardniUcet {a}/></ucet>' for a in accounts)
    published = f'<zverejneneUcty>{rows}</zverejneneUcty>' if rows else ''
    return (f'<?xml version="1.0"?><soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            f'<soapenv:Body><StatusNespolehlivyPlatceResponse xmlns="{rc.ADIS_NS}">'
            f'<status statusCode="0" statusText="OK"/>'
            f'<statusPlatceDPH dic="{digits}" nespolehlivyPlatce="{flag}" cisloFu="451"'
            f'{" datumZverejneniNespolehlivosti=" + chr(34) + "2026-03-01" + chr(34) if flag == "ANO" else ""}>'
            f'{published}</statusPlatceDPH></StatusNespolehlivyPlatceResponse></soapenv:Body></soapenv:Envelope>').encode()


CEU = json.dumps({'ico': BANKRUPT, 'upadek': [{'spisZn': 'KSPH 99 INS 1/2026', 'typUpadek': 'INSOLVENCE',
                                               'akceUpadek': 'ZAHAJENI', 'datum': '2026-09-01', 'soudUpadek': 'KSPH',
                                               'detail': 'https://isir.justice.cz/synteticky'}]}).encode()


class Registers:
    """Answers like the public registers would, and counts the calls."""

    def __init__(self, down=()):
        self.calls, self.down = [], set(down)

    def __call__(self, url, data, headers):
        self.calls.append(url)
        host = urlparse(url).hostname
        if host in self.down:
            raise rc.Unavailable('down')
        if host == 'ares.gov.cz':
            number = url.rstrip('/').split('/')[-1]
            if '/ekonomicke-subjekty-ceu/' in url:
                return CEU
            return {PAYER: ares_answer(PAYER, 'CZ' + PAYER),
                    SMALL: ares_answer(SMALL),
                    BANKRUPT: ares_answer(BANKRUPT, ceu='AKTIVNI'),
                    UNRELIABLE: ares_answer(UNRELIABLE, 'CZ' + UNRELIABLE)}.get(number) or _missing()
        body = data.decode()
        if PAYER in body:
            assert headers['Content-Type'].startswith('text/xml') and f'<dic>{PAYER}</dic>' in body
            return adis_answer(PAYER, accounts=('predcisli="19" cislo="123457" kodBanky="0800"',))
        if UNRELIABLE in body:
            return adis_answer(UNRELIABLE, 'ANO')
        raise AssertionError('unexpected call')


def _missing():
    raise rc.NotFound()


@pytest.fixture(autouse=True)
def registers():
    fake = Registers()
    rc.use_fetcher(fake)
    yield fake
    rc.use_fetcher(None)


def test_ico_check_digit():
    assert rc.valid_ico(PAYER) and rc.valid_ico('00006947')
    assert not rc.valid_ico(PAYER[:7] + str((int(PAYER[7]) + 1) % 10))
    assert not rc.valid_ico('1234567') and not rc.valid_ico('abcdefgh')


def test_a_reliable_vat_payer_with_its_published_account():
    result = rc.check(PAYER, account='000019-0000123457/0800')
    assert result['company']['status'] == 'ok' and result['company']['dic'] == 'CZ' + PAYER
    assert result['company']['address'] == 'Testovací 1, 110 00 Praha 1'
    assert result['insolvency'] == {'status': 'ok', 'listed': False, 'proceedings': []}
    assert result['vat']['unreliable'] is False
    assert result['vat']['published_accounts'] == [{'account': '19-123457/0800', 'published_since': '2020-01-01'}]
    assert result['account'] == {'account': '000019-0000123457/0800', 'published': True}
    assert result['warnings'] == []


def test_paying_to_an_account_the_payer_has_not_published_is_flagged():
    result = rc.check(PAYER, account='2000000001/2010')
    assert result['account']['published'] is False
    assert result['warnings'] == ['account_not_published']


def test_unreliable_vat_payer():
    result = rc.check(UNRELIABLE)
    assert result['vat']['unreliable'] is True and result['vat']['unreliable_since'] == '2026-03-01'
    assert 'unreliable_vat_payer' in result['warnings']


def test_insolvency_is_read_only_when_ares_lists_the_subject(registers):
    result = rc.check(BANKRUPT)
    assert result['insolvency']['listed'] is True
    assert result['insolvency']['proceedings'][0]['case'] == 'KSPH 99 INS 1/2026'
    assert 'insolvency' in result['warnings']
    rc.check(SMALL)
    assert not any('ceu' in u and SMALL in u for u in registers.calls)


def test_no_dic_means_no_vat_register_call(registers):
    result = rc.check(SMALL)
    assert result['vat'] == {'status': 'not_registered'}
    assert all(urlparse(u).hostname == 'ares.gov.cz' for u in registers.calls)


def test_unknown_subject():
    result = rc.check(GHOST)
    assert result['company'] == {'status': 'not_found'} and result['warnings'] == ['not_in_ares']


def test_a_register_that_does_not_answer_is_never_all_clear():
    fake = Registers(down={'adisrws.mfcr.cz'})
    rc.use_fetcher(fake)
    result = rc.check(PAYER, account='19-123457/0800')
    assert result['vat'] == {'status': 'unavailable'} and result['account']['published'] is None
    assert result['warnings'] == ['register_unavailable']
    rc.check(PAYER)
    assert len([u for u in fake.calls if 'ares' in u]) == 2  # an incomplete answer is not cached
    rc.use_fetcher(Registers(down={'ares.gov.cz'}))
    result = rc.check(PAYER)
    assert {result[p]['status'] for p in ('company', 'insolvency', 'vat')} == {'unavailable'}


def test_answers_are_cached_for_a_while(registers):
    rc.check(PAYER)
    count = len(registers.calls)
    again = rc.check(PAYER, account='1/0100')
    assert len(registers.calls) == count and again['warnings'] == ['account_not_published']


def test_an_answer_for_another_subject_or_with_a_dtd_is_refused():
    rc.use_fetcher(lambda url, data, headers: ares_answer(SMALL))
    assert rc.check(PAYER)['company'] == {'status': 'unavailable'}

    def evil(url, data, headers):
        if 'ares' in url:
            return ares_answer(PAYER, 'CZ' + PAYER)
        return b'<!DOCTYPE x [<!ENTITY e "boom">]><x>&e;</x>'
    rc.use_fetcher(evil)
    assert rc.check(PAYER)['vat'] == {'status': 'unavailable'}


def test_api_roles_validation_and_audit():
    owner, accountant, employee, org = company()
    path = f'/v1/organizations/{org}/registry-check/'
    r = c.get(path + PAYER, headers=h(owner))
    assert r.status_code == 200 and r.json()['company']['name'].startswith('Synteticka')
    assert c.get(path + UNRELIABLE + '?account=19-123457/0800', headers=h(accountant)).status_code == 200
    assert c.get(path + PAYER, headers=h(employee)).status_code == 403
    assert c.get(path + '12345678', headers=h(owner)).status_code == 422
    assert c.get(path + PAYER + '?account=abc', headers=h(owner)).status_code == 422
    events = [e['event'] for e in c.get(f'/v1/organizations/{org}/audit', headers=h(owner)).json()]
    assert events.count('registry.checked') == 2


def test_tests_never_reach_the_network():
    rc.use_fetcher(None)
    assert rc.check(PAYER)['warnings'] == ['register_unavailable']


def test_checks_count_against_the_sensitive_rate_limit():
    assert any(m == 'GET' and p.match(f'/v1/organizations/x/registry-check/{PAYER}') for m, p in SENSITIVE)
