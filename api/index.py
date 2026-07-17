import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')

from crm.wsgi import application
app = application
