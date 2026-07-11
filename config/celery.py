import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('config')

# All Celery settings live in settings.py behind a CELERY_ prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
