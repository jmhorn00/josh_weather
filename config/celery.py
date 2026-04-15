import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

app = Celery('wxradar')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'poll-mrms-mosaic': {
        'task': 'apps.radar.tasks.poll_mrms_mosaic',
        'schedule': 120.0,
    },
    'poll-active-stations': {
        'task': 'apps.radar.tasks.poll_active_stations',
        'schedule': 90.0,
    },
    'poll-nws-alerts': {
        'task': 'apps.radar.tasks.poll_nws_alerts',
        'schedule': 60.0,
    },
    'cleanup-old-data': {
        'task': 'apps.radar.tasks.cleanup_old_data',
        'schedule': crontab(minute=0),
    },
}
