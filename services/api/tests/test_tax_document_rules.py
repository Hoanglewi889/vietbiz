"""Czech VAT tax-document checks (§ 29, § 30, § 30a, § 47 zákon č. 235/2004 Sb.). Synthetic data only."""
from datetime import date
from decimal import Decimal as D

import pytest

from app.tax_document_rules import (
    MISMATCH,
    MISSING,
    REVIEW,
    UNSUPPORTED,
    TaxDocument,
    VatLine,
    check_tax_document,
)


def receipt(**changes):
    """Synthetic two-rate store receipt: 2 000 Kč at 12 % and 800 Kč at 21 %."""
    values = dict(supplier_name='Synthetic Wholesale s.r.o., Praha', supplier_vat_id='CZ00000001',
                  document_number='SYN-204', subject='Potraviny a drogerie', issue_date=date(2026, 10, 30),
                  lines=(VatLine(D('12'), D('2000.00'), D('240.00')), VatLine(D('21'), D('800.00'), D('168.00'))),
                  total=D('3208.00'))
    values.update(changes)
    return TaxDocument(**values)


def invoice(**changes):
    values = dict(customer_name='Synthetic Potraviny s.r.o., Brno', customer_vat_id='CZ00000002',
                  total=D('12100.00'), lines=(VatLine(D('21'), D('10000.00'), D('2100.00')),))
    values.update(changes)
    return receipt(**values)


def codes(result):
    return {f.code for f in result.findings}


def test_complete_two_rate_receipt_is_simplified_and_clean():
    result = check_tax_document(receipt())
    assert result.kind == 'simplified'
    assert result.findings == ()
    assert result.complete


def test_full_invoice_with_customer_is_clean():
    result = check_tax_document(invoice())
    assert result.kind == 'full'
    assert result.findings == () and result.complete


@pytest.mark.parametrize('field, code, basis', [
    ('supplier_name', 'supplier_name_missing', '§ 29 odst. 1 písm. a)'),
    ('supplier_vat_id', 'supplier_vat_id_missing', '§ 29 odst. 1 písm. b)'),
    ('document_number', 'document_number_missing', '§ 29 odst. 1 písm. e)'),
    ('subject', 'subject_missing', '§ 29 odst. 1 písm. f)'),
    ('issue_date', 'issue_date_missing', '§ 29 odst. 1 písm. g)'),
])
def test_elements_required_on_every_document(field, code, basis):
    result = check_tax_document(receipt(**{field: None}))
    finding = next(f for f in result.findings if f.code == code)
    assert finding.severity == MISSING and finding.field == field
    assert finding.basis.startswith(basis) and finding.basis.endswith('zákon č. 235/2004 Sb.')
    assert not result.complete


def test_blank_text_counts_as_missing():
    assert 'supplier_vat_id_missing' in codes(check_tax_document(receipt(supplier_vat_id='   ')))


def test_simplified_receipt_may_omit_base_and_tax_but_needs_total():
    lines = (VatLine(D('12')), VatLine(D('21')))
    assert check_tax_document(receipt(lines=lines)).findings == ()  # § 30a odst. 1 písm. d), e)
    result = check_tax_document(receipt(lines=lines, total=None))
    assert result.kind == 'full'  # no total: the 10 000 Kč limit cannot be confirmed
    assert {'base_missing', 'tax_missing', 'customer_name_missing'} <= codes(result)


def test_simplified_still_requires_rate():
    result = check_tax_document(receipt(lines=(VatLine(None, D('2000.00'), D('240.00')),), total=D('2240.00')))
    assert 'rate_missing' in codes(result)


def test_over_limit_without_customer_is_a_full_document():
    result = check_tax_document(invoice(customer_name=None, customer_vat_id=None))
    assert result.kind == 'full'
    assert 'customer_name_missing' in codes(result)
    assert 'customer_vat_id_unconfirmed' in codes(result)


def test_exactly_10000_kc_may_be_simplified():
    lines = (VatLine(D('21'), D('8264.46'), D('1735.54')),)
    assert check_tax_document(receipt(lines=lines, total=D('10000.00'))).kind == 'simplified'
    assert check_tax_document(receipt(lines=lines, total=D('10000.01'))).kind == 'full'


def test_missing_customer_vat_id_on_full_invoice_is_for_accountant_review():
    result = check_tax_document(invoice(customer_vat_id=None))
    finding = next(f for f in result.findings if f.code == 'customer_vat_id_unconfirmed')
    assert finding.severity == REVIEW and '§ 29 odst. 3 písm. a)' in finding.basis
    assert result.complete  # § 29 odst. 3 písm. a) allows omission when no DIČ was assigned


def test_wrong_tax_amount_is_flagged_with_expected_value():
    result = check_tax_document(receipt(lines=(VatLine(D('12'), D('2000.00'), D('260.00')),
                                               VatLine(D('21'), D('800.00'), D('168.00'))), total=D('3228.00')))
    finding = next(f for f in result.findings if f.code == 'tax_mismatch')
    assert finding.severity == MISMATCH
    assert finding.detail == {'line': 0, 'expected': '240.00', 'stated': '260.00'}


def test_rounding_within_one_crown_is_accepted():
    result = check_tax_document(receipt(lines=(VatLine(D('21'), D('99.90'), D('21.00')),), total=D('120.90')))
    assert 'tax_mismatch' not in codes(result)


def test_total_must_match_sum_of_lines():
    result = check_tax_document(receipt(total=D('3308.00')))
    finding = next(f for f in result.findings if f.code == 'total_mismatch')
    assert finding.detail == {'computed': '3208.00', 'stated': '3308.00'}


@pytest.mark.parametrize('rate', ['15', '10', '0', '19'])
def test_rates_outside_current_czech_set_are_unsupported(rate):
    result = check_tax_document(receipt(lines=(VatLine(D(rate), D('100.00'), D('1.00')),), total=D('101.00')))
    finding = next(f for f in result.findings if f.code == 'rate_unsupported')
    assert finding.severity == UNSUPPORTED and finding.detail['known'] == ['21', '12']
    assert 'tax_mismatch' not in codes(result)  # arithmetic is not judged against an unknown rate


def test_documents_before_2024_are_outside_this_rule_set():
    result = check_tax_document(receipt(issue_date=date(2023, 12, 31)))
    assert result.kind == 'not_applicable'
    assert [f.code for f in result.findings] == ['rules_before_2024']


def test_reverse_charge_needs_no_rate_but_is_never_simplified():
    result = check_tax_document(receipt(reverse_charge=True, lines=(VatLine(None, D('5000.00')),), total=D('5000.00')))
    assert result.kind == 'full'  # § 30 odst. 2 písm. c)
    assert 'rate_missing' not in codes(result) and 'tax_missing' not in codes(result)
    assert 'reverse_charge_wording_check' in codes(result)


def test_exempt_supply_asks_accountant_to_check_legal_reference():
    result = check_tax_document(invoice(exempt=True, lines=(VatLine(None, D('12100.00')),)))
    assert 'exemption_reference_check' in codes(result)
    assert 'rate_missing' not in codes(result)


def test_foreign_currency_is_a_full_document_and_needs_tax_in_czk():
    result = check_tax_document(receipt(currency='EUR', total=D('128.32'),
                                        lines=(VatLine(D('21'), D('106.05'), D('22.27')),)))
    assert result.kind == 'full'
    assert 'tax_in_czk_check' in codes(result)


def test_floats_are_rejected():
    with pytest.raises(TypeError):
        check_tax_document(receipt(total=3208.0))
    with pytest.raises(TypeError):
        check_tax_document(receipt(lines=(VatLine(D('21'), 800.0, D('168.00')),)))


def test_result_never_states_deductibility():
    result = check_tax_document(invoice())
    text = repr(result).lower()
    assert 'deduct' not in text and 'odpočet' not in text
