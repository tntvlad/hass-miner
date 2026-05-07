import json
import sys

har_path = r'c:\Users\home\Documents\git\hass-miner\har_files\192.168.1.21-vnis-manual.har'

with open(har_path, encoding='utf-8') as f:
    har = json.load(f)

entries = har['log']['entries']
print(f'Total entries: {len(entries)}')
print()

for e in entries:
    req = e['request']
    resp = e['response']
    url = req['url']
    method = req['method']
    status = resp['status']
    # strip query string for display
    short_url = url.split('?')[0]
    print(f'{method} {status}  {short_url}')

print()
print('=== RESPONSE BODIES for API calls ===')
for e in entries:
    req = e['request']
    resp = e['response']
    url = req['url']
    method = req['method']
    if '/api/' not in url:
        continue
    body = resp.get('content', {}).get('text', '')
    if not body:
        continue
    print(f'\n--- {method} {url} ---')
    try:
        parsed = json.loads(body)
        print(json.dumps(parsed, indent=2)[:3000])
    except Exception:
        print(body[:1000])

print()
print('=== REQUEST BODIES for POST/PATCH/PUT ===')
for e in entries:
    req = e['request']
    url = req['url']
    method = req['method']
    if method not in ('POST', 'PATCH', 'PUT'):
        continue
    post_data = req.get('postData', {})
    body = post_data.get('text', '')
    if not body:
        continue
    print(f'\n--- {method} {url} ---')
    try:
        parsed = json.loads(body)
        print(json.dumps(parsed, indent=2)[:3000])
    except Exception:
        print(body[:1000])
