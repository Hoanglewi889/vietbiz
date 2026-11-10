"""Accountant portfolio (CR-6): one overview across every company the user keeps books for.

Counts only, per company where the user is accountant or owner: documents waiting for
review or for changes, approved invoices without a recorded payment, open, overdue and
waiting tasks, and the last activity. Employees' memberships are not included, and no
document, amount or name beyond the company name leaves its company scope.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import median

from fastapi import APIRouter, Depends

from .database import connection
from .filing_calendar import _profile, deadlines, window
from .tasks import today_prague
from .vat_threshold import estimate, is_vat_payer
from .bank import statements_status

FINANCE_ROLES = ('accountant', 'owner')
CLOSED = ('DONE', 'CANCELLED')


def _minutes(start, end):
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60


def reply_times(comments, today):
    """Per company: open tasks whose last word is the shop's, the oldest such message, and the
    median minutes from a shop message to the accountant's next reply over the last 30 days.
    """
    since = (date.fromisoformat(today) - timedelta(days=30)).isoformat()
    threads = defaultdict(list)
    for row in comments:
        threads[(row['organization_id'], row['task_id'])].append(row)
    waiting, delays = defaultdict(list), defaultdict(list)
    for (org, _), rows in threads.items():
        pending = None
        for row in rows:
            if row['role'] == 'accountant':
                if pending and row['created_at'][:10] >= since:
                    delays[org].append(_minutes(pending, row['created_at']))
                pending = None
            elif pending is None:
                pending = row['created_at']
        if pending and rows[-1]['status'] not in CLOSED:
            waiting[org].append(pending)
    out = {}
    for org in set(waiting) | set(delays):
        out[org] = {'unanswered_messages': len(waiting[org]),
                    'oldest_unanswered_at': min(waiting[org]) if waiting[org] else None,
                    'median_reply_minutes': round(median(delays[org])) if delays[org] else None}
    return out


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
            # Task work (creation, status changes, replies) is activity too; it is not in audit_events.
            activity = db.execute(
                'SELECT organization_id, MAX(at) AS at FROM ('
                f'SELECT organization_id, created_at AS at FROM audit_events WHERE organization_id IN ({marks}) '
                f'UNION ALL SELECT organization_id, created_at FROM task_events WHERE organization_id IN ({marks}) '
                f'UNION ALL SELECT organization_id, created_at FROM task_comments WHERE organization_id IN ({marks})'
                ') a GROUP BY organization_id', (*ids, *ids, *ids)).fetchall()
            profiles = {org: _profile(db, org) for org in ids}
            # Client-visible thread only; an internal accountant note is not a reply to the shop.
            comments = db.execute(
                f"SELECT c.organization_id, c.task_id, c.created_at, m.role, t.status FROM task_comments c "
                'JOIN accounting_tasks t ON t.id=c.task_id AND t.organization_id=c.organization_id '
                'LEFT JOIN memberships m ON m.organization_id=c.organization_id AND m.user_id=c.author_id '
                f"WHERE c.organization_id IN ({marks}) AND c.visibility='client' ORDER BY c.created_at, c.id",
                tuple(ids)).fetchall()
            year = int(today[:4])
            thresholds = {org: estimate(db, org, year)['status'] for org in ids if is_vat_payer(db, org) is False}
            statements = {org: statements_status(db, org, date.fromisoformat(today)) for org in ids}
        start, end = window(30)
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
        replies = reply_times(comments, today)
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
                'profile_missing': profiles[org] is None,
                'vat_threshold': thresholds.get(org),
                **statements[org],
                **replies.get(org, {'unanswered_messages': 0, 'oldest_unanswered_at': None,
                                    'median_reply_minutes': None}),
            }
            upcoming = deadlines(profiles[org], start, end) if profiles[org] else []
            item['next_deadline'] = ({k: upcoming[0][k] for k in ('code', 'due_date', 'period')}
                                     if upcoming else None)
            # What needs a person first: overdue work, then documents to review, then the rest.
            item['attention'] = ('high' if item['overdue_tasks'] else
                                 'medium' if item['documents_to_review'] or item['documents_returned'] else 'low')
            items.append(item)
        rank = {'high': 0, 'medium': 1, 'low': 2}
        items.sort(key=lambda i: (rank[i['attention']], -i['documents_to_review'], i['name'].casefold()))
        return {'items': items, 'as_of_date': today, 'timezone': 'Europe/Prague'}

    return router
