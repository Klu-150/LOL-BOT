"""Limited GET retries and a per-instrument circuit breaker for public data."""
import json
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


class CircuitOpen(RuntimeError):
    pass


class ProviderRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        destination = urllib.parse.urlsplit(newurl)
        if destination.scheme != 'https' or destination.hostname != 'query1.finance.yahoo.com' or destination.port not in (None, 443):
            raise ValueError('Unexpected data-provider redirect')
        return super().redirect_request(request, fp, code, message, headers, newurl)


class FeedTransport:
    def __init__(self, opener=None, clock=time.monotonic, sleep=time.sleep, jitter=random.random):
        self.opener = opener or urllib.request.build_opener(ProviderRedirects()).open
        self.clock, self.sleep, self.jitter = clock, sleep, jitter
        self.states, self.lock = {}, threading.Lock()

    def fetch(self, url, instrument):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname != 'query1.finance.yahoo.com' or parsed.port not in (None, 443):
            raise ValueError('Unsupported market-data host')
        with self.lock:
            state = self.states.setdefault(instrument, {'failures': 0, 'retry_at': 0, 'busy': False})
            if self.clock() < state['retry_at'] or state['busy']:
                raise CircuitOpen('Market-data feed cooling down; no new entries authorised')
            state['busy'] = True
        try:
            for attempt in range(2):
                try:
                    request = urllib.request.Request(url, headers={'User-Agent': 'LastOfOurLeague/1.1 research'})
                    with self.opener(request, timeout=10) as response:
                        final = urllib.parse.urlsplit(response.geturl())
                        if final.scheme != 'https' or final.hostname != parsed.hostname:
                            raise ValueError('Unexpected data-provider redirect')
                        raw = response.read(8 * 1024 * 1024 + 1)
                    if len(raw) > 8 * 1024 * 1024:
                        raise ValueError('Market-data response too large')
                    result = json.loads(raw)
                    with self.lock:
                        state.update(failures=0, retry_at=0)
                    return result
                except (urllib.error.URLError, TimeoutError, OSError) as error:
                    retryable = not isinstance(error, urllib.error.HTTPError) or error.code in (408, 429, 500, 502, 503, 504)
                    if not retryable or attempt == 1:
                        raise
                    wait = min(16, 2 ** (state['failures'] + attempt)) + self.jitter()
                    if isinstance(error, urllib.error.HTTPError):
                        try:
                            wait = max(wait, min(30, float(error.headers.get('Retry-After', '0'))))
                        except (TypeError, ValueError):
                            pass
                    self.sleep(wait)
        except Exception:
            with self.lock:
                state['failures'] += 1
                if state['failures'] >= 3:
                    state['retry_at'] = self.clock() + 60
            raise
        finally:
            with self.lock:
                state['busy'] = False

    def status(self):
        with self.lock:
            return {symbol: {'failures': value['failures'], 'cooldown_seconds': max(0, round(value['retry_at'] - self.clock()))}
                    for symbol, value in self.states.items()}


transport = FeedTransport()
