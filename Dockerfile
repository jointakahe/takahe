FROM python:3.9-bullseye as builder

RUN mkdir -p /takahe
RUN python -m venv /takahe/.venv
RUN apt-get update && apt-get -y install libpq-dev python3-dev

WORKDIR /takahe

COPY requirements.txt requirements.txt

RUN . /takahe/.venv/bin/activate \
    && pip install --upgrade pip \
    && pip install --upgrade -r requirements.txt


FROM python:3.9-slim-bullseye

RUN apt-get update && apt-get install -y libpq5

COPY --from=builder /takahe /takahe
COPY . /takahe

WORKDIR /takahe
EXPOSE 8000

CMD ["/takahe/scripts/start.sh"]
