ARG IMAGE_HOST=python
ARG IMAGE_LABEL=3.11.0-slim-buster

FROM ${IMAGE_HOST}:${IMAGE_LABEL}

RUN apt-get update && apt-get -y install libpq-dev libxml2-dev libxslt1-dev zlib1g-dev python3-dev build-essential

COPY requirements.txt requirements.txt

RUN pip3 install --upgrade pip \
    && pip3 install --upgrade -r requirements.txt

COPY . /takahe

WORKDIR /takahe

RUN TAKAHE_DATABASE_SERVER="postgres://x@example.com/x" python3 manage.py collectstatic

EXPOSE 8000

# Set some sensible defaults
ENV GUNICORN_CMD_ARGS="--workers 8"

CMD ["gunicorn", "takahe.wsgi:application", "-b", "0.0.0.0:8000"]
