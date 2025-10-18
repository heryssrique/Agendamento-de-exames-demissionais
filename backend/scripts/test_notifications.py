import requests
import os

BASE = os.environ.get('BASE_URL', 'http://127.0.0.1:8000')

# Dev login payload - use one of the ADMIN_EMAILS from .env
payload = {
    "email": "hhsjunior@gmail.com",
    "name": "Dev Admin",
    "department": "ADMIN"
}

s = requests.Session()

print('Creating dev session...')
resp = s.post(f"{BASE}/api/auth/dev-login", json=payload)
print(resp.status_code, resp.text)
if resp.status_code != 200:
    raise SystemExit('Dev login failed')

print('Calling test-notifications (dry_run)')
resp = s.post(f"{BASE}/api/admin/test-notifications", json={"dry_run": True})
print(resp.status_code)
print(resp.text)
