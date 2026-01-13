from django.template.loader import get_template
from django.template import TemplateSyntaxError
import traceback

try:
    t = get_template('admin/dashboard.html')
    print('Template OK')
except TemplateSyntaxError as e:
    print('TemplateSyntaxError:')
    traceback.print_exc()