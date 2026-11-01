"""Small company-scoped collaboration slice; no automatic accounting decisions."""
import json
from datetime import date, datetime, timezone
from hashlib import sha256
from typing import Annotated, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from .database import connection

Status = Literal['OPEN', 'IN_PROGRESS', 'WAITING_CLIENT', 'BLOCKED', 'IN_REVIEW',
                 'DONE', 'REOPENED', 'CANCELLED']
Key = Annotated[str, Header(alias='Idempotency-Key', min_length=8, max_length=128,
                            pattern=r'^[A-Za-z0-9._:-]+$')]
STATES = ('OPEN', 'IN_PROGRESS', 'WAITING_CLIENT', 'BLOCKED', 'IN_REVIEW',
          'DONE', 'REOPENED', 'CANCELLED')
TRANSITIONS = {
    'OPEN': ('IN_PROGRESS', 'WAITING_CLIENT', 'BLOCKED', 'CANCELLED'),
    'IN_PROGRESS': ('WAITING_CLIENT', 'BLOCKED', 'IN_REVIEW', 'CANCELLED'),
    'WAITING_CLIENT': ('IN_PROGRESS', 'IN_REVIEW', 'BLOCKED', 'CANCELLED'),
    'BLOCKED': ('IN_PROGRESS', 'WAITING_CLIENT', 'CANCELLED'),
    'IN_REVIEW': ('DONE', 'WAITING_CLIENT', 'BLOCKED', 'CANCELLED'),
    'DONE': ('REOPENED',),
    'REOPENED': ('IN_PROGRESS', 'WAITING_CLIENT', 'BLOCKED', 'CANCELLED'),
    'CANCELLED': (),
}
OWNER_TARGETS = {'IN_PROGRESS', 'IN_REVIEW'}
TASK_COLUMNS = ('id', 'organization_id', 'document_id', 'title', 'description',
                'status', 'priority', 'due_date', 'created_by', 'version',
                'created_at', 'updated_at')
COMMENT_COLUMNS = ('id', 'organization_id', 'task_id', 'author_id', 'body',
                   'visibility', 'created_at')


class StrictBody(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class TaskCreate(StrictBody):
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(default='', max_length=4000)
    document_id: str | None = Field(default=None, min_length=1, max_length=64)
    priority: Literal['normal', 'high'] = 'normal'
    due_date: date | None = None


class TaskTransition(StrictBody):
    version: int = Field(ge=1, strict=True)
    status: Status
    reason: str = Field(default='', max_length=2000)


class CommentCreate(StrictBody):
    body: str = Field(min_length=1, max_length=4000)
    visibility: Literal['client', 'accountant'] = 'client'


def today_prague():
    return datetime.now(ZoneInfo('Europe/Prague')).date().isoformat()


def digest(body):
    return sha256(json.dumps(body.model_dump(mode='json'), sort_keys=True,
                             separators=(',', ':')).encode()).hexdigest()


def get_task(db, org, task_id):
    row = db.execute('SELECT * FROM accounting_tasks WHERE organization_id=? AND id=?',
                     (org, task_id)).fetchone()
    if not row:
        raise HTTPException(404, 'Task not found')
    return row


def available(status, role):
    return [target for target in TRANSITIONS[status]
            if role == 'accountant' or target in OWNER_TARGETS]


def public_task(row, role):
    item = {key: row[key] for key in TASK_COLUMNS}
    item['is_overdue'] = bool(row['due_date'] and row['due_date'] < today_prague()
                              and row['status'] not in ('DONE', 'CANCELLED'))
    item['available_transitions'] = available(row['status'], role)
    return item


def record_event(db, row, actor, previous, reason):
    db.execute('INSERT INTO task_events VALUES(?,?,?,?,?,?,?,?,?)',
               (str(uuid4()), row['organization_id'], row['id'], actor, previous,
                row['status'], row['version'], reason, row['updated_at']))


def page(db, table, where, params, cursor, limit, columns='*'):
    # table/where/columns are fixed internal constants, never request SQL.
    if cursor:
        anchor = db.execute(f'SELECT created_at,id FROM {table} WHERE {where} AND id=?',
                            (*params, cursor)).fetchone()
        if not anchor:
            raise HTTPException(422, 'Invalid cursor for this scope or filter')
        where += ' AND (created_at<? OR (created_at=? AND id<?))'
        params = (*params, anchor['created_at'], anchor['created_at'], anchor['id'])
    rows = db.execute(f'SELECT {columns} FROM {table} WHERE {where} '
                      'ORDER BY created_at DESC,id DESC LIMIT ?', (*params, limit + 1)).fetchall()
    return rows[:limit], rows[limit - 1]['id'] if len(rows) > limit else None


def build_router(current_user, authorize):
    router = APIRouter(prefix='/v1/organizations/{org_id}/tasks', tags=['Accountant tasks'])

    def role_for(db, uid, org):
        # Staff delegation is intentionally deferred: employee membership alone
        # does not reveal accountant notes or financial tasks.
        return authorize(db, uid, org, ('owner', 'accountant'))

    @router.post('', status_code=201)
    def create_task(org_id: str, body: TaskCreate, response: Response,
                    idempotency_key: Key, uid: str = Depends(current_user)):
        now = datetime.now(timezone.utc).isoformat()
        task_id, request_hash = str(uuid4()), digest(body)
        with connection() as db:
            role = role_for(db, uid, org_id)
            if body.document_id and not db.execute(
                'SELECT 1 FROM documents WHERE id=? AND organization_id=?',
                (body.document_id, org_id)
            ).fetchone():
                raise HTTPException(404, 'Document not found')
            inserted = db.execute(
                'INSERT INTO accounting_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) '
                'ON CONFLICT(organization_id,created_by,idempotency_key) DO NOTHING',
                (task_id, org_id, body.document_id, body.title, body.description, 'OPEN',
                 body.priority, body.due_date.isoformat() if body.due_date else None,
                 uid, 1, now, now, idempotency_key, request_hash)
            )
            row = db.execute('SELECT * FROM accounting_tasks WHERE organization_id=? '
                             'AND created_by=? AND idempotency_key=?',
                             (org_id, uid, idempotency_key)).fetchone()
            if row['request_hash'] != request_hash:
                raise HTTPException(409, 'Idempotency key already used for another request')
            if inserted.rowcount == 1:
                record_event(db, row, uid, None, '')
            else:
                response.status_code = 200
            return public_task(row, role)

    @router.get('')
    def list_tasks(org_id: str, status: Status | None = None,
                   overdue: bool = False, cursor: str | None = Query(default=None, max_length=64),
                   limit: int = Query(default=25, ge=1, le=100), uid: str = Depends(current_user)):
        with connection() as db:
            role = role_for(db, uid, org_id)
            where, params = 'organization_id=?', (org_id,)
            if status:
                where += ' AND status=?'
                params += (status,)
            if overdue:
                where += " AND due_date<? AND status NOT IN ('DONE','CANCELLED')"
                params += (today_prague(),)
            rows, next_cursor = page(db, 'accounting_tasks', where, params, cursor, limit)
            return {'items': [public_task(row, role) for row in rows], 'next_cursor': next_cursor}

    @router.get('/summary')
    def summary(org_id: str, uid: str = Depends(current_user)):
        with connection() as db:
            role_for(db, uid, org_id)
            counts = {status: 0 for status in STATES}
            for row in db.execute('SELECT status,COUNT(*) AS n FROM accounting_tasks '
                                  'WHERE organization_id=? GROUP BY status', (org_id,)).fetchall():
                counts[row['status']] = row['n']
            late = db.execute("SELECT COUNT(*) AS n FROM accounting_tasks WHERE organization_id=? "
                              "AND due_date<? AND status NOT IN ('DONE','CANCELLED')",
                              (org_id, today_prague())).fetchone()['n']
            return {'by_status': counts, 'overdue': late, 'as_of_date': today_prague(),
                    'timezone': 'Europe/Prague'}

    @router.get('/{task_id}')
    def detail(org_id: str, task_id: str, uid: str = Depends(current_user)):
        with connection() as db:
            role = role_for(db, uid, org_id)
            return public_task(get_task(db, org_id, task_id), role)

    @router.patch('/{task_id}')
    def transition(org_id: str, task_id: str, body: TaskTransition,
                   uid: str = Depends(current_user)):
        with connection() as db:
            role = role_for(db, uid, org_id)
            row = get_task(db, org_id, task_id)
            if row['version'] != body.version:
                raise HTTPException(409, 'Task changed; reload before updating')
            if body.status not in TRANSITIONS[row['status']]:
                raise HTTPException(409, 'Invalid task transition')
            if body.status not in available(row['status'], role):
                raise HTTPException(403, 'Only an accountant can make this transition')
            if body.status in {'WAITING_CLIENT', 'BLOCKED', 'REOPENED', 'CANCELLED'} and not body.reason:
                raise HTTPException(422, 'A reason is required for this transition')
            changed = db.execute('UPDATE accounting_tasks SET status=?,version=version+1,updated_at=? '
                                 'WHERE organization_id=? AND id=? AND version=?',
                                 (body.status, datetime.now(timezone.utc).isoformat(),
                                  org_id, task_id, body.version))
            if changed.rowcount != 1:
                raise HTTPException(409, 'Task changed; reload before updating')
            updated = get_task(db, org_id, task_id)
            record_event(db, updated, uid, row['status'], body.reason)
            return public_task(updated, role)

    @router.get('/{task_id}/events')
    def history(org_id: str, task_id: str, cursor: str | None = Query(default=None, max_length=64),
                limit: int = Query(default=25, ge=1, le=100), uid: str = Depends(current_user)):
        with connection() as db:
            role_for(db, uid, org_id)
            get_task(db, org_id, task_id)
            rows, next_cursor = page(db, 'task_events', 'organization_id=? AND task_id=?',
                                     (org_id, task_id), cursor, limit)
            return {'items': [dict(row) for row in rows], 'next_cursor': next_cursor}

    @router.post('/{task_id}/comments', status_code=201)
    def comment(org_id: str, task_id: str, body: CommentCreate, response: Response,
                idempotency_key: Key, uid: str = Depends(current_user)):
        with connection() as db:
            role = role_for(db, uid, org_id)
            get_task(db, org_id, task_id)
            if body.visibility == 'accountant' and role != 'accountant':
                raise HTTPException(403, 'Only accountants may write internal notes')
            request_hash = digest(body)
            inserted = db.execute('INSERT INTO task_comments VALUES(?,?,?,?,?,?,?,?,?) '
                                  'ON CONFLICT(task_id,author_id,idempotency_key) DO NOTHING',
                                  (str(uuid4()), org_id, task_id, uid, body.body, body.visibility,
                                   datetime.now(timezone.utc).isoformat(), idempotency_key, request_hash))
            row = db.execute('SELECT * FROM task_comments WHERE organization_id=? AND task_id=? '
                             'AND author_id=? AND idempotency_key=?',
                             (org_id, task_id, uid, idempotency_key)).fetchone()
            if row['request_hash'] != request_hash:
                raise HTTPException(409, 'Idempotency key already used for another comment')
            if inserted.rowcount != 1:
                response.status_code = 200
            return {key: row[key] for key in COMMENT_COLUMNS}

    @router.get('/{task_id}/comments')
    def comments(org_id: str, task_id: str, cursor: str | None = Query(default=None, max_length=64),
                 limit: int = Query(default=25, ge=1, le=100), uid: str = Depends(current_user)):
        with connection() as db:
            role = role_for(db, uid, org_id)
            get_task(db, org_id, task_id)
            where = 'organization_id=? AND task_id=?'
            if role != 'accountant':
                where += " AND visibility='client'"
            rows, next_cursor = page(db, 'task_comments', where, (org_id, task_id), cursor,
                                     limit, ','.join(COMMENT_COLUMNS))
            return {'items': [dict(row) for row in rows], 'next_cursor': next_cursor}

    return router
