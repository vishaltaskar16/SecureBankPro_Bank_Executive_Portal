import os
import django
import sys
from django.test import RequestFactory

# Ensure project base dir is in path and DJANGO_SETTINGS_MODULE set
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'banking_system.settings')
django.setup()

from accounts.models import User
from accounts.admin import admin_dashboard

u = User.objects.filter(is_staff=True).first()
if not u:
    print('No staff user found; cannot render admin dashboard')
    sys.exit(1)

rf = RequestFactory()
req = rf.get('/admin/')
req.user = u
resp = admin_dashboard(req)
resp.render()
content = resp.content.decode('utf-8')
start = content.find('<script type="application/json" id="chart-data">')
if start == -1:
    print('chart-data element not found')
else:
    snippet = content[start:start+500]
    print('--- chart-data snippet ---')
    print(snippet)
    print('--- raw JSON (trimmed) ---')
    s = snippet.split('>')[-1].rsplit('<', 1)[0]
    print(s[:400])

# Print KPIs
print('\n--- KPI values in template context ---')
from django.template import Context, Template
# Simple way: search for KPI values in rendered content
for kpi in ('Total Users','Total Transactions','Total Deposits','Total Withdrawals'):
    if kpi in content:
        print(f"Found KPI label: {kpi}")

# Print some recent transactions list snippet
ix = content.find('<tbody>')
if ix != -1:
    print('\n--- tbody snippet ---')
    print(content[ix:ix+400])
else:
    print('\nNo tbody found in rendered content')
