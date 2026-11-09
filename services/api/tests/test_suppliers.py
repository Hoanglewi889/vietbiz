"""Supplier and category breakdown after scanning; categories learnt per supplier. Synthetic data only."""
from test_api import c, h, user
from test_archive import FIELDS, company, record, upload

WHOLESALE = {'supplier_name': 'Synthetic Wholesale s.r.o., Praha', 'supplier_vat_id': 'CZ00000001'}
MARKET = {'supplier_name': 'Synthetic Supermarket a.s., Brno', 'supplier_vat_id': 'CZ00000002',
          'total': '121.00', 'lines': [{'rate': '21', 'base': '100.00', 'tax': '21.00'}]}


def categorise(org, who, did, category):
    assert c.put(f'/v1/organizations/{org}/documents/{did}/category', headers=h(who),
                 json={'category': category}).status_code == 200


def category_of(org, who, did):
    return next(i['category'] for i in c.get(f'/v1/organizations/{org}/archive', headers=h(who)).json()['items']
                if i['id'] == did)


def scanned(org, who, body, **fields):
    did = upload(org, who, body).json()['id']
    record(org, who, did, **fields)
    return did


def test_next_receipt_from_a_known_supplier_gets_its_category():
    owner, accountant, _, org = company()
    first = scanned(org, owner, b'%PDF-1.4\nW1', **WHOLESALE)
    assert category_of(org, owner, first) is None  # nothing learnt yet: no guess
    categorise(org, owner, first, 'goods')
    second = scanned(org, owner, b'%PDF-1.4\nW2', **WHOLESALE, document_number='SYN-2')
    assert category_of(org, owner, second) == 'goods'
    other = scanned(org, owner, b'%PDF-1.4\nM1', **MARKET)
    assert category_of(org, owner, other) is None
    categorise(org, owner, second, 'supplies')  # a manual choice is never overwritten
    record_again = c.put(f'/v1/organizations/{org}/documents/{second}/extraction', headers=h(owner),
                         json={'version': 1, 'fields': {**FIELDS, **WHOLESALE, 'subject': 'Edited'}})
    assert record_again.status_code == 200 and category_of(org, owner, second) == 'supplies'
    events = [e['event'] for e in c.get(f'/v1/organizations/{org}/audit', headers=h(accountant)).json()]
    assert events.count('document.auto_categorized') == 1


def test_learning_stays_inside_the_company():
    owner_a, _, _, org_a = company()
    owner_b, _, _, org_b = company()
    first = scanned(org_a, owner_a, b'%PDF-1.4\nA', **WHOLESALE)
    categorise(org_a, owner_a, first, 'rent')
    other = scanned(org_b, owner_b, b'%PDF-1.4\nB', **WHOLESALE)
    assert category_of(org_b, owner_b, other) is None


def test_suppliers_breakdown_totals_months_and_categories():
    owner, _, employee, org = company()
    a = scanned(org, owner, b'%PDF-1.4\nS1', **WHOLESALE)
    categorise(org, owner, a, 'goods')
    scanned(org, owner, b'%PDF-1.4\nS2', **WHOLESALE, document_number='SYN-2', issue_date='2026-09-15')
    scanned(org, owner, b'%PDF-1.4\nS3', **MARKET)
    upload(org, owner, b'%PDF-1.4\nNo data')
    body = c.get(f'/v1/organizations/{org}/suppliers', headers=h(owner)).json()
    first, second = body['items']
    assert (first['name'], first['vat_id'], first['documents']) == ('Synthetic Wholesale s.r.o.', 'CZ00000001', 2)
    assert first['totals'] == {'CZK': {'total': '6416.00', 'tax': '816.00'}}
    assert first['months'] == {'2026-09': '3208.00', '2026-10': '3208.00'}
    assert first['category'] == 'goods' and second['category'] is None
    assert body['by_category'] == {'CZK': {'goods': '6416.00', 'none': '121.00'}}
    assert body['uncategorised_documents'] == 1
    only_2025 = c.get(f'/v1/organizations/{org}/suppliers', headers=h(owner), params={'year': 2025}).json()
    assert only_2025['items'] == []
    assert c.get(f'/v1/organizations/{org}/suppliers', headers=h(employee)).status_code == 403
    stranger = user('Supplier stranger')
    assert c.get(f'/v1/organizations/{org}/suppliers', headers=h(stranger)).status_code == 403


def test_learning_follows_current_supplier_and_latest_choice():
    """Codex review, PR #12: superseded supplier data and extraction time must not decide."""
    owner, _, _, org = company()
    moved = scanned(org, owner, b'%PDF-1.4\nMoved', **WHOLESALE)
    categorise(org, owner, moved, 'rent')
    fix = c.put(f'/v1/organizations/{org}/documents/{moved}/extraction', headers=h(owner),
                json={'version': 1, 'fields': {**FIELDS, **MARKET}})
    assert fix.status_code == 200  # supplier corrected from Wholesale to Supermarket
    fresh = scanned(org, owner, b'%PDF-1.4\nFresh W', **WHOLESALE, document_number='SYN-9')
    assert category_of(org, owner, fresh) is None  # no current Wholesale history any more

    older = scanned(org, owner, b'%PDF-1.4\nOlder M', **MARKET, document_number='M-1')
    assert category_of(org, owner, older) == 'rent'  # learnt from the corrected document
    categorise(org, owner, moved, 'utilities')
    categorise(org, owner, older, 'supplies')  # the latest choice, on the document with older data
    newest = scanned(org, owner, b'%PDF-1.4\nNewest M', **MARKET, document_number='M-2')
    assert category_of(org, owner, newest) == 'supplies'
