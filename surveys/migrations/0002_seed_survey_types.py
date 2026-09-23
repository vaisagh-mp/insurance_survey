from django.db import migrations


SURVEY_TYPES = [
    {"name": "Engineering", "code": "ENG", "description": "Engineering and industrial risk surveys"},
    {"name": "Fire", "code": "FIRE", "description": "Fire and allied perils damage assessment surveys"},
    {"name": "Marine", "code": "MARINE", "description": "Marine cargo, hull, and transit loss surveys"},
    {"name": "Property", "code": "PROPERTY", "description": "Commercial and residential property damage surveys"},
]


def seed_survey_types(apps, schema_editor):
    SurveyType = apps.get_model('surveys', 'SurveyType')
    for item in SURVEY_TYPES:
        SurveyType.objects.get_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "description": item["description"],
                "is_active": True,
            }
        )


def unseed_survey_types(apps, schema_editor):
    SurveyType = apps.get_model('surveys', 'SurveyType')
    codes = [item["code"] for item in SURVEY_TYPES]
    SurveyType.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_survey_types, reverse_code=unseed_survey_types),
    ]
