FROM python:3.11.0-slim-buster

RUN apt-get update && apt-get -y install libpq-dev python3-dev build-essential

COPY requirements.txt requirements.txt

RUN pip3 install --upgrade pip \
    && pip3 install --upgrade -r requirements.txt

COPY . /takahe

WORKDIR /takahe

# We use development here to skip settings checks
RUN DJANGO_SETTINGS_MODULE=takahe.settings.development python3 manage.py collectstatic

EXPOSE 8000

# Set some sensible defaults
ENV GUNICORN_CMD_ARGS="--workers 8"

CMD ["sh", "/takahe/docker/start.sh"]
