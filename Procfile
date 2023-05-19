web: gunicorn takahe.wsgi:application --workers 8
worker: python manage.py runstator
release: python manage.py migrate
