# Build stage

FROM python:3.11.0-buster as builder

RUN mkdir -p /takahe
RUN python -m venv /takahe/.venv
RUN apt-get update && apt-get -y install libpq-dev python3-dev

WORKDIR /takahe

COPY requirements.txt requirements.txt

RUN . /takahe/.venv/bin/activate \
    && pip install --upgrade pip \
    && pip install --upgrade -r requirements.txt

# Final image stage

FROM python:3.11.0-slim-buster

RUN apt-get update && apt-get install -y libpq5

COPY --from=builder /takahe /takahe
COPY . /takahe

WORKDIR /takahe
EXPOSE 8000

CMD ["/takahe/docker/start.sh"]
