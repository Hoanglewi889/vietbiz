"""Invoice data per document (CR-1): append-only revisions checked against the VAT Act.

Data is entered manually for now. No OCR result is faked; `source` reserves room for a
provider once the owner chooses one. Checks never conclude deductibility or tax due.
"""
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.exc import IntegrityError

from .archive import learn_category
from .goods import reconcile_supplier
from .database import connection
from .tax_document_rules import TaxDocument, VatLine, check_tax_document

Amount = Annotated[str, Field(pattern=r'^-?\d{1,12}(\.\d{1,2})?$')]
Rate = Annotated[str, Field(pattern=r'^\d{1,2}(\.\d{1,2})?$')]
OPEN_STATUSES = ('needs_review', 'needs_changes')


class StrictBody(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class LineIn(StrictBody):
    rate: Rate | None = None
    base: Amount | None = None
    tax: Amount | None = None


class FieldsIn(StrictBody):
    supplier_name: str | None = Field(default=None, max_length=200)
    supplier_vat_id: str | None = Field(default=None, max_length=20)
    document_number: str | None = Field(default=None, max_length=64)
    subject: str | None = Field(default=None, max_length=500)
    issue_date: date | None = None
    supply_date: date | None = None
    customer_name: str | None = Field(default=None, max_length=200)
    customer_vat_id: str | None = Field(default=None, max_length=20)
    currency: str = Field(default='CZK', pattern=r'^[A-Z]{3}$')
    total: Amount | None = None
    exempt: bool = False
    reverse_charge: bool = False
    lines: list[LineIn] = Field(default_factory=list, max_length=10)

    @field_validator('supplier_name', 'supplier_vat_id', 'document_number', 'subject',
                     'customer_name', 'customer_vat_id', mode='before')
    @classmethod
    def blank_is_missing(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


class ExtractionIn(StrictBody):
    version: int = Field(ge=0, strict=True)
    source: Literal['manual'] = 'manual'
    fields: FieldsIn


def _dec(value):
    return None if value is None else Decimal(value)


def to_tax_document(fields: FieldsIn) -> TaxDocument:
    return TaxDocument(
        supplier_name=fields.supplier_name, supplier_vat_id=fields.supplier_vat_id,
        document_number=fields.document_number, subject=fields.subject,
        issue_date=fields.issue_date, supply_date=fields.supply_date,
        customer_name=fields.customer_name, customer_vat_id=fields.customer_vat_id,
        currency=fields.currency, total=_dec(fields.total),
        exempt=fields.exempt, reverse_charge=fields.reverse_charge,
        lines=tuple(VatLine(_dec(line.rate), _dec(line.base), _dec(line.tax)) for line in fields.lines))


def check_to_json(result):
    return {'kind': result.kind, 'complete': result.complete,
            'findings': [{'code': f.code, 'severity': f.severity, 'field': f.field,
                          'basis': f.basis, 'detail': f.detail} for f in result.findings]}


def _insert(db, org_id, doc_id, uid, version, source, fields: 'FieldsIn', check):
    db.execute('INSERT INTO document_extractions VALUES(?,?,?,?,?,?,?,?)',
               (doc_id, org_id, version, source,
                json.dumps(fields.model_dump(mode='json'), ensure_ascii=False, sort_keys=True),
                json.dumps(check, ensure_ascii=False, sort_keys=True), uid,
                datetime.now(timezone.utc).isoformat()))
    # After a scan or edit: same supplier as before -> same category (company's own history only).
    learn_category(db, org_id, uid, doc_id, fields.model_dump(mode='json'))
    # A corrected supplier moves the document's goods lines with it (CR-9).
    reconcile_supplier(db, org_id, uid, doc_id, fields.model_dump(mode='json'))


def record_isdoc(db, org_id, uid, doc_id, raw_fields):
    """Store ISDOC data as revision 1 inside the upload transaction. Invalid data is skipped."""
    if raw_fields is None:
        return False
    try:
        fields = FieldsIn(**raw_fields)
    except ValidationError:
        return False
    check = check_to_json(check_tax_document(to_tax_document(fields)))
    _insert(db, org_id, doc_id, uid, 1, 'isdoc', fields, check)
    return True


def public(row):
    return {'document_id': row['document_id'], 'version': row['version'], 'source': row['source'],
            'fields': json.loads(row['fields']), 'check': json.loads(row['check_result']),
            'updated_by': row['actor_id'], 'updated_at': row['created_at']}


def build_router(current_user, authorize, audit):
    router = APIRouter(prefix='/v1/organizations/{org_id}/documents/{doc_id}/extraction',
                       tags=['Invoice data'])

    def scope(db, uid, org_id, doc_id):
        # Employees upload but do not see financial data, as with accountant tasks.
        authorize(db, uid, org_id, ('owner', 'accountant'))
        doc = db.execute('SELECT status FROM documents WHERE id=? AND organization_id=?',
                         (doc_id, org_id)).fetchone()
        if not doc:
            raise HTTPException(404, 'Document not found')
        return doc

    def latest(db, org_id, doc_id):
        return db.execute('SELECT * FROM document_extractions WHERE organization_id=? AND document_id=? '
                          'ORDER BY version DESC LIMIT 1', (org_id, doc_id)).fetchone()

    @router.get('')
    def read(org_id: str, doc_id: str, uid: str = Depends(current_user)):
        with connection() as db:
            scope(db, uid, org_id, doc_id)
            row = latest(db, org_id, doc_id)
        if not row:
            raise HTTPException(404, 'No invoice data yet')
        return public(row)

    @router.put('')
    def save(org_id: str, doc_id: str, body: ExtractionIn, uid: str = Depends(current_user)):
        check = check_to_json(check_tax_document(to_tax_document(body.fields)))
        with connection() as db:
            scope(db, uid, org_id, doc_id)
            # Row-locking no-op: serialises with a concurrent review decision, and
            # refuses data changes once the document is approved or rejected.
            open_doc = db.execute('UPDATE documents SET status=status WHERE id=? AND organization_id=? '
                                  "AND status IN ('needs_review','needs_changes')", (doc_id, org_id))
            if open_doc.rowcount != 1:
                raise HTTPException(409, 'Document already decided; invoice data is locked')
            row = latest(db, org_id, doc_id)
            current = row['version'] if row else 0
            if body.version != current:
                raise HTTPException(409, 'Invoice data changed; reload before saving')
            try:
                _insert(db, org_id, doc_id, uid, current + 1, body.source, body.fields, check)
            except IntegrityError:
                raise HTTPException(409, 'Invoice data changed; reload before saving') from None
            audit(db, org_id, uid, 'document.extraction_saved', doc_id)
            return public(latest(db, org_id, doc_id))

    return router
