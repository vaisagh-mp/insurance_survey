"""
Production settings for insurance_survey project.
Requires DATABASE_URL (PostgreSQL) and sets DEBUG=False.
"""

from .base import *

DEBUG = env.bool('DEBUG', default=False)

# Database: Expects PostgreSQL DATABASE_URL, e.g.:
# postgres://user:password@hostname:5432/dbname
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }

# PostgreSQL configuration for production:
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'insurance_survey_db',
        'USER': 'postgres',
        'PASSWORD': 'admin@2026',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Production Security
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# HTTPS / SSL settings (can be overridden via environment variables if behind a reverse proxy)
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=False)
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=False)
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=False)
