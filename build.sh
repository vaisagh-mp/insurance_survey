#!/usr/bin/env bash
# ==============================================================================
# Render Build & Deployment Script for Insurance Survey System
# ==============================================================================
# Exit immediately if a command exits with a non-zero status
set -o errexit

echo "==> Upgrading pip and installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Collecting static assets via WhiteNoise..."
python manage.py collectstatic --no-input

echo "==> Applying database migrations..."
python manage.py migrate --no-input

# Optional: Automatically create superuser on deployment if environment variables are configured
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "==> Ensuring superuser exists..."
    python manage.py createsuperuser --no-input || true
fi

echo "==> Build process completed successfully!"
