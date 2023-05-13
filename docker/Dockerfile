ARG IMAGE_HOST=python
ARG IMAGE_LABEL=3.11-slim-bullseye

FROM ${IMAGE_HOST}:${IMAGE_LABEL}

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

RUN TAKAHE_DATABASE_SERVER="postgres://x@example.com/x" TAKAHE_SECRET_KEY="takahe" TAKAHE_MAIN_DOMAIN="static.test" python3 manage.py collectstatic --noinput

EXPOSE 8000

# Set some sensible defaults
ENV GUNICORN_CMD_ARGS="--workers 8"

CMD ["bash", "docker/run.sh"]
