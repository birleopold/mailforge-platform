import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mailforge.settings")

app = Celery("mailforge")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
