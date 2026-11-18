"""EET 2.0 readiness, step by step (owner request 18.11.2026: "chỉ dẫn và làm theo quy trình").

The web shows the steps in plain Vietnamese / Czech with the official links; this module keeps
which steps a company has done, by whom and when, so the owner and the accountant see the same
progress.

- `GET  /v1/organizations/{org}/eet-readiness` — every member: the steps in order, done or not.
- `PUT  /v1/organizations/{org}/eet-readiness/{step}` — owner or accountant: `{"done": true|false,
  "choice": …}`. The first step `applies` takes a choice: `yes` (payments taken in person),
  `no` (only transfers / online payments — EET does not apply) or `eet_off` (flat-tax band 1 with
  income up to 1 million Kč, paying the EET OFF surcharge instead; to agree with the accountant).
  Every change is audited (`eet.step`).

Dates the steps rely on (Financial Administration / Ministry of Finance, checked 18.11.2026):
DIS+ on MOJE daně open for EET since 1.11.2026 (register, places of business, cash register
certificates), the free MOJE EET web app from 1.12.2026, EET 2.0 from 1.1.2027 with January as a
pilot month without sanctions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from .database import connection

STEPS = ('applies', 'dis', 'units', 'certificate', 'tool', 'pilot')


class StepIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    done: bool
    choice: Literal['yes', 'no', 'eet_off'] | None = None


def readiness(db, org_id: str) -> dict:
    rows = {r['step']: r for r in db.execute(
        'SELECT s.step, s.choice, s.done_at, u.display_name FROM eet_steps s JOIN users u ON u.id=s.done_by '
        'WHERE s.organization_id=?', (org_id,)).fetchall()}
    steps = [{'step': step, 'done': step in rows, 'choice': rows[step]['choice'] if step in rows else None,
              'done_at': rows[step]['done_at'] if step in rows else None,
              'done_by': rows[step]['display_name'] if step in rows else None} for step in STEPS]
    choice = steps[0]['choice']
    # "no": EET does not apply; "eet_off": the shop leaves EET by paying the surcharge.
    needed = [] if choice in ('no', 'eet_off') else list(STEPS)
    return {'steps': steps, 'choice': choice, 'applies': choice not in ('no', 'eet_off'),
            'remaining': [s['step'] for s in steps if s['step'] in needed and not s['done']]}


def build_router(current_user, authorize, audit):
    router = APIRouter(prefix='/v1/organizations/{org_id}')

    @router.get('/eet-readiness')
    def get_readiness(org_id: str, uid: str = Depends(current_user)):
        """The EET 2.0 steps of this company, done or not."""
        with connection() as db:
            authorize(db, uid, org_id, ('owner', 'accountant', 'employee'))
            return readiness(db, org_id)

    @router.put('/eet-readiness/{step}')
    def set_step(org_id: str, step: str, body: StepIn, uid: str = Depends(current_user)):
        """Mark a step done or not done again."""
        if step not in STEPS:
            raise HTTPException(404, 'Unknown step')
        if step == 'applies' and body.done and body.choice is None:
            raise HTTPException(422, 'The first step needs a choice')
        if step != 'applies' and body.choice is not None:
            raise HTTPException(422, 'Only the first step takes a choice')
        with connection() as db:
            authorize(db, uid, org_id, ('owner', 'accountant'))
            if body.done:
                db.execute('DELETE FROM eet_steps WHERE organization_id=? AND step=?', (org_id, step))
                db.execute('INSERT INTO eet_steps(organization_id,step,choice,done_by,done_at) VALUES (?,?,?,?,?)',
                           (org_id, step, body.choice, uid, datetime.now(timezone.utc).isoformat(timespec='seconds')))
            else:
                db.execute('DELETE FROM eet_steps WHERE organization_id=? AND step=?', (org_id, step))
            audit(db, org_id, uid, 'eet.step', None)
            return readiness(db, org_id)

    return router
