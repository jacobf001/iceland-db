import time
import requests

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "iceland-db/1.0 (fixtures ingestion)",
    "Accept-Language": "is,en;q=0.8",
})

def get(url: str, tries: int = 3, sleep_s: float = 1.5) -> str:
    last_err = None
    for i in range(tries):
        try:
            r = SESSION.get(url, timeout=25)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_err = e
            time.sleep(sleep_s * (i + 1))
    raise RuntimeError(f"GET failed: {url} ({last_err})")
