import os
import re
import sys
import json
import time
import datetime
import urllib.request
import urllib.parse
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

# ────────────────────────────────────────────────
# 유틸리티 함수
# ────────────────────────────────────────────────

def fetch_with_retry(url, max_retries=3):
    """URL에서 JSON 데이터를 가져오되, 실패 시 최대 max_retries회 재시도"""
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as res:
                return json.loads(res.read().decode('utf-8'))
        except Exception:
            if attempt < max_retries:
                time.sleep(2 * attempt)
    return None

def input_with_timeout(prompt, timeout=5.0):
    if not sys.stdin.isatty():
        print(prompt + " [Non-interactive: using default]")
        return None
    try:
        import msvcrt
        print(prompt, end="", flush=True)
        start_time = time.time()
        input_chars = []
        while True:
            if msvcrt.kbhit():
                while True:
                    char = msvcrt.getwche()
                    if char in ('\r', '\n'):
                        print()
                        return "".join(input_chars)
                    elif char == '\b':
                        if input_chars:
                            input_chars.pop()
                            print('\b \b', end="", flush=True)
                    else:
                        input_chars.append(char)
            if time.time() - start_time > timeout:
                print()
                return None
            time.sleep(0.05)
    except ImportError:
        print(prompt)
        return None

# ────────────────────────────────────────────────
# 메인 로직
# ────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  2학년 야간자율학습 '주간' 출결 보고서 생성기")
    print("=" * 60)

    # 1. index.html에서 GAS URL 추출
    script_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(script_dir, 'index.html')

    if not os.path.exists(html_path):
        print(f"[오류] index.html 파일을 찾을 수 없습니다.")
        input("엔터키를 누르면 종료됩니다...")
        sys.exit(1)

    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        match = re.search(r'id=["\']gasUrl["\'][\s\S]*?value=["\'](https://script\.google\.com/macros/s/[^"\']+/exec)["\']', html_content)
        if not match:
            match = re.search(r'value=["\'](https://script\.google\.com/macros/s/[^"\']+/exec)["\'][\s\S]*?id=["\']gasUrl["\']', html_content)
        if not match:
            # 최종 예비 수단: input 태그와 상관없이 첫 번째 exec URL 추출
            match = re.search(r'(https://script\.google\.com/macros/s/[a-zA-Z0-9_-]+/exec)', html_content)
        if not match:
            print("[오류] GAS URL을 추출하지 못했습니다.")
            input("엔터키를 누르면 종료됩니다...")
            sys.exit(1)
        gas_url = match.group(1)
        print(f"[OK] GAS 웹앱 URL 추출 성공: {gas_url}")
    except Exception as e:
        print(f"[오류] {e}")
        input("엔터키를 누르면 종료됩니다...")
        sys.exit(1)

    # 2. 대상 주간 결정
    today = datetime.date.today()
    # 이번 주 월요일 계산
    this_monday = today - datetime.timedelta(days=today.weekday())
    
    # 월요일이거나 주말이면 지난 주를 기본값으로
    if today.weekday() == 0 or today.weekday() >= 5:
        default_monday = this_monday - datetime.timedelta(weeks=1)
    else:
        default_monday = this_monday

    default_friday = default_monday + datetime.timedelta(days=4)
    default_monday_str = default_monday.strftime("%Y-%m-%d")
    default_friday_str = default_friday.strftime("%Y-%m-%d")

    print(f"\n기본 대상 주간: {default_monday_str}(월) ~ {default_friday_str}(금)")
    
    target_monday = default_monday
    # 명령줄 인자가 제공되었는지 확인 (예: python print_yaja_weekly.py 2026-05-20)
    if len(sys.argv) > 1:
        date_arg = sys.argv[1].strip()
        try:
            parsed = datetime.datetime.strptime(date_arg, "%Y-%m-%d").date()
            target_monday = parsed - datetime.timedelta(days=parsed.weekday())
            if target_monday != parsed:
                print(f"-> 입력 날짜가 월요일이 아니어서 해당 주 월요일({target_monday.strftime('%Y-%m-%d')})로 보정합니다.")
        except ValueError:
            print("[오류] 입력된 날짜 형식이 올바르지 않습니다 (YYYY-MM-DD 필요). 기본 주간으로 진행합니다.")
    else:
        print("-> 추가 명령줄 인자가 없어 기본 주간으로 진행합니다. (원하는 주간 지정 방법: python 스크립트명 YYYY-MM-DD)")

    target_friday = target_monday + datetime.timedelta(days=4)
    
    # 5일치 날짜/요일 정보
    day_names = ['월', '화', '수', '목', '금']
    week_days = []
    for i in range(5):
        d = target_monday + datetime.timedelta(days=i)
        week_days.append({'date': d, 'date_str': d.strftime("%Y-%m-%d"), 'day_name': day_names[i]})

    print(f"\n-> 대상 주간: {target_monday.strftime('%Y-%m-%d')}(월) ~ {target_friday.strftime('%Y-%m-%d')}(금)")

    # 3. 학생 명단 로드
    print("\n[1/3] 학생 명단을 구글 시트에서 가져오는 중...")
    try:
        student_url = f"{gas_url}?action=getStudents"
        students = fetch_with_retry(student_url)
        if not students:
            raise Exception("응답이 없습니다")
        print(f"[OK] 학생 {len(students)}명 명단 로드 성공")
    except Exception as e:
        print(f"[오류] 학생 명단을 가져오는 데 실패했습니다: {e}")
        input("엔터키를 누르면 종료됩니다...")
        sys.exit(1)

    # 4. 5일치 출결 로그 병렬 로드
    print("\n[2/3] 주간 출결 로그를 구글 시트에서 가져오는 중...")
    rooms = ['2-3', '2-4', '2-5', '2-6']
    periods = ['1교시', '2교시']

    # 전체 요청 목록 생성: 5일 × 4교실 × 2교시 = 40 요청
    fetch_tasks = []
    for wd in week_days:
        for room in rooms:
            for period in periods:
                params = {
                    'date': wd['date_str'],
                    'day': wd['day_name'],
                    'period': period,
                    'room': room
                }
                fetch_tasks.append(params)

    total = len(fetch_tasks)
    print(f"   총 {total}개 요청을 병렬로 처리합니다 (4개씩 동시)...")

    # 결과 저장: attendance_weekly[student_id][day_name + period_num] = status_str
    attendance_weekly = {}
    completed = [0]
    failed_count = [0]

    def do_fetch(params):
        url = gas_url + '?' + urllib.parse.urlencode(params)
        data = fetch_with_retry(url, max_retries=3)
        completed[0] += 1
        if completed[0] % 8 == 0 or completed[0] == total:
            print(f"   -> 진행률: {completed[0]}/{total}")
        return (params['day'], params['period'], data)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(do_fetch, p) for p in fetch_tasks]
        for future in as_completed(futures):
            try:
                day_name, period, data = future.result()
                period_num = '1' if period == '1교시' else '2'
                key_prefix = day_name + period_num  # 예: '월1', '화2'

                if data and isinstance(data, dict) and 'error' not in data:
                    for s_id, att in data.items():
                        s_id = str(s_id).strip()
                        if not s_id or s_id in ("error", "supervisor"):
                            continue
                        if s_id not in attendance_weekly:
                            attendance_weekly[s_id] = {}

                        status_val = att.get('status')
                        if status_val is True or str(status_val).lower() == 'true' or status_val == '출석':
                            attendance_weekly[s_id][key_prefix] = '출석'
                        else:
                            attendance_weekly[s_id][key_prefix] = '결석'
                else:
                    failed_count[0] += 1
            except Exception:
                failed_count[0] += 1

    if failed_count[0] > 0:
        print(f"[경고] {failed_count[0]}개 요청 실패 (해당 데이터는 '미체크'로 표시)")
    print(f"[OK] 주간 출결 로그 병합 완료 (체크된 학생: {len(attendance_weekly)}명)")

    # 5. 학급별 보고서 생성
    print("\n[3/3] 학급별 주간 보고서 HTML 생성 중...")

    valid_students = [s for s in students
                      if str(s.get('학번', '')).strip().startswith('2')
                      and len(str(s.get('학번', '')).strip()) >= 5]

    # 야자실 배정 로직 (각 요일별)
    def get_assigned_rooms_for_day(day_name):
        col1 = f"{day_name}1"
        col2 = f"{day_name}2"
        override_col = f"{day_name}_배정"

        room_lists = {'2-3': [], '2-4': [], '2-5': [], '2-6': []}
        unassigned = []

        for s in valid_students:
            s_id = str(s.get('학번', '')).strip()
            manual = s.get(override_col, '').strip()
            has_p1 = s.get(col1, '').strip() != ''
            has_p2 = s.get(col2, '').strip() != ''

            if manual in room_lists:
                room_lists[manual].append(s_id)
            elif has_p1 or has_p2:
                unassigned.append(s)

        both = [s for s in unassigned if s.get(col1, '').strip() != '' and s.get(col2, '').strip() != '']
        p1_only = [s for s in unassigned if s.get(col1, '').strip() != '' and s.get(col2, '').strip() == '']
        p2_only = [s for s in unassigned if s.get(col1, '').strip() == '' and s.get(col2, '').strip() != '']

        both.sort(key=lambda x: int(x.get('학번', 0)))
        p1_only.sort(key=lambda x: int(x.get('학번', 0)))
        p2_only.sort(key=lambda x: int(x.get('학번', 0)))

        for s in p1_only:
            room_lists['2-5'].append(str(s['학번']).strip())
        for s in p2_only:
            room_lists['2-6'].append(str(s['학번']).strip())
        half = (len(both) + 1) // 2
        for s in both[:half]:
            room_lists['2-3'].append(str(s['학번']).strip())
        for s in both[half:]:
            room_lists['2-4'].append(str(s['학번']).strip())

        assigned = {}
        for room, ids in room_lists.items():
            for sid in ids:
                assigned[sid] = room
        return assigned

    # 각 요일별 배정 정보 미리 계산
    daily_assignments = {}
    for wd in week_days:
        daily_assignments[wd['day_name']] = get_assigned_rooms_for_day(wd['day_name'])

    # 학급별 그룹화
    classes = {f"20{i}": [] for i in range(1, 10)}
    for s in valid_students:
        s_id = str(s.get('학번', '')).strip()
        ck = s_id[:3]
        if ck in classes:
            classes[ck].append(s)

    # ────────────────────────────────────────
    # HTML 렌더링
    # ────────────────────────────────────────
    monday_str = target_monday.strftime("%Y-%m-%d")
    friday_str = target_friday.strftime("%Y-%m-%d")

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>주간 야자 출결 보고서 ({monday_str} ~ {friday_str})</title>
<link rel="stylesheet" as="style" crossorigin href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" />
<style>
  :root {{
    --primary: #4361EE;
    --success: #137333;
    --danger: #C5221F;
    --border: #DADCE0;
    --text: #202124;
    --muted: #9AA0A6;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Pretendard', sans-serif;
    background: #525659;
    padding: 20px;
    color: var(--text);
  }}
  .page {{
    background: white;
    max-width: 900px;
    margin: 0 auto 30px;
    padding: 32px 36px;
    border-radius: 8px;
    box-shadow: 0 4px 16px rgba(0,0,0,.2);
  }}
  @media print {{
    body {{ background: white; padding: 0; }}
    .page {{
      margin: 0; padding: 12px 16px;
      box-shadow: none; border-radius: 0;
      page-break-after: always;
    }}
    .page:last-child {{ page-break-after: avoid; }}
  }}

  /* 헤더 */
  .hdr {{ text-align: center; border-bottom: 2px solid var(--primary); padding-bottom: 10px; margin-bottom: 14px; }}
  .hdr h1 {{ font-size: 1.35rem; color: var(--primary); font-weight: 800; margin-bottom: 4px; }}
  .hdr .sub {{ font-size: .88rem; color: #5F6368; font-weight: 600; }}

  /* 요약 카드 */
  .summary {{ display: flex; gap: 8px; margin-bottom: 14px; }}
  .summary .card {{
    flex: 1; background: #F8F9FA; border: 1px solid var(--border);
    border-radius: 6px; padding: 7px 6px; text-align: center;
  }}
  .summary .card .t {{ font-size: .7rem; color: #5F6368; font-weight: 600; }}
  .summary .card .v {{ font-size: 1.1rem; font-weight: 800; }}
  .v-blue {{ color: var(--primary); }}
  .v-green {{ color: var(--success); }}
  .v-red {{ color: var(--danger); }}

  /* 테이블 */
  table {{ width: 100%; border-collapse: collapse; font-size: .72rem; }}
  thead th {{
    background: #F1F3F4; font-weight: 700; color: #3C4043;
    border-top: 1px solid var(--border); border-bottom: 2px solid var(--border);
    padding: 5px 2px; text-align: center; white-space: nowrap;
  }}
  thead th.day-group {{ border-bottom: 1px solid var(--border); font-size: .75rem; }}
  tbody td {{
    border-bottom: 1px solid #ECECEC; padding: 4px 2px; text-align: center;
    vertical-align: middle;
  }}
  tbody tr:hover {{ background: #F8F9FA; }}
  .inactive td {{ color: #C0C4C8; }}
  .has-absent {{ background: #FFF5F5; }}

  /* 기호 */
  .s-ok {{ color: var(--success); font-weight: 800; font-size: .85rem; }}
  .s-no {{ color: var(--danger); font-weight: 800; font-size: .85rem; }}
  .s-na {{ color: #D0D0D0; }}
  .s-uc {{ color: #E09200; font-size: .7rem; }}

  .name-col {{ text-align: left !important; padding-left: 6px; font-weight: 600; white-space: nowrap; }}
  .rate-col {{ font-weight: 700; }}
  .rate-perfect {{ color: var(--success); }}
  .rate-warn {{ color: #E09200; }}
  .rate-bad {{ color: var(--danger); }}

  /* 범례 */
  .legend {{
    display: flex; gap: 14px; justify-content: center;
    margin-bottom: 10px; font-size: .72rem; color: #5F6368;
  }}
  .legend span {{ display: flex; align-items: center; gap: 3px; }}

  /* 서명 */
  .sigs {{ display: flex; justify-content: flex-end; margin-top: 24px; gap: 16px; }}
  .sig-box {{
    border: 1px solid var(--border); padding: 6px 18px;
    border-radius: 4px; text-align: center; font-size: .78rem;
  }}
  .sig-box .sig-t {{ font-weight: bold; color: #5F6368; margin-bottom: 20px; }}
  .sig-box .sig-l {{ border-bottom: 1px dashed #DADCE0; width: 70px; margin: 0 auto; }}
</style>
</head>
<body>
"""

    for class_key in sorted(classes.keys()):
        class_num = int(class_key[2:])
        class_students = sorted(classes[class_key], key=lambda x: int(x.get('학번', 0)))

        total_students = len(class_students)
        total_scheduled = 0
        total_attended = 0
        total_absent = 0
        yaja_student_count = 0

        rows_html = ""
        for s in class_students:
            s_id = str(s.get('학번', '')).strip()
            name = s.get('이름', '').strip()
            num = s_id[-2:]

            cells = ""
            student_scheduled = 0
            student_attended = 0
            student_absent = 0
            has_any_yaja = False
            has_any_absent = False

            for wd in week_days:
                dn = wd['day_name']
                assigned = daily_assignments[dn]
                is_assigned = s_id in assigned

                for pn in ['1', '2']:
                    col_key = f"{dn}{pn}"
                    has_sched = s.get(col_key, '').strip() != ''

                    if is_assigned and has_sched:
                        has_any_yaja = True
                        student_scheduled += 1
                        att_key = f"{dn}{pn}"
                        att_status = attendance_weekly.get(s_id, {}).get(att_key)

                        if att_status == '출석':
                            cells += '<td><span class="s-ok">●</span></td>'
                            student_attended += 1
                        elif att_status == '결석':
                            cells += '<td><span class="s-no">✕</span></td>'
                            student_absent += 1
                            has_any_absent = True
                        else:
                            cells += '<td><span class="s-uc">?</span></td>'
                    else:
                        cells += '<td><span class="s-na">-</span></td>'

            # 출석률 계산
            if student_scheduled > 0:
                rate = student_attended / student_scheduled * 100
                yaja_student_count += 1
                total_scheduled += student_scheduled
                total_attended += student_attended
                total_absent += student_absent

                if rate >= 100:
                    rate_class = "rate-perfect"
                elif rate >= 80:
                    rate_class = "rate-warn"
                else:
                    rate_class = "rate-bad"
                rate_str = f'<span class="{rate_class}">{rate:.0f}%</span>'
            else:
                rate_str = '<span class="s-na">-</span>'

            row_class = ""
            if not has_any_yaja:
                row_class = "inactive"
            elif has_any_absent:
                row_class = "has-absent"

            rows_html += f'<tr class="{row_class}"><td>{num}</td><td class="name-col">{name}</td>{cells}<td class="rate-col">{rate_str}</td></tr>\n'

        # 전체 출석률
        overall_rate = (total_attended / total_scheduled * 100) if total_scheduled > 0 else 0

        # 요일 헤더 (2단)
        day_header_top = ""
        day_header_bottom = ""
        for wd in week_days:
            dn = wd['day_name']
            d_str = wd['date'].strftime("%m/%d")
            day_header_top += f'<th colspan="2" class="day-group">{dn} ({d_str})</th>'
            day_header_bottom += '<th>1</th><th>2</th>'

        html += f"""
<div class="page">
  <div class="hdr">
    <h1>2학년 {class_num}반 주간 야자 출결 보고서</h1>
    <div class="sub">{monday_str}(월) ~ {friday_str}(금) 야간자율학습</div>
  </div>

  <div class="summary">
    <div class="card"><div class="t">학급 총원</div><div class="v">{total_students}명</div></div>
    <div class="card"><div class="t">야자 참여</div><div class="v v-blue">{yaja_student_count}명</div></div>
    <div class="card"><div class="t">주간 출석</div><div class="v v-green">{total_attended}회</div></div>
    <div class="card"><div class="t">주간 결석</div><div class="v v-red">{total_absent}회</div></div>
    <div class="card"><div class="t">주간 출석률</div><div class="v v-blue">{overall_rate:.1f}%</div></div>
  </div>

  <div class="legend">
    <span><span class="s-ok">●</span> 출석</span>
    <span><span class="s-no">✕</span> 결석</span>
    <span><span class="s-na">-</span> 야자 없음</span>
    <span><span class="s-uc">?</span> 미체크</span>
  </div>

  <table>
    <thead>
      <tr><th rowspan="2" style="width:5%">번호</th><th rowspan="2" style="width:10%">이름</th>{day_header_top}<th rowspan="2" style="width:7%">출석률</th></tr>
      <tr>{day_header_bottom}</tr>
    </thead>
    <tbody>
{rows_html}
    </tbody>
  </table>

  <div class="sigs">
    <div class="sig-box"><div class="sig-t">감독교사 확인</div><div class="sig-l"></div></div>
    <div class="sig-box"><div class="sig-t">담임교사 확인</div><div class="sig-l"></div></div>
  </div>
</div>
"""

    html += """
</body>
</html>
"""

    report_path = os.path.join(script_dir, 'yaja_weekly_report.html')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n[OK] 주간 출결 보고서 HTML 생성 성공: {report_path}")
    print("브라우저로 화면을 열어 시각적으로 확인합니다...")

    edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if os.path.exists(edge_path):
        subprocess.Popen([edge_path, f"--app=file:///{report_path}", "--no-first-run"])
    else:
        os.startfile(report_path)

if __name__ == '__main__':
    main()
