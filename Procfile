web: gunicorn takahe.wsgi:application --workers ${TAKAHE_WORKERS:-8}
worker: python manage.py runstator
release: python manage.py migrate
