from django.core.management.base import BaseCommand
from django.conf import settings
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

CHART_JS_URLS = [
    "https://cdn.jsdelivr.net/npm/chart.js@4.3.0/dist/chart.umd.min.js",
    "https://cdn.jsdelivr.net/npm/chart.js/dist/chart.umd.min.js",
    "https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.umd.min.js",
]


class Command(BaseCommand):
    """Fetch Chart.js UMD build and save to static/js/chart.umd.min.js"""
    help = "Fetch Chart.js UMD build and save to static/js/chart.umd.min.js"

    def handle(self, *args, **options):
        target = settings.BASE_DIR / Path('static') / Path('js') / 'chart.umd.min.js'
        target.parent.mkdir(parents=True, exist_ok=True)
        data = None
        for url in CHART_JS_URLS:
            self.stdout.write(f"Attempting to fetch Chart.js from {url} ...")
            try:
                with urlopen(url) as resp:
                    data = resp.read()
                self.stdout.write(self.style.SUCCESS(f"Downloaded {len(data)} bytes from {url}"))
                break
            except (URLError, HTTPError) as e:
                self.stderr.write(f"Failed to download from {url}: {e}")

        if not data:
            self.stderr.write("All attempts to fetch Chart.js failed.")
            raise SystemExit(1)

        with open(target, 'wb') as f:
            f.write(data)
        self.stdout.write(self.style.SUCCESS(f"Wrote {target} ({len(data)} bytes)"))
