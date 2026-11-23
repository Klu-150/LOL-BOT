"""Download the latest Nifty 50 and India VIX daily closes into data/."""
import urllib.request
from pathlib import Path

import config as C

ROOT = Path(__file__).resolve().parent


def fetch(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as r:
        dest.write_bytes(r.read())
    lines = dest.read_text().strip().splitlines()
    print(f"{dest.name}: {len(lines) - 1} rows, last = {lines[-1].split(',')[0]}")


if __name__ == "__main__":
    fetch(C.NIFTY_URL, ROOT / C.NIFTY_CSV)
    fetch(C.VIX_URL, ROOT / C.VIX_CSV)
