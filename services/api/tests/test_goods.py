"""CR-9 goods lines, learned goods groups and the monthly goods-intake report. Synthetic data only."""
from test_api import c, h
from test_archive import company, record, upload
from test_isdoc_import import pdf_with

from app import isdoc

BEER = {'item_code': 'SYN-001', 'name': 'Synthetic pivo 0,5 l plech (24)', 'quantity': '24', 'unit': 'ks',
        'unit_price': '25.00', 'vat_rate': '21'}
SODA = {'item_code': 'SYN-002', 'name': 'Synthetic limonáda 0,5 l', 'quantity': '10', 'unit': 'ks',
        'unit_price': '20.00', 'vat_rate': '21'}
SWEETS = {'item_code': 'SYN-003', 'name': 'Synthetic tyčinka 50 g (40)', 'quantity': '40', 'unit': 'ks',
          'unit_price': '30.00', 'vat_rate': '12'}
BREAD = {'item_code': None, 'name': 'Synthetic  chléb  1 kg', 'quantity': '20', 'unit': 'ks',
         'unit_price': '40', 'vat_rate': '12'}


def lines_url(org, did):
    return f'/v1/organizations/{org}/documents/{did}/lines'


def invoice(org, owner, name, **changes):
    did = upload(org, owner, f'%PDF-1.4\n{name}'.encode()).json()['id']
    record(org, owner, did, **changes)
    return did


def save(org, who, did, lines, version=None):
    return c.put(lines_url(org, did), headers=h(who), json={'lines': lines, 'expected_version': version})


def test_lines_need_invoice_data_and_finance_role_and_match_the_vat_bases():
    owner, accountant, employee, org = company()
    bare = upload(org, owner, b'%PDF-1.4\nNo data yet').json()['id']
    assert save(org, accountant, bare, [BEER]).status_code == 409
    did = invoice(org, owner, 'Lines ok')
    assert save(org, employee, did, [BEER]).status_code == 403
    assert c.get(lines_url(org, did), headers=h(employee)).status_code == 403
    assert save(org, accountant, did, [{**BEER, 'quantity': '0'}]).status_code == 422
    r = save(org, accountant, did, [BEER, SODA, SWEETS, BREAD])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['version'] == 1 and body['source'] == 'manual'
    assert [(l['line_no'], l['quantity'], l['net']) for l in body['lines']] == [
        (1, '24', '600.00'), (2, '10', '200.00'), (3, '40', '1200.00'), (4, '20', '800.00')]
    assert body['lines'][3]['name'] == 'Synthetic chléb 1 kg' and body['lines'][3]['item_key'] == 'name:synthetic chléb 1 kg'
    assert body['net_by_rate'] == {'12': '2000.00', '21': '800.00'}
    assert body['findings'] == []
    # Another save must name the version it replaces.
    assert save(org, owner, did, [BEER]).status_code == 409
    assert save(org, owner, did, [BEER, SODA, SWEETS, BREAD], version=1).json()['version'] == 2


def test_findings_flag_repeated_lines_wrong_line_net_and_rate_totals():
    owner, accountant, _, org = company()
    did = invoice(org, owner, 'Lines with problems')
    body = save(org, accountant, did, [BEER, BEER, {**SODA, 'net': '210.00'}, SWEETS, BREAD]).json()
    codes = {f['code']: f for f in body['findings']}
    assert codes['duplicate_line']['lines'] == [1, 2]
    assert codes['line_net_mismatch']['lines'] == [3]
    assert codes['line_net_mismatch']['detail'] == {'computed': '200.00', 'stated': '210.00'}
    assert codes['rate_total_mismatch']['detail'] == {'rate': '21', 'invoice_base': '800.00', 'lines_net': '1410.00'}


def test_group_chosen_once_is_learned_per_supplier_and_company_only():
    owner, accountant, _, org = company()
    first = invoice(org, owner, 'First delivery')
    save(org, accountant, first, [BEER, {**SODA, 'goods_group': 'soft_drinks'}, SWEETS, BREAD])
    chosen = c.put(lines_url(org, first) + '/1/group', headers=h(accountant), json={'goods_group': 'beer'})
    assert chosen.status_code == 200 and chosen.json()['lines'][0]['group_source'] == 'manual'
    second = invoice(org, owner, 'Second delivery', document_number='SYN-2')
    other = invoice(org, owner, 'Other supplier', document_number='X-1', supplier_name='Synthetic Cash & Carry',
                    supplier_vat_id='CZ00000009')
    learned = save(org, owner, second, [BREAD, BEER, SODA, SWEETS]).json()['lines']
    assert [(l['goods_group'], l['group_source']) for l in learned] == [
        (None, None), ('beer', 'learned'), ('soft_drinks', 'learned'), (None, None)]
    stranger = save(org, owner, other, [BEER]).json()['lines'][0]
    assert stranger['goods_group'] is None  # same code, different supplier: no guess
    # Choosing the sweets group on the second invoice reaches the first one too, not manual picks.
    c.put(lines_url(org, first) + '/2/group', headers=h(owner), json={'goods_group': 'other'})
    r = c.put(lines_url(org, second) + '/4/group', headers=h(owner), json={'goods_group': 'sweets'})
    assert r.json()['also_updated'] == 1
    firsts = c.get(lines_url(org, first), headers=h(owner)).json()['lines']
    assert firsts[2]['goods_group'] == 'sweets' and firsts[2]['group_source'] == 'learned'
    assert firsts[1]['goods_group'] == 'other' and firsts[1]['group_source'] == 'manual'
    assert c.put(lines_url(org, first) + '/9/group', headers=h(owner), json={'goods_group': 'beer'}).status_code == 404
    # Another company with the same supplier and code learns nothing from this one.
    owner_b, _, _, org_b = company()
    foreign = invoice(org_b, owner_b, 'Company B delivery')
    assert save(org_b, owner_b, foreign, [BEER]).json()['lines'][0]['goods_group'] is None
    assert c.get(lines_url(org_b, first), headers=h(owner_b)).status_code == 404
    assert c.get(lines_url(org, first), headers=h(owner_b)).status_code == 403


def test_monthly_report_by_group_supplier_and_item_skips_rejected_documents():
    owner, accountant, _, org = company()
    october = invoice(org, owner, 'October', supply_date='2026-10-29')
    november = invoice(org, owner, 'November', document_number='SYN-11', issue_date='2026-11-03')
    rejected = invoice(org, owner, 'Rejected', document_number='SYN-R', issue_date='2026-11-04')
    save(org, accountant, october, [{**BEER, 'goods_group': 'beer'}, SODA, SWEETS, BREAD])
    save(org, accountant, november, [{**BEER, 'quantity': '48'}, {**SWEETS, 'goods_group': 'sweets'}])
    save(org, accountant, rejected, [{**BEER, 'quantity': '480'}])
    c.post(f'/v1/organizations/{org}/documents/{rejected}/review', headers=h(accountant), json={'decision': 'reject'})
    report = c.get(f'/v1/organizations/{org}/goods', headers=h(owner), params={'month': '2026-11'}).json()
    assert report['documents'] == 1
    assert {'group': 'sweets', 'totals': {'CZK': '1200.00'}, 'quantity': {'ks': '40'}, 'lines': 1} in report['groups']
    beer = next(g for g in report['groups'] if g['group'] == 'beer')
    assert beer == {'group': 'beer', 'totals': {'CZK': '1200.00'}, 'quantity': {'ks': '48'}, 'lines': 1}
    assert report['suppliers'][0]['name'] == 'Synthetic Wholesale s.r.o.'
    assert report['suppliers'][0]['groups'] == {'beer': '1200.00', 'sweets': '1200.00'}
    october_report = c.get(f'/v1/organizations/{org}/goods', headers=h(owner), params={'month': '2026-10'}).json()
    assert october_report['uncategorised_lines'] == 3 and october_report['groups'][-1]['group'] is None
    year = c.get(f'/v1/organizations/{org}/goods', headers=h(accountant), params={'year': 2026}).json()
    assert set(year['months']) == {'2026-10', '2026-11'}
    assert year['months']['2026-10']['beer'] == '600.00'
    top = {i['name']: i for i in year['top_items']}
    assert year['top_items'][0]['name'] == SWEETS['name'] and top[SWEETS['name']]['quantity'] == {'ks': '80'}
    assert top[BEER['name']]['quantity'] == {'ks': '72'} and top[BEER['name']]['totals'] == {'CZK': '1800.00'}
    assert c.get(f'/v1/organizations/{org}/goods', headers=h(owner), params={'month': '2026-13'}).status_code == 422


def isdoc_with_lines(lines):
    """The CR-1 synthetic ISDOC with full goods lines instead of descriptions only."""
    xml = __import__('test_isdoc_import').invoice_xml().decode()
    body = ''.join(
        f'<InvoiceLine><ID>{n}</ID><InvoicedQuantity unitCode="{unit}">{qty}</InvoicedQuantity>'
        f'<LineExtensionAmount>{net}</LineExtensionAmount><UnitPrice>{price}</UnitPrice>'
        f'<ClassifiedTaxCategory><Percent>{rate}</Percent><VATCalculationMethod>0</VATCalculationMethod>'
        f'</ClassifiedTaxCategory><Item><Description>{name}</Description>'
        f'<SellersItemIdentification><ID>{code}</ID></SellersItemIdentification></Item></InvoiceLine>'
        for n, (code, name, qty, unit, price, rate, net) in enumerate(lines, start=1))
    start, end = xml.index('<InvoiceLines>') + len('<InvoiceLines>'), xml.index('</InvoiceLines>')
    return (xml[:start] + body + xml[end:]).encode()


def test_isdoc_goods_lines_are_imported_with_learned_groups():
    owner, accountant, _, org = company()
    seed = invoice(org, owner, 'Seed delivery')
    save(org, accountant, seed, [{**BEER, 'goods_group': 'beer'}, SODA, SWEETS, BREAD])
    xml = isdoc_with_lines([('SYN-001', 'Synthetic pivo 0,5 l plech (24)', '48', 'ks', '25.00', '21', '1200.00'),
                            ('SYN-003', 'Synthetic tyčinka 50 g (40)', '40', 'ks', '30.00', '12', '1200.00')])
    assert len(isdoc.goods_lines(xml)) == 2
    did = c.post(f'/v1/organizations/{org}/documents', headers=h(owner),
                 files={'file': ('isdoc.pdf', pdf_with([('f.isdoc', xml)]), 'application/pdf')}).json()['id']
    body = c.get(lines_url(org, did), headers=h(accountant)).json()
    assert body['source'] == 'isdoc' and body['version'] == 1
    assert [(l['item_code'], l['quantity'], l['net'], l['goods_group']) for l in body['lines']] == [
        ('SYN-001', '48', '1200.00', 'beer'), ('SYN-003', '40', '1200.00', None)]
    # The synthetic invoice's VAT bases (2000 / 800) do not match these lines: shown, not hidden.
    assert {f['code'] for f in body['findings']} == {'rate_total_mismatch'}
    # A line without a quantity drops the whole list rather than importing part of it.
    assert isdoc.goods_lines(isdoc_with_lines([('A', 'x', '', 'ks', '1', '21', '1.00')])) == []
