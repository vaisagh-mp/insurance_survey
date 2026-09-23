from django.db import migrations

DOCUMENT_TYPES = [
    {"code": "POLICY", "name": "Insurance Policy"},
    {"code": "CLAIM_FORM", "name": "Claim Form"},
    {"code": "POLICE_REPORT", "name": "Police Report / FIR"},
    {"code": "FIRE_BRIGADE_REPORT", "name": "Fire Brigade Report"},
    {"code": "INVOICE", "name": "Invoice"},
    {"code": "ESTIMATE", "name": "Repair / Replacement Estimate"},
    {"code": "PURCHASE_INVOICE", "name": "Purchase Invoice"},
    {"code": "SALES_INVOICE", "name": "Sales Invoice"},
    {"code": "STOCK_REGISTER", "name": "Stock Register"},
    {"code": "VALUATION_CERTIFICATE", "name": "Valuation Certificate"},
    {"code": "CA_CERTIFICATE", "name": "Chartered Accountant (CA) Certificate"},
    {"code": "WORK_ORDER", "name": "Work Order"},
    {"code": "BILL_OF_ENTRY", "name": "Bill of Entry"},
    {"code": "FAR", "name": "Fixed Asset Register (FAR)"},
    {"code": "PHOTOGRAPH", "name": "Photograph"},
    {"code": "ILA", "name": "Immediate Loss Advice (ILA)"},
    {"code": "ISR", "name": "Interim Survey Report (ISR)"},
    {"code": "FSR", "name": "Final Survey Report (FSR)"},
    {"code": "OTHER", "name": "Other Supporting Document"},
]


def seed_document_types(apps, schema_editor):
    DocumentType = apps.get_model('documents', 'DocumentType')
    for item in DOCUMENT_TYPES:
        DocumentType.objects.get_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "is_active": True,
            }
        )


def unseed_document_types(apps, schema_editor):
    DocumentType = apps.get_model('documents', 'DocumentType')
    codes = [item["code"] for item in DOCUMENT_TYPES]
    DocumentType.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_document_types, reverse_code=unseed_document_types),
    ]
