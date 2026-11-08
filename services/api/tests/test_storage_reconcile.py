"""Originals storage reconcile tool: dry-run by default, never deletes referenced data."""
import os
from datetime import UTC, datetime, timedelta

from test_api import c, h, user

from app import main, maintenance

PDF = b'%PDF-1.4\nSynthetic reconcile'


def uploaded():
    owner = user('Reconcile owner')
    org = c.post('/v1/organizations', headers=h(owner), json={'name': 'Reconcile'}).json()['id']
    did = c.post(f'/v1/organizations/{org}/documents', headers=h(owner),
                 files={'file': ('a.pdf', PDF, 'application/pdf')}).json()['id']
    return owner, org, did


def age(path, hours):
    old = (datetime.now(UTC) - timedelta(hours=hours)).timestamp()
    os.utime(path, (old, old), follow_symlinks=False)


def test_reconcile_promotes_committed_partial_and_removes_only_stale_orphans():
    owner, org, did = uploaded()
    folder = main.FILES / org
    final = folder / f'{did}.pdf'
    partial = folder / f'.{did}.part'
    os.replace(final, partial)  # crash after commit, before rename
    stale = folder / '.00000000-dead-beef-0000-000000000000.part'
    stale.write_bytes(PDF)
    age(stale, 2)
    fresh = folder / '.11111111-0000-0000-0000-000000000000.part'
    fresh.write_bytes(PDF)  # may belong to an upload still in flight
    unreferenced = folder / '22222222-0000-0000-0000-000000000000.pdf'
    unreferenced.write_bytes(PDF)
    age(unreferenced, 2)

    dry = maintenance.reconcile(main.FILES, apply=False)
    assert str(partial) in dry['promoted']
    assert str(stale) in dry['stale_partials']
    assert str(fresh) not in dry['stale_partials']
    assert str(unreferenced) in dry['unreferenced']
    assert partial.exists() and stale.exists() and not final.exists()  # dry-run changes nothing

    maintenance.reconcile(main.FILES, apply=True)
    assert final.read_bytes() == PDF and not partial.exists()
    assert not stale.exists()
    assert fresh.exists()
    assert unreferenced.exists()  # reported for a human, never auto-deleted
    assert c.get(f'/v1/organizations/{org}/documents/{did}/original', headers=h(owner)).status_code == 200


def test_reconcile_ignores_symlinks_and_foreign_tenant_paths(tmp_path):
    _, org, _ = uploaded()
    folder = main.FILES / org
    outside = tmp_path / 'outside.part'
    outside.write_bytes(PDF)
    link = folder / '.33333333-0000-0000-0000-000000000000.part'
    link.symlink_to(outside)
    age(link, 2)
    # A partial whose document row points into another tenant must not be promoted.
    _, other_org, other_did = uploaded()
    os.replace(main.FILES / other_org / f'{other_did}.pdf', folder / f'.{other_did}.part')

    result = maintenance.reconcile(main.FILES, apply=True)
    assert str(link) not in result['stale_partials'] and link.is_symlink() and outside.exists()
    assert str(folder / f'.{other_did}.part') not in result['promoted']
    assert (folder / f'.{other_did}.part').exists()
    assert not (main.FILES / other_org / f'{other_did}.pdf').exists()
