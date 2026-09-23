from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction

TWO_PLACES = Decimal('0.01')


def round_curr(val):
    """Round a numeric value to two decimal places."""
    if val is None:
        return Decimal('0.00')
    return Decimal(str(val)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@transaction.atomic
def recalculate_assessment(assessment):
    """
    Recalculates all financial figures for an assessment:
    - amount per AssessmentItem = quantity * rate (recompute and save each item first).
    - gross_assessed_loss = sum of AssessmentItem.assessed_amount.
    - underinsurance_amount = gross_assessed_loss * (underinsurance_percentage / 100) if underinsurance_percentage else 0.
    - adjusted_loss = gross_assessed_loss - salvage_amount - underinsurance_amount - depreciation_amount.
    - net_assessed_loss = max(adjusted_loss - policy_excess - other_deductions, 0).
    - Persists the assessment atomically.
    """
    # 1. Recompute and save each item's assessed_amount
    for item in assessment.items.select_for_update():
        qty = Decimal(str(item.quantity or 0))
        rate = Decimal(str(item.rate or 0))
        item.assessed_amount = round_curr(qty * rate)
        item.save(update_fields=['assessed_amount'])

    # 2. Gross assessed loss = sum of item assessed amounts
    gross = sum(
        (item.assessed_amount for item in assessment.items.all()),
        Decimal('0.00')
    )
    assessment.gross_assessed_loss = round_curr(gross)

    # 3. Underinsurance amount
    pct = Decimal(str(assessment.underinsurance_percentage or 0))
    if pct > Decimal('0.00'):
        underinsurance = (assessment.gross_assessed_loss * pct) / Decimal('100')
        assessment.underinsurance_amount = round_curr(underinsurance)
    else:
        assessment.underinsurance_amount = round_curr(assessment.underinsurance_amount or 0)

    # 4. Adjusted loss
    salvage = round_curr(assessment.salvage_amount or 0)
    underinsurance = assessment.underinsurance_amount
    depreciation = round_curr(assessment.depreciation_amount or 0)
    adjusted = assessment.gross_assessed_loss - salvage - underinsurance - depreciation
    assessment.adjusted_loss = round_curr(adjusted)

    # 5. Net assessed loss
    excess = round_curr(assessment.policy_excess or 0)
    deductions = round_curr(assessment.other_deductions or 0)
    net = adjusted - excess - deductions
    assessment.net_assessed_loss = round_curr(max(net, Decimal('0.00')))

    # 6. Save the assessment in one transaction
    assessment.save(update_fields=[
        'gross_assessed_loss',
        'underinsurance_amount',
        'adjusted_loss',
        'net_assessed_loss',
        'updated_at',
    ])

    return assessment
