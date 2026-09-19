"""Resolve the browser-facing origin without trusting arbitrary proxy headers."""
import os
from urllib.parse import urlsplit


def trusted_proxy(scope):
    peer = (scope.get('client') or ('', 0))[0]
    return peer in {value.strip() for value in os.getenv('TRUSTED_PROXY_IPS', '127.0.0.1,::1').split(',') if value.strip()}


def public_scheme(scope, headers):
    # The immediate trusted proxy must overwrite these headers, never append.
    forwarded = headers.get('x-forwarded-proto', '').lower()
    if trusted_proxy(scope) and forwarded in {'http', 'https'}:
        return forwarded
    return scope.get('scheme', 'http')


def normalize_origin(value):
    if not value or any(char.isspace() or ord(char) < 32 for char in value) or any(char in value for char in ('\\', ',', '%')):
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in {'', '/'} or parsed.query or parsed.fragment):
            return None
        return (parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == 'https' else 80))
    except ValueError:
        return None


def origin_allowed(scope, headers):
    origin = headers.get('origin')
    # Preserve non-browser API calls; explicit cross-site browser requests still fail.
    if origin is None:
        return headers.get('sec-fetch-site') != 'cross-site'
    source = normalize_origin(origin)
    if source is None:
        return False
    # Older BaoTa proxy rules replace Host with the internal upstream and omit
    # X-Forwarded-Host. Keep the actual production origin explicit in that case.
    configured = os.getenv('ALLOWED_ORIGINS', '').strip() or 'https://www.wiscomper.com'
    allowed = {normalize_origin(value.strip()) for value in configured.split(',')}
    allowed.update({normalize_origin('http://127.0.0.1:5173'), normalize_origin('http://localhost:5173')})
    if source in allowed:
        return True
    if headers.get('sec-fetch-site') == 'cross-site':
        return False
    authority = headers.get('host', '')
    if trusted_proxy(scope) and 'x-forwarded-host' in headers:
        authority = headers['x-forwarded-host']
    target = normalize_origin(public_scheme(scope, headers) + '://' + authority)
    return target is not None and source == target
