"""Completeness and arithmetic checks for Czech VAT tax documents (daňové doklady).

Scope: checks that data read from an invoice or receipt carries the elements the VAT
Act requires and that its numbers agree. It never decides whether VAT is deductible,
how much tax is payable or which regime applies: under zákon č. 523/1992 Sb. that is
tax advice, which belongs to the business's accountant or tax adviser.

Legal basis (zákon č. 235/2004 Sb., o dani z přidané hodnoty, as in force from
1 January 2024; verify against e-Sbírka before showing citations to customers):
- § 29 odst. 1-3: mandatory elements of a tax document and permitted omissions
- § 30 odst. 1-2: simplified document allowed up to 10 000 Kč, with exclusions
- § 30a: elements a simplified document may omit
- § 47: rates 21 % (basic) and 12 % (reduced) for supplies from 1 January 2024

Findings are codes plus legal references, so the UI can translate them (VI/CS).
Amounts must be Decimal; floats are rejected so money is never rounded silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

VAT_ACT = 'zákon č. 235/2004 Sb.'
RATES_FROM = date(2024, 1, 1)
RATES = (Decimal('21'), Decimal('12'))
SIMPLIFIED_LIMIT = Decimal('10000')
DEFAULT_TOLERANCE = Decimal('1.00')  # plausibility tolerance in the document currency, not a legal rule

MISSING = 'missing'      # a mandatory element is absent
MISMATCH = 'mismatch'    # numbers do not agree
UNSUPPORTED = 'unsupported'  # outside the rule set this module knows
REVIEW = 'review'        # the accountant must confirm; the data alone cannot decide


@dataclass(frozen=True)
class VatLine:
    """One rate on the document: tax base and tax amount for that rate."""
    rate: Decimal | None
    base: Decimal | None = None
    tax: Decimal | None = None


@dataclass(frozen=True)
class TaxDocument:
    """Fields as read from the document. None means the field was not found."""
    supplier_name: str | None
    supplier_vat_id: str | None
    document_number: str | None
    subject: str | None
    issue_date: date | None
    lines: tuple[VatLine, ...] = ()
    total: Decimal | None = None
    currency: str = 'CZK'
    customer_name: str | None = None
    customer_vat_id: str | None = None
    supply_date: date | None = None
    exempt: bool = False
    reverse_charge: bool = False


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    field: str
    basis: str
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CheckResult:
    kind: str  # 'full' | 'simplified' | 'not_applicable'
    findings: tuple[Finding, ...]

    @property
    def complete(self) -> bool:
        return not any(f.severity in (MISSING, MISMATCH, UNSUPPORTED) for f in self.findings)


def _basis(section: str) -> str:
    return f'§ {section} {VAT_ACT}'


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _amounts(doc: TaxDocument):
    yield 'total', doc.total
    for line in doc.lines:
        yield 'rate', line.rate
        yield 'base', line.base
        yield 'tax', line.tax


def _document_kind(doc: TaxDocument) -> str:
    # § 30 odst. 2 písm. c): no simplified document when the customer declares the tax.
    # The 10 000 limit is in Kč, so a foreign-currency document is checked as a full one.
    if doc.reverse_charge or doc.currency.upper() != 'CZK' or doc.total is None or doc.total > SIMPLIFIED_LIMIT:
        return 'full'
    if _blank(doc.customer_name) and _blank(doc.customer_vat_id):
        return 'simplified'
    return 'full'


def check_tax_document(doc: TaxDocument, tolerance: Decimal = DEFAULT_TOLERANCE) -> CheckResult:
    for name, value in _amounts(doc):
        if value is not None and not isinstance(value, Decimal):
            raise TypeError(f'{name} must be Decimal, got {type(value).__name__}')
    if not isinstance(tolerance, Decimal):
        raise TypeError('tolerance must be Decimal')

    if doc.issue_date is not None and doc.issue_date < RATES_FROM:
        return CheckResult('not_applicable', (Finding('rules_before_2024', UNSUPPORTED, 'issue_date', _basis('47'),
                                                       {'rules_from': RATES_FROM.isoformat()}),))

    kind = _document_kind(doc)
    findings: list[Finding] = []

    def need(value, code, name, section):
        if _blank(value):
            findings.append(Finding(code, MISSING, name, _basis(section)))

    # Elements every tax document needs (§ 29 odst. 1; not omissible under § 30a).
    need(doc.supplier_name, 'supplier_name_missing', 'supplier_name', '29 odst. 1 písm. a)')
    need(doc.supplier_vat_id, 'supplier_vat_id_missing', 'supplier_vat_id', '29 odst. 1 písm. b)')
    need(doc.document_number, 'document_number_missing', 'document_number', '29 odst. 1 písm. e)')
    need(doc.subject, 'subject_missing', 'subject', '29 odst. 1 písm. f)')
    need(doc.issue_date, 'issue_date_missing', 'issue_date', '29 odst. 1 písm. g)')

    if kind == 'full':
        need(doc.customer_name, 'customer_name_missing', 'customer_name', '29 odst. 1 písm. c)')
        if _blank(doc.customer_vat_id):
            # § 29 odst. 3 písm. a): may be omitted when the customer has no DIČ.
            findings.append(Finding('customer_vat_id_unconfirmed', REVIEW, 'customer_vat_id', _basis('29 odst. 3 písm. a)')))

    rate_needed = not (doc.exempt or doc.reverse_charge)  # § 29 odst. 3 písm. d)
    if doc.exempt:
        findings.append(Finding('exemption_reference_check', REVIEW, 'exempt', _basis('29 odst. 2 písm. a)')))
    if doc.reverse_charge:
        findings.append(Finding('reverse_charge_wording_check', REVIEW, 'reverse_charge', _basis('29 odst. 2 písm. c)')))

    if rate_needed and not doc.lines:
        findings.append(Finding('rate_missing', MISSING, 'lines', _basis('29 odst. 1 písm. k)')))

    for index, line in enumerate(doc.lines):
        where = {'line': index}
        if line.rate is None:
            if rate_needed:
                findings.append(Finding('rate_missing', MISSING, 'rate', _basis('29 odst. 1 písm. k)'), where))
        elif line.rate not in RATES:
            findings.append(Finding('rate_unsupported', UNSUPPORTED, 'rate', _basis('47'),
                                    {**where, 'rate': str(line.rate), 'known': [str(r) for r in RATES]}))
        if kind == 'full' and rate_needed:
            if line.base is None:
                findings.append(Finding('base_missing', MISSING, 'base', _basis('29 odst. 1 písm. j)'), where))
            if line.tax is None:
                findings.append(Finding('tax_missing', MISSING, 'tax', _basis('29 odst. 1 písm. l)'), where))
        if line.rate in RATES and line.base is not None and line.tax is not None:
            expected = line.base * line.rate / Decimal(100)
            if abs(expected - line.tax) > tolerance:
                findings.append(Finding('tax_mismatch', MISMATCH, 'tax', _basis('29 odst. 1 písm. j)-l)'),
                                        {**where, 'expected': str(expected.quantize(Decimal('0.01'))), 'stated': str(line.tax)}))

    if kind == 'simplified' and any(line.tax is None for line in doc.lines) and doc.total is None:
        # § 30a odst. 2: without the tax amount the document must show the total paid.
        findings.append(Finding('total_missing', MISSING, 'total', _basis('30a odst. 2')))

    if doc.total is not None and doc.lines and all(l.base is not None and l.tax is not None for l in doc.lines):
        computed = sum((l.base + l.tax for l in doc.lines), Decimal(0))
        if abs(computed - doc.total) > tolerance:
            findings.append(Finding('total_mismatch', MISMATCH, 'total', _basis('29 odst. 1 písm. j)-l)'),
                                    {'computed': str(computed), 'stated': str(doc.total)}))

    if doc.currency.upper() != 'CZK' and rate_needed:
        # § 29 odst. 1 písm. l): the tax amount must also be stated in Czech currency.
        findings.append(Finding('tax_in_czk_check', REVIEW, 'currency', _basis('29 odst. 1 písm. l)'),
                                {'currency': doc.currency}))

    return CheckResult(kind, tuple(findings))
