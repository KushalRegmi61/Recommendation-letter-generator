# Simple production image: gunicorn + whitenoise, config from the environment.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=auth.settings

# Runtime lib for opencv-python-headless (libGL is avoided by -headless, but
# glib is still needed). Everything else ships as manylinux wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements.txt is UTF-16 encoded in this repo; convert it so pip can read it.
COPY requirements.txt /tmp/requirements-utf16.txt
RUN python -c "open('/tmp/requirements.txt','w').write(open('/tmp/requirements-utf16.txt',encoding='utf-16').read())" \
    && pip install --upgrade pip \
    && pip install -r /tmp/requirements.txt

COPY . /app

# Collect static during build (no DB touched: DATABASE_URL is unset here, so
# settings fall back to SQLite and collectstatic just reads STATICFILES_DIRS).
RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Apply migrations, then serve. Config (DATABASE_URL, secrets) comes from the
# environment / --env-file at run time.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn auth.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3 --timeout 120"]
