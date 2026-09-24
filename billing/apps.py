from django.apps import AppConfig
from django.core.checks import register, Tags, Warning

PLACEHOLDER_FIRM_GSTIN = '27AAACS0000A1Z5'


@register(Tags.security)
def check_firm_gstin_production(app_configs, **kwargs):
    from django.conf import settings
    errors = []
    # If DEBUG is False (production mode), warn if FIRM_GSTIN is still the placeholder value
    if not getattr(settings, 'DEBUG', True):
        firm_gstin = getattr(settings, 'FIRM_GSTIN', '')
        if firm_gstin == PLACEHOLDER_FIRM_GSTIN:
            errors.append(
                Warning(
                    "FIRM_GSTIN is currently set to the default placeholder value ('27AAACS0000A1Z5') with DEBUG=False. "
                    "Set the real surveying firm's GSTIN in environment variable FIRM_GSTIN before generating production invoices.",
                    id='billing.W001',
                    hint='Configure FIRM_GSTIN in your environment or .env file.',
                )
            )
    return errors


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'billing'
