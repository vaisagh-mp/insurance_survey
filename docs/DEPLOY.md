# Production Deployment Guide — Insurance Survey System

> **Target Environments:** Render / PaaS & Linux Virtual Machines (Ubuntu 22.04 / 24.04 LTS / Debian 12)  
> **Application Server:** Gunicorn 22.x (with WhiteNoise for static assets)  
> **Database:** PostgreSQL 15+  
> **Cache Backend:** Redis 7+  
> **PDF Engine:** WeasyPrint 70+  

---

## 1. Quick Deploy on Render.com (PaaS)

### Build & Start Commands
- **Build Command:** `./build.sh` (or `bash build.sh`)
- **Start Command:** `gunicorn config.wsgi:application --workers 3 --bind 0.0.0.0:$PORT`

### Required Environment Variables on Render:
| Variable | Value / Description |
| :--- | :--- |
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `DEBUG` | `False` |
| `SECRET_KEY` | *(Click "Generate" or provide a secure key)* |
| `ALLOWED_HOSTS` | `insurance-survey-3anl.onrender.com,.onrender.com,localhost,127.0.0.1` |
| `CSRF_TRUSTED_ORIGINS` | `https://insurance-survey-3anl.onrender.com,https://*.onrender.com` |
| `DATABASE_URL` | *(Internal Database URL from Render PostgreSQL service)* |
| `REDIS_URL` | *(Internal Redis URL from Render Redis service)* |
| `FIRM_NAME` | `SOTERIA Insurance Surveyors & Loss Assessors Pvt. Ltd.` |
| `FIRM_ADDRESS` | `Z3215, 3rd floor, Akshar Business Park, Sector 25 Vashi-Thurbe, Navi Mumbai, Maharashtra-400703` |
| `FIRM_GSTIN` | `27AAACS0000A1Z5` *(Replace with real firm GSTIN before live billing)* |
| `SECURE_SSL_REDIRECT` | `True` |
| `SESSION_COOKIE_SECURE` | `True` |
| `CSRF_COOKIE_SECURE` | `True` |

---

## 2. Linux VPS / Bare Metal Deployment (Ubuntu / Debian)

### Native System Dependencies
Install system libraries required by WeasyPrint, psycopg2, and Pillow:

```bash
sudo apt-get update && sudo apt-get install -y \
    python3-pip python3-venv python3-dev build-essential \
    libpq-dev postgresql postgresql-contrib redis-server nginx \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libpango1.0-dev \
    libcairo2 libgdk-pixbuf2.0-0 libglib2.0-0 fonts-dejavu-core fonts-liberation \
    certbot python3-certbot-nginx
```

---

## 3. Directory Setup & Permissions

```bash
sudo mkdir -p /var/www/insurance_survey
sudo chown -R $USER:www-data /var/www/insurance_survey
cd /var/www/insurance_survey

# Setup Python Virtual Environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4. Gunicorn & Nginx Configuration

1. **Systemd Service:**
   ```bash
   sudo cp deploy/insurance_survey.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now insurance_survey
   ```

2. **Nginx Reverse Proxy:**
   ```bash
   sudo cp deploy/nginx.conf /etc/nginx/sites-available/insurance_survey
   sudo ln -s /etc/nginx/sites-available/insurance_survey /etc/nginx/sites-enabled/
   sudo rm -f /etc/nginx/sites-enabled/default
   sudo nginx -t && sudo systemctl reload nginx
   ```

> **CRITICAL SECURITY NOTE:**  
> In `deploy/nginx.conf`, `/static/` is served directly by Nginx, but **`/media/` MUST be proxied to Gunicorn/Django** (`proxy_pass http://gunicorn_app;`). This ensures `secure_media_view` enforces claim-scoped permissions (only Admins and the assigned Surveyor can view uploaded inspection photos and claim documents).

---

## 5. Automated Backups

Schedule daily automated PostgreSQL dump and media file archiving:
```bash
chmod +x deploy/backup.sh
# Crontab entry:
# 0 2 * * * /var/www/insurance_survey/deploy/backup.sh >> /var/log/insurance_survey_backup.log 2>&1
```
