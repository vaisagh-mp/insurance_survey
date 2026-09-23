"""
Development settings for insurance_survey project.
Uses SQLite by default and enables DEBUG.
"""

from .base import *

DEBUG = env.bool('DEBUG', default=True)

# Database: Default to SQLite for local development
DATABASES = {
    'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')
}

# Allow all origins in local development
CORS_ALLOW_ALL_ORIGINS = True
