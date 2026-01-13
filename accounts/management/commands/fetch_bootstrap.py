from django.core.management.base import BaseCommand
from django.conf import settings
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

BOOTSTRAP_CSS = "https://cdn.jsdelivr.net/npm/bootstrap@5.2.3/dist/css/bootstrap.min.css"
BOOTSTRAP_JS = "https://cdn.jsdelivr.net/npm/bootstrap@5.2.3/dist/js/bootstrap.bundle.min.js"


class Command(BaseCommand):
    """Fetch Bootstrap CSS/JS into static files for the admin dashboard."""
    help = "Fetch Bootstrap CSS/JS into static files for the admin dashboard."

    def handle(self, *args, **options):
        base = settings.BASE_DIR
        items = [
            (BOOTSTRAP_CSS, base / Path('static') / Path('css') / 'bootstrap.min.css'),
            (BOOTSTRAP_JS, base / Path('static') / Path('js') / 'bootstrap.bundle.min.js'),
        ]
        for url, target in items:
            target.parent.mkdir(parents=True, exist_ok=True)
            self.stdout.write(f"Fetching {url} ...")
            try:
                with urlopen(url) as resp:
                    data = resp.read()
                with open(target, 'wb') as f:
                    f.write(data)
                self.stdout.write(self.style.SUCCESS(f"Wrote {target} ({len(data)} bytes)"))
            except (URLError, HTTPError) as e:
                self.stderr.write(f"Failed to download {url}: {e}")
                raise SystemExit(1)

