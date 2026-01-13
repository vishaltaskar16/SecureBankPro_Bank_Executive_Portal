import os, django, sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','banking_system.settings')
django.setup()
from django.urls import reverse
print('reverse admin-dashboard-data ->', reverse('admin-dashboard-data'))
