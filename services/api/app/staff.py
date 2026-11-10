"""Staff, shifts and tips for the owner (CR-12).

A shift is what was actually worked: date, start, end (an end before the start runs past
midnight), unpaid break minutes and tips. Hours, labour cost (hours × the staff member's
hourly rate, when set) and tips are summed per person for any period up to 62 days.

Findings follow the Labour Code as described by SÚIP and MPSV: a shift longer than 12 hours,
more than 6 hours of work (4.5 for a person under 18) with less than 30 minutes of break,
less than 11 hours of rest before the next shift of the same person, and overlapping shifts.
The app cannot see when the break was taken or the exceptions the law allows, so these are
prompts for the owner to check, not a verdict.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .database import connection
from .tasks import Key, digest, today_prague

Rate = Annotated[str, Field(pattern=r'^\d{1,6}(\.\d{1,2})?$')]
Time = Annotated[str, Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')]
CENT = Decimal('0.01')
MAX_SHIFT = 12 * 60
BREAK_AFTER, BREAK_AFTER_MINOR, BREAK_MIN = 6 * 60, 270, 30
REST_MIN = 11 * 60
SOURCES = {
    'break': 'https://ppropo.mpsv.cz/pdf/VIII4Prestavkavpraciabezpecnostn.pdf',
    'shift_rest': 'https://suip.gov.cz/documents/20142/43720/pracovni_doba_2020.pdf/fdb5a992-0cfc-e015-361b-a9eff00766b0',
}


class StaffIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    display_name: str = Field(min_length=1, max_length=80)
    job: str | None = Field(default=None, max_length=60)
    hourly_rate: Rate | None = None
    minor: bool = False
    active: bool = True
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator('display_name', 'job', mode='before')
    @classmethod
    def tidy(cls, value):
        if isinstance(value, str):
            value = ' '.join(value.split())
            return value or None
        return value


class ShiftIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    staff_id: str = Field(max_length=64)
    work_date: date
    start_time: Time
    end_time: Time
    break_minutes: int = Field(default=0, ge=0, le=600)
    tips: Rate = '0'
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode='after')
    def sensible(self):
        if self.start_time == self.end_time:
            raise ValueError('a shift needs different start and end times')
        if self.break_minutes >= span(self.start_time, self.end_time):
            raise ValueError('the break is as long as the shift')
        return self


class VoidIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: str = Field(min_length=3, max_length=300)


def _minutes(hhmm):
    hours, minutes = hhmm.split(':')
    return int(hours) * 60 + int(minutes)


def span(start, end):
    """Minutes from start to end; an end at or before the start is on the next day."""
    length = _minutes(end) - _minutes(start)
    return length if length > 0 else length + 24 * 60


def _bounds(shift):
    begin = datetime.fromisoformat(shift['work_date']) + timedelta(minutes=_minutes(shift['start_time']))
    return begin, begin + timedelta(minutes=span(shift['start_time'], shift['end_time']))


def _money(value):
    return str(Decimal(value).quantize(CENT, ROUND_HALF_UP))


def shift_findings(shifts, staff):
    """Findings keyed by shift id. `shifts` are the active shifts in date order."""
    out = defaultdict(list)
    last = {}
    for shift in sorted(shifts, key=lambda s: (s['staff_id'], *_bounds(s))):
        worked = span(shift['start_time'], shift['end_time']) - shift['break_minutes']
        minor = bool(staff.get(shift['staff_id'], {}).get('minor'))
        if worked > MAX_SHIFT:
            out[shift['id']].append({'code': 'shift_too_long', 'minutes': worked, 'limit': MAX_SHIFT,
                                     'source': SOURCES['shift_rest']})
        if worked > (BREAK_AFTER_MINOR if minor else BREAK_AFTER) and shift['break_minutes'] < BREAK_MIN:
            out[shift['id']].append({'code': 'break_missing', 'minutes': worked,
                                     'after': BREAK_AFTER_MINOR if minor else BREAK_AFTER,
                                     'break_minutes': shift['break_minutes'], 'source': SOURCES['break']})
        begin, end = _bounds(shift)
        previous = last.get(shift['staff_id'])
        if previous:
            gap = (begin - previous[1]).total_seconds() / 60
            if gap < 0:
                out[shift['id']].append({'code': 'shift_overlap', 'other_shift_id': previous[0]})
            elif gap < REST_MIN:
                out[shift['id']].append({'code': 'rest_too_short', 'minutes': int(gap), 'limit': REST_MIN,
                                         'other_shift_id': previous[0], 'source': SOURCES['shift_rest']})
        if previous is None or end > previous[1]:
            last[shift['staff_id']] = (shift['id'], end)
    return out


SHIFT_COLUMNS = ('id,staff_id,work_date,start_time,end_time,break_minutes,tips,note,created_by,created_at,'
                 'voided_at,voided_by,void_reason')
STAFF_COLUMNS = 'id,display_name,job,hourly_rate,minor,active,version,updated_at'


def _staff(row):
    item = dict(row)
    item['minor'], item['active'] = bool(item['minor']), bool(item['active'])
    return item


def build_router(current_user, authorize, audit):
    router = APIRouter(prefix='/v1/organizations/{org_id}', tags=['Staff and shifts'])
    roles = ('owner', 'accountant')

    def all_staff(db, org_id):
        return {r['id']: _staff(r) for r in db.execute(
            f'SELECT {STAFF_COLUMNS} FROM staff_members WHERE organization_id=? ORDER BY display_name', (org_id,))}

    @router.get('/staff')
    def list_staff(org_id: str, uid: str = Depends(current_user)):
        with connection() as db:
            authorize(db, uid, org_id, roles)
            return {'items': list(all_staff(db, org_id).values())}

    @router.post('/staff', status_code=201)
    def add_staff(org_id: str, body: StaffIn, uid: str = Depends(current_user)):
        staff_id, now = str(uuid4()), datetime.now(timezone.utc).isoformat()
        with connection() as db:
            authorize(db, uid, org_id, roles)
            db.execute('INSERT INTO staff_members(id,organization_id,display_name,job,hourly_rate,minor,active,version,'
                       'updated_by,updated_at) VALUES(?,?,?,?,?,?,?,1,?,?)',
                       (staff_id, org_id, body.display_name, body.job,
                        _money(body.hourly_rate) if body.hourly_rate else None, int(body.minor), int(body.active),
                        uid, now))
            audit(db, org_id, uid, 'staff.added', None)
            return all_staff(db, org_id)[staff_id]

    @router.put('/staff/{staff_id}')
    def edit_staff(org_id: str, staff_id: str, body: StaffIn, uid: str = Depends(current_user)):
        if body.expected_version is None:
            raise HTTPException(422, 'expected_version is required to edit a staff member')
        now = datetime.now(timezone.utc).isoformat()
        with connection() as db:
            authorize(db, uid, org_id, roles)
            changed = db.execute(
                'UPDATE staff_members SET display_name=?, job=?, hourly_rate=?, minor=?, active=?, version=version+1, '
                'updated_by=?, updated_at=? WHERE id=? AND organization_id=? AND version=?',
                (body.display_name, body.job, _money(body.hourly_rate) if body.hourly_rate else None,
                 int(body.minor), int(body.active), uid, now, staff_id, org_id, body.expected_version)).rowcount
            if changed != 1:
                exists = db.execute('SELECT 1 FROM staff_members WHERE id=? AND organization_id=?',
                                    (staff_id, org_id)).fetchone()
                raise HTTPException(409 if exists else 404, 'Changed by someone else; reload' if exists
                                    else 'Staff member not found')
            audit(db, org_id, uid, 'staff.updated', None)
            return all_staff(db, org_id)[staff_id]

    @router.post('/shifts', status_code=201)
    def add_shift(org_id: str, body: ShiftIn, response: Response, idempotency_key: Key,
                  uid: str = Depends(current_user)):
        if body.work_date > date.fromisoformat(today_prague()):
            raise HTTPException(422, 'A shift is recorded once it was worked')
        shift_id, now, request_hash = str(uuid4()), datetime.now(timezone.utc).isoformat(), digest(body)
        with connection() as db:
            authorize(db, uid, org_id, roles)
            member = db.execute('SELECT active FROM staff_members WHERE id=? AND organization_id=?',
                                (body.staff_id, org_id)).fetchone()
            if member is None:
                raise HTTPException(422, 'Unknown staff member for this company')
            inserted = db.execute(
                'INSERT INTO shifts(id,organization_id,staff_id,work_date,start_time,end_time,break_minutes,tips,note,'
                'idempotency_key,request_hash,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) '
                'ON CONFLICT(organization_id,created_by,idempotency_key) DO NOTHING',
                (shift_id, org_id, body.staff_id, body.work_date.isoformat(), body.start_time, body.end_time,
                 body.break_minutes, _money(body.tips), body.note, idempotency_key, request_hash, uid, now))
            row = db.execute(f'SELECT request_hash,{SHIFT_COLUMNS} FROM shifts WHERE organization_id=? AND created_by=? '
                             'AND idempotency_key=?', (org_id, uid, idempotency_key)).fetchone()
            if row['request_hash'] != request_hash:
                raise HTTPException(409, 'Idempotency key already used for another shift')
            if inserted.rowcount == 1:
                audit(db, org_id, uid, 'shift.recorded', None)
            else:
                response.status_code = 200
            item = dict(row)
            item.pop('request_hash')
            return item

    @router.post('/shifts/{shift_id}/void')
    def void_shift(org_id: str, shift_id: str, body: VoidIn, uid: str = Depends(current_user)):
        now = datetime.now(timezone.utc).isoformat()
        with connection() as db:
            authorize(db, uid, org_id, roles)
            changed = db.execute('UPDATE shifts SET voided_at=?, voided_by=?, void_reason=? WHERE id=? '
                                 'AND organization_id=? AND voided_at IS NULL',
                                 (now, uid, body.reason, shift_id, org_id)).rowcount
            if changed != 1:
                exists = db.execute('SELECT 1 FROM shifts WHERE id=? AND organization_id=?', (shift_id, org_id)).fetchone()
                raise HTTPException(409 if exists else 404, 'Already voided' if exists else 'Shift not found')
            audit(db, org_id, uid, 'shift.voided', None)
            return dict(db.execute(f'SELECT {SHIFT_COLUMNS} FROM shifts WHERE id=?', (shift_id,)).fetchone())

    @router.get('/shifts')
    def list_shifts(org_id: str, start: date = Query(alias='from'), end: date = Query(alias='to'),
                    uid: str = Depends(current_user)):
        if end < start or (end - start).days > 62:
            raise HTTPException(422, 'Choose a period of at most 62 days')
        with connection() as db:
            authorize(db, uid, org_id, roles)
            staff = all_staff(db, org_id)
            # One day either side, so rest between shifts at the edges of the period is checked too.
            rows = [dict(r) for r in db.execute(
                f'SELECT {SHIFT_COLUMNS} FROM shifts WHERE organization_id=? AND work_date >= ? AND work_date <= ? '
                'ORDER BY work_date, start_time', (org_id, (start - timedelta(days=1)).isoformat(),
                                                   (end + timedelta(days=1)).isoformat()))]
        active = [r for r in rows if r['voided_at'] is None]
        findings = shift_findings(active, staff)
        inside = [r for r in rows if start.isoformat() <= r['work_date'] <= end.isoformat()]
        per = defaultdict(lambda: {'shifts': 0, 'minutes': 0, 'tips': Decimal('0'), 'cost': Decimal('0'),
                                   'findings': 0})
        for shift in inside:
            worked = span(shift['start_time'], shift['end_time']) - shift['break_minutes']
            shift['worked_minutes'] = worked
            shift['findings'] = findings.get(shift['id'], []) if shift['voided_at'] is None else []
            if shift['voided_at'] is not None:
                continue
            p = per[shift['staff_id']]
            p['shifts'] += 1
            p['minutes'] += worked
            p['tips'] += Decimal(shift['tips'])
            p['findings'] += len(shift['findings'])
            rate = staff.get(shift['staff_id'], {}).get('hourly_rate')
            if rate:
                p['cost'] += Decimal(rate) * worked / 60
        summary = [{'staff_id': sid, 'display_name': staff[sid]['display_name'], 'shifts': p['shifts'],
                    'minutes': p['minutes'], 'hours': str((Decimal(p['minutes']) / 60).quantize(CENT)),
                    'labour_cost': _money(p['cost']) if staff[sid]['hourly_rate'] else None,
                    'tips': _money(p['tips']), 'findings': p['findings']}
                   for sid, p in sorted(per.items(), key=lambda kv: staff[kv[0]]['display_name'].casefold())]
        totals = {'minutes': sum(s['minutes'] for s in summary),
                  'labour_cost': _money(sum((Decimal(s['labour_cost'] or 0) for s in summary), Decimal('0'))),
                  'tips': _money(sum((Decimal(s['tips']) for s in summary), Decimal('0'))),
                  'unpriced_staff': [s['display_name'] for s in summary if s['labour_cost'] is None]}
        return {'from': start.isoformat(), 'to': end.isoformat(), 'items': inside, 'summary': summary,
                'totals': totals}

    return router
