"""Claude's security review of 11.11.2026 (report gap 5): regression tests for its findings.
Synthetic data only."""
import pytest
from test_api import c, h
from test_bank import gpc_075
from test_invoicing import draft, issue, payer_company, url
from test_statements import header, send, statement

from app import isdoc, news


def events(org, who):
    return [e['event'] for e in c.get(f'/v1/organizations/{org}/audit', headers=h(who)).json()]


def test_a_dtd_hidden_behind_a_long_comment_is_refused():
    body = (b'<?xml version="1.0"?><!--' + b'x' * 5000 + b'--><!DOCTYPE Invoice SYSTEM "http://x.example/a.dtd">'
            b'<Invoice xmlns="' + isdoc.NS.encode() + b'" version="6.0.2"/>')
    with pytest.raises(isdoc.NotImportable, match='dtd'):
        isdoc.parse_invoice(body)


def test_a_feed_with_a_dtd_is_refused():
    with pytest.raises(ValueError, match='DTD'):
        news.extract_items(b'<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY a "b">]><rss><channel/></rss>', 'x')


def test_statement_downloads_and_invoice_exports_are_logged():
    owner, accountant, employee, org = payer_company()
    body = statement(header('300926', 100000, 150000, 10, '311026'), gpc_075(50000, '2', ref='1', day='151026'))
    import_id = send(org, owner, body).json()['import_id']
    assert c.get(url(org, f'/bank/imports/{import_id}/file'), headers=h(accountant)).status_code == 200
    iid = draft(org, owner).json()['id']
    issue(org, owner, iid)
    assert c.get(url(org, f'/invoices/{iid}/isdoc'), headers=h(owner)).status_code == 200
    names = events(org, owner)
    assert 'bank.statement_download_requested' in names and 'invoice.exported' in names
    # Refused requests leave no download record.
    other = c.get(url(org, '/bank/imports/missing/file'), headers=h(accountant))
    assert other.status_code == 404
    assert events(org, owner).count('bank.statement_download_requested') == 1
