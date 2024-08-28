ARG IMAGE_HOST=python
ARG IMAGE_LABEL=3.11-slim-bullseye

FROM ${IMAGE_HOST}:${IMAGE_LABEL}

ARG TAKAHE_DATABASE_SERVER
ARG TAKAHE_DEBUG
ARG TAKAHE_SECRET_KEY
ARG TAKAHE_CSRF_HOSTS
ARG TAKAHE_USE_PROXY_HEADERS
ARG TAKAHE_EMAIL_BACKEND
ARG TAKAHE_MEDIA_BACKEND
ARG TAKAHE_MAIN_DOMAIN
ARG TAKAHE_ENVIRONMENT
ARG TAKAHE_AUTO_ADMIN_EMAIL

ENV TAKAHE_DATABASE_SERVER ${TAKAHE_DATABASE_SERVER}
ENV TAKAHE_DEBUG ${TAKAHE_DEBUG}
ENV TAKAHE_SECRET_KEY ${TAKAHE_SECRET_KEY}
ENV TAKAHE_CSRF_HOSTS ${TAKAHE_CSRF_HOSTS}
ENV TAKAHE_USE_PROXY_HEADERS ${TAKAHE_USE_PROXY_HEADERS}
ENV TAKAHE_EMAIL_BACKEND ${TAKAHE_EMAIL_BACKEND}
ENV TAKAHE_MEDIA_BACKEND ${TAKAHE_MEDIA_BACKEND}
ENV TAKAHE_MAIN_DOMAIN ${TAKAHE_MAIN_DOMAIN}
ENV TAKAHE_ENVIRONMENT ${TAKAHE_ENVIRONMENT}
ENV TAKAHE_AUTO_ADMIN_EMAIL ${TAKAHE_AUTO_ADMIN_EMAIL}

ENV PYTHONUNBUFFERED=1

COPY requirements.txt requirements.txt

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        libxslt1.1 \
        nginx \
        busybox \
        netcat \
        gcc \
        libc6-dev \
        libpq-dev \
        # Required to build lxml on arm64.
        libxslt1-dev \
        zlib1g-dev \
        postgresql-client \
    && python3 -m pip install --no-cache-dir --upgrade -r requirements.txt \
    && apt-get purge -y --auto-remove \
        gcc \
        libc6-dev \
        libpq-dev \
        libxslt1-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /cache

# Python mimetypes package is missing some common mappings
COPY docker/mime.types /etc/mime.types

# Configure nginx
COPY docker/nginx.conf /etc/nginx/
COPY docker/nginx.conf.d/* /etc/nginx/conf.d/

COPY . /takahe

# Sanity-test the nginx config
RUN nginx -t

WORKDIR /takahe

RUN python3 manage.py collectstatic --noinput

EXPOSE 8000

# Set some sensible defaults
ENV GUNICORN_CMD_ARGS="--workers 8"

CMD ["bash", "docker/run.sh"]
