"""Review flags on documents and the archive date range (UI elements #012, #030). Synthetic data only."""
from test_api import c, h
from test_archive import archive, company, ids, stocked


def flag(org, who, did, flagged):
    return c.put(f'/v1/organizations/{org}/documents/{did}/flag', headers=h(who), json={'flagged': flagged})


def test_flag_marks_a_document_and_counts_the_company():
    owner, accountant, employee, org, d = stocked()
    assert c.get(f"/v1/organizations/{org}/documents/{d['makro']}/flag", headers=h(owner)).json() == \
        {'flagged': False, 'flagged_count': 0}
    assert flag(org, accountant, d['makro'], True).json() == {'flagged': True, 'flagged_count': 1}
    assert flag(org, owner, d['lidl'], True).json() == {'flagged': True, 'flagged_count': 2}
    # The same state again changes nothing and logs nothing.
    assert flag(org, owner, d['lidl'], True).json() == {'flagged': True, 'flagged_count': 2}
    body = archive(org, owner).json()
    assert body['flagged_count'] == 2
    assert {i['id'] for i in body['items'] if i['flagged']} == {d['makro'], d['lidl']}
    assert ids(archive(org, owner, flagged='true')) == {d['makro'], d['lidl']}
    assert flag(org, owner, d['makro'], False).json() == {'flagged': False, 'flagged_count': 1}
    names = [e['event'] for e in c.get(f'/v1/organizations/{org}/audit', headers=h(owner)).json()]
    assert names.count('document.flagged') == 2 and names.count('document.unflagged') == 1


def test_only_finance_roles_flag_and_tenancy_holds():
    owner, accountant, employee, org, d = stocked()
    assert flag(org, employee, d['makro'], True).status_code == 403
    assert c.get(f"/v1/organizations/{org}/documents/{d['makro']}/flag", headers=h(employee)).status_code == 403
    other_owner, _, _, other = company()
    # A document of another company is not found, even for its own owner's id.
    assert flag(other, other_owner, d['makro'], True).status_code == 404
    assert flag(org, other_owner, d['makro'], True).status_code == 403
    assert flag(org, owner, 'missing', True).status_code == 404
    assert c.put(f"/v1/organizations/{org}/documents/{d['makro']}/flag", headers=h(owner),
                 json={'flagged': True, 'extra': 1}).status_code == 422


def test_archive_date_range_uses_the_issue_date():
    owner, accountant, employee, org, d = stocked()
    # makro and rent are issued 2026-10-30, lidl 2026-09-12; bare has no data and counts by upload day.
    assert ids(archive(org, owner, date_from='2026-09-01', date_to='2026-09-30')) == {d['lidl']}
    assert ids(archive(org, owner, date_from='2026-10-30', date_to='2026-10-30')) == {d['makro'], d['rent']}
    assert d['lidl'] not in ids(archive(org, owner, date_from='2026-10-01'))
    assert ids(archive(org, owner, date_to='2026-09-12')) == {d['lidl']}
    assert archive(org, owner, date_from='2026-10-02', date_to='2026-10-01').status_code == 422
    assert archive(org, owner, date_from='2026-13-01').status_code == 422
