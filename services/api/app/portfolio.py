"""Accountant portfolio (CR-6): one overview across every company the user keeps books for.

Counts only, per company where the user is accountant or owner: documents waiting for
review or for changes, approved invoices without a recorded payment, open, overdue and
waiting tasks, and the last activity. Employees' memberships are not included, and no
document, amount or name beyond the company name leaves its company scope.
"""
from collections import defaultdict

from fastapi import APIRouter, Depends

from .database import connection
from .tasks import today_prague

FINANCE_ROLES = ('accountant', 'owner')
CLOSED = ('DONE', 'CANCELLED')


def build_router(current_user):
    router = APIRouter(prefix='/v1', tags=['Accountant portfolio'])

    @router.get('/portfolio')
    def portfolio(uid: str = Depends(current_user)):
        today = today_prague()
        with connection() as db:
            companies = db.execute(
                'SELECT o.id, o.name, m.role FROM organizations o JOIN memberships m ON m.organization_id=o.id '
                "WHERE m.user_id=? AND m.role IN ('accountant','owner') ORDER BY o.name", (uid,)).fetchall()
            ids = [c['id'] for c in companies]
            if not ids:
                return {'items': [], 'as_of_date': today, 'timezone': 'Europe/Prague'}
            marks = ','.join('?' * len(ids))
            docs = db.execute(f'SELECT organization_id, status, COUNT(*) AS n FROM documents '
                              f'WHERE organization_id IN ({marks}) GROUP BY organization_id, status',
                              tuple(ids)).fetchall()
            tasks = db.execute(f'SELECT organization_id, status, due_date FROM accounting_tasks '
                               f'WHERE organization_id IN ({marks}) AND status NOT IN (?,?)',
                               (*ids, *CLOSED)).fetchall()
            unrecorded = db.execute(
                f"SELECT d.organization_id, COUNT(*) AS n FROM documents d WHERE d.organization_id IN ({marks}) "
                "AND d.status='approved' AND EXISTS (SELECT 1 FROM document_extractions e "
                'WHERE e.document_id=d.id AND e.organization_id=d.organization_id) '
                'AND NOT EXISTS (SELECT 1 FROM cashbook_entries c WHERE c.document_id=d.id '
                'AND c.organization_id=d.organization_id AND c.voided_at IS NULL) GROUP BY d.organization_id',
                tuple(ids)).fetchall()
            activity = db.execute(f'SELECT organization_id, MAX(created_at) AS at FROM audit_events '
                                  f'WHERE organization_id IN ({marks}) GROUP BY organization_id', tuple(ids)).fetchall()
        by_doc = defaultdict(dict)
        for row in docs:
            by_doc[row['organization_id']][row['status']] = row['n']
        open_tasks, overdue, waiting = defaultdict(int), defaultdict(int), defaultdict(int)
        for task in tasks:
            org = task['organization_id']
            open_tasks[org] += 1
            overdue[org] += bool(task['due_date'] and task['due_date'] < today)
            waiting[org] += task['status'] == 'WAITING_CLIENT'
        unpaid = {r['organization_id']: r['n'] for r in unrecorded}
        last = {r['organization_id']: r['at'] for r in activity}
        items = []
        for c in companies:
            org = c['id']
            item = {
                'organization_id': org, 'name': c['name'], 'role': c['role'],
                'documents_to_review': by_doc[org].get('needs_review', 0),
                'documents_returned': by_doc[org].get('needs_changes', 0),
                'approved_without_payment': unpaid.get(org, 0),
                'open_tasks': open_tasks[org], 'overdue_tasks': overdue[org], 'waiting_on_client': waiting[org],
                'last_activity_at': last.get(org),
            }
            # What needs a person first: overdue work, then documents to review, then the rest.
            item['attention'] = ('high' if item['overdue_tasks'] else
                                 'medium' if item['documents_to_review'] or item['documents_returned'] else 'low')
            items.append(item)
        rank = {'high': 0, 'medium': 1, 'low': 2}
        items.sort(key=lambda i: (rank[i['attention']], -i['documents_to_review'], i['name'].casefold()))
        return {'items': items, 'as_of_date': today, 'timezone': 'Europe/Prague'}

    return router
