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

echo "==> Build process completed successfully!"
