import os
import django
import sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'banking_system.settings')
django.setup()
from django.test import Client
from accounts.models import User
c = Client()
user = User.objects.filter(is_staff=True).first()
print('staff user:', bool(user), getattr(user,'email',None))
if user:
    c.force_login(user)
    r = c.get('/admin/dashboard-data/', HTTP_HOST='127.0.0.1')
    print('status', r.status_code)
    print(r.json())
else:
    print('No staff user')
