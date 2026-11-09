"""CR-3 document archive: filters, totals, categories, duplicates, roles, tenancy. Synthetic data only."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from test_api import c, h, user

from app.database import Transaction

FIELDS = {
    'supplier_name': 'Synthetic Wholesale s.r.o., Praha', 'supplier_vat_id': 'CZ00000001',
    'document_number': 'SYN-1', 'subject': 'Potraviny', 'issue_date': '2026-10-30',
    'currency': 'CZK', 'total': '3208.00',
    'lines': [{'rate': '12', 'base': '2000.00', 'tax': '240.00'},
              {'rate': '21', 'base': '800.00', 'tax': '168.00'}],
}


def company():
    owner, accountant, employee = user('Archive owner'), user('Archive accountant'), user('Archive employee')
    org = c.post('/v1/organizations', json={'name': 'Archive'}, headers=h(owner)).json()['id']
    for member, role in ((accountant, 'accountant'), (employee, 'employee')):
        invite = c.post(f'/v1/organizations/{org}/members', json={'user_id': member, 'role': role}, headers=h(owner))
        c.post(f"/v1/invitations/{invite.json()['id']}/accept", headers=h(member))
    return owner, accountant, employee, org


def upload(org, who, body=b'%PDF-1.4\nSynthetic', name='a.pdf'):
    return c.post(f'/v1/organizations/{org}/documents', headers=h(who),
                  files={'file': (name, body, 'application/pdf')})


def record(org, who, did, **changes):
    r = c.put(f'/v1/organizations/{org}/documents/{did}/extraction', headers=h(who),
              json={'version': 0, 'fields': {**FIELDS, **changes}})
    assert r.status_code == 200, r.text


def archive(org, who, **params):
    return c.get(f'/v1/organizations/{org}/archive', headers=h(who), params=params)


def stocked():
    owner, accountant, employee, org = company()
    makro = upload(org, owner, b'%PDF-1.4\nMakro').json()['id']
    lidl = upload(org, owner, b'%PDF-1.4\nLidl').json()['id']
    rent = upload(org, owner, b'%PDF-1.4\nRent').json()['id']
    bare = upload(org, owner, b'%PDF-1.4\nNo data yet').json()['id']
    record(org, owner, makro)
    record(org, owner, lidl, supplier_name='Synthetic Discount v.o.s., Brno', supplier_vat_id='CZ00000003',
           document_number='L-77', issue_date='2026-09-12', total='121.00',
           lines=[{'rate': '21', 'base': '100.00', 'tax': '21.00'}])
    record(org, owner, rent, supplier_name='Synthetic Reality a.s.', supplier_vat_id='CZ00000004',
           document_number='N-10', total='24200.00', customer_name='Archive', customer_vat_id='CZ00000009',
           lines=[{'rate': '21', 'base': '20000.00', 'tax': '4200.00'}])
    assert c.put(f'/v1/organizations/{org}/documents/{rent}/category', headers=h(accountant),
                 json={'category': 'rent'}).status_code == 200
    return owner, accountant, employee, org, {'makro': makro, 'lidl': lidl, 'rent': rent, 'bare': bare}


def ids(response):
    return {i['id'] for i in response.json()['items']}


def test_archive_lists_invoice_data_and_totals():
    owner, _, _, org, d = stocked()
    body = archive(org, owner).json()
    assert len(body['items']) == 4
    makro = next(i for i in body['items'] if i['id'] == d['makro'])
    assert makro['invoice'] == {'supplier_name': 'Synthetic Wholesale s.r.o., Praha', 'supplier_vat_id': 'CZ00000001',
                                'document_number': 'SYN-1', 'issue_date': '2026-10-30', 'currency': 'CZK',
                                'total': '3208.00', 'tax': '408.00', 'complete': True, 'source': 'manual', 'version': 1}
    assert body['summary'] == {'count': 4, 'without_data': 1,
                               'by_currency': {'CZK': {'count': 3, 'total': '27529.00', 'tax': '4629.00'}}}
    assert 'goods' in body['categories'] and 'rent' in body['categories']


def test_filters_by_month_text_category_and_status():
    owner, accountant, _, org, d = stocked()
    assert ids(archive(org, owner, month='2026-09')) == {d['lidl']}
    assert ids(archive(org, owner, q='wholesale')) == {d['makro']}
    assert ids(archive(org, owner, q='cz00000004')) == {d['rent']}
    assert ids(archive(org, owner, q='L-77')) == {d['lidl']}
    assert ids(archive(org, owner, category='rent')) == {d['rent']}
    assert ids(archive(org, owner, category='none')) == {d['makro'], d['lidl'], d['bare']}
    c.post(f"/v1/organizations/{org}/documents/{d['makro']}/review", headers=h(accountant), json={'decision': 'approve'})
    assert ids(archive(org, owner, status='approved')) == {d['makro']}
    month = archive(org, owner, month='2026-10').json()['summary']['by_currency']['CZK']
    assert month == {'count': 2, 'total': '27408.00', 'tax': '4608.00'}


def test_invalid_filters_are_rejected():
    owner, _, _, org, _ = stocked()
    assert archive(org, owner, month='2026-13').status_code == 422
    assert archive(org, owner, category='tax_deductible').status_code == 422
    assert archive(org, owner, status='paid').status_code == 422


def test_category_can_be_set_and_cleared_and_is_audited():
    owner, accountant, _, org, d = stocked()
    url = f"/v1/organizations/{org}/documents/{d['makro']}/category"
    assert c.put(url, headers=h(owner), json={'category': 'goods'}).json() == {'id': d['makro'], 'category': 'goods'}
    assert c.put(url, headers=h(owner), json={'category': 'bribes'}).status_code == 422
    assert c.put(url, headers=h(owner), json={'category': None}).status_code == 200
    assert ids(archive(org, owner, category='goods')) == set()
    audit = c.get(f'/v1/organizations/{org}/audit', headers=h(accountant)).json()
    assert sum(1 for e in audit if e['event'] == 'document.categorized') >= 3


def test_same_supplier_and_number_is_flagged_as_possible_duplicate():
    owner, _, _, org, d = stocked()
    copy = upload(org, owner, b'%PDF-1.4\nMakro photographed again').json()['id']
    record(org, owner, copy, document_number='syn-1', supplier_vat_id='cz00000001')
    items = {i['id']: i for i in archive(org, owner).json()['items']}
    assert items[copy]['possible_duplicates'] == [d['makro']]
    assert items[d['makro']]['possible_duplicates'] == [copy]
    assert items[d['lidl']]['possible_duplicates'] == []


def test_identical_file_is_refused_with_the_existing_document():
    owner, _, employee, org, d = stocked()
    again = upload(org, employee, b'%PDF-1.4\nMakro', name='copy.pdf')
    assert again.status_code == 409
    assert again.json()['detail'] == {'code': 'duplicate_file', 'document_id': d['makro']}
    other_owner, _, _, other_org = company()
    assert upload(other_org, other_owner, b'%PDF-1.4\nMakro').status_code == 201  # other company: allowed


def test_concurrent_identical_uploads_keep_one(monkeypatch):
    owner, _, employee, org = company()
    gate, original = Barrier(2), Transaction.execute

    def synchronized(self, statement, parameters=()):
        if statement.startswith('UPDATE organizations SET id=id'):
            gate.wait(timeout=10)
        return original(self, statement, parameters)

    monkeypatch.setattr(Transaction, 'execute', synchronized)
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(lambda who: upload(org, who, b'%PDF-1.4\nSame').status_code, (owner, employee)))
    monkeypatch.setattr(Transaction, 'execute', original)
    assert statuses == [201, 409]
    assert len(archive(org, owner).json()['items']) == 1


def test_employee_and_outsiders_cannot_open_the_archive():
    _, _, employee, org, d = stocked()
    stranger = user('Archive stranger')
    for who in (employee, stranger):
        assert archive(org, who).status_code == 403
        assert c.put(f"/v1/organizations/{org}/documents/{d['makro']}/category", headers=h(who),
                     json={'category': 'goods'}).status_code == 403


def test_other_companies_documents_cannot_be_categorised():
    _, _, _, org_a, d = stocked()
    owner_b, _, _, org_b = company()
    assert c.put(f"/v1/organizations/{org_b}/documents/{d['makro']}/category", headers=h(owner_b),
                 json={'category': 'goods'}).status_code == 404
    assert ids(archive(org_b, owner_b)) == set()
