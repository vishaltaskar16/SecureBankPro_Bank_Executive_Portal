import os, django, sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','banking_system.settings')
django.setup()
from accounts.admin import admin_dashboard_data
from django.test import RequestFactory
from accounts.models import User
u=User.objects.filter(is_staff=True).first()
req=RequestFactory().get('/admin/dashboard-data/')
req.user=u
resp=admin_dashboard_data(req)
print('status', getattr(resp,'status_code',None))
print(resp.content[:1000])
