import urllib.request
import urllib.parse
import json
import re

with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

match = re.search(r'id=["\']gasUrl["\'][^>]*value=["\'](https://script\.google\.com/macros/s/[^"\']+/exec)["\']', html)
if not match:
    match = re.search(r'value=["\'](https://script\.google\.com/macros/s/[^"\']+/exec)["\'][^>]*id=["\']gasUrl["\']', html)

gas_url = match.group(1)
print(f"GAS URL: {gas_url[:60]}...")

# Test: 2-3실 2교시, 2026-05-20 (수요일)
rooms = ['2-3', '2-4', '2-5', '2-6']
for room in rooms:
    for period in ['1교시', '2교시']:
        params = {'date': '2026-05-20', 'day': '수', 'period': period, 'room': room}
        url = gas_url + '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            res = urllib.request.urlopen(req, timeout=15)
            data = json.loads(res.read().decode('utf-8'))
            student_count = len([k for k in data.keys() if k not in ('error', 'supervisor')]) if isinstance(data, dict) else 0
            print(f"\n=== {room} {period} === ({student_count}명)")
            if isinstance(data, dict):
                for sid, info in list(data.items())[:3]:
                    print(f"  {sid}: {info}")
                if student_count > 3:
                    print(f"  ... +{student_count - 3}명")
            else:
                print(f"  Response: {data}")
        except Exception as e:
            print(f"\n=== {room} {period} === ERROR: {e}")
