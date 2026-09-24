"""
Production settings for insurance_survey project.
Configured for production deployment with Gunicorn, Nginx, Render, PostgreSQL, Redis,
WhiteNoise static asset compression, HTTPS security headers, and structured logging.
"""

from .base import *

# 1. Core Production Settings
DEBUG = False

ALLOWED_HOSTS = env.list(
    'ALLOWED_HOSTS',
    default=['127.0.0.1', 'localhost', 'insurance-survey-3anl.onrender.com', '.onrender.com']
)

CSRF_TRUSTED_ORIGINS = env.list(
    'CSRF_TRUSTED_ORIGINS',
    default=[
        'https://insurance-survey-3anl.onrender.com',
        'https://*.onrender.com',
        'http://localhost:8000',
        'http://127.0.0.1:8000',
    ]
)

# 2. Database: PostgreSQL via DATABASE_URL
# Expects e.g. postgres://user:password@hostname:5432/dbname
DATABASES = {
    'default': env.db(
        'DATABASE_URL',
        default='postgres://postgres:admin@localhost:5432/insurance_survey_db'
    )
}

# 3. WhiteNoise Static File Serving & Middleware Configuration
# WhiteNoiseMiddleware MUST sit immediately after SecurityMiddleware
MIDDLEWARE = list(MIDDLEWARE)
if 'django.middleware.security.SecurityMiddleware' in MIDDLEWARE:
    security_idx = MIDDLEWARE.index('django.middleware.security.SecurityMiddleware')
    MIDDLEWARE.insert(security_idx + 1, 'whitenoise.middleware.WhiteNoiseMiddleware')
else:
    MIDDLEWARE.insert(0, 'whitenoise.middleware.WhiteNoiseMiddleware')

# Content-hashed, compressed static files with far-future caching headers
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# 4. HTTPS & Security Hardening
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=True)
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=True)
SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=31536000)  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True)
SECURE_HSTS_PRELOAD = env.bool('SECURE_HSTS_PRELOAD', default=True)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# 5. Shared Cache Backend (Redis via django-redis)
# Multiple Gunicorn worker processes share this cache so DRF login rate throttling
# (5 attempts/min) is strictly enforced across all worker processes.
REDIS_URL = env('REDIS_URL', default='redis://127.0.0.1:6379/1')
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'IGNORE_EXCEPTIONS': True,  # Fall back gracefully if Redis is temporarily unreachable
        }
    }
}

# 6. Structured Logging Configuration (Console + Rotating File Handler)
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} [{name}:{lineno}] {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'insurance_survey.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB per file
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console', 'file'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# 7. Surveying Firm Profile (Overridable via environment variables in production)
FIRM_NAME = env('FIRM_NAME', default=FIRM_NAME)
FIRM_ADDRESS = env('FIRM_ADDRESS', default=FIRM_ADDRESS)
FIRM_GSTIN = env('FIRM_GSTIN', default=FIRM_GSTIN)
