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

def fetch_with_retry(url, max_retries=3):
    """Fetch JSON from URL with retry on failure."""
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as res:
                return json.loads(res.read().decode('utf-8'))
        except Exception:
            if attempt < max_retries:
                time.sleep(2 * attempt)
    return None

def main():
    print("=" * 60)
    print(" 2학년 야간자율학습 '결석자 현황' 보고서 생성기 ")
    print("=" * 60)

    # 1. index.html에서 GAS URL 추출
    script_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(script_dir, 'index.html')
    
    if not os.path.exists(html_path):
        print(f"[오류] index.html 파일을 찾을 수 없습니다. (경로: {html_path})")
        input("엔터키를 누르면 종료됩니다...")
        sys.exit(1)
        
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        match = re.search(r'id=["\']gasUrl["\'][\s\S]*?value=["\'](https://script\.google\.com/macros/s/[^"\']+/exec)["\']', html_content)
        if not match:
            match = re.search(r'value=["\'](https://script\.google\.com/macros/s/[^"\']+/exec)["\'][\s\S]*?id=["\']gasUrl["\']', html_content)
        if not match:
            match = re.search(r'(https://script\.google\.com/macros/s/[a-zA-Z0-9_-]+/exec)', html_content)
            
        if not match:
            print("[오류] index.html에서 구글 앱스 스크립트(GAS) URL을 추출하지 못했습니다.")
            input("엔터키를 누르면 종료됩니다...")
            sys.exit(1)
            
        gas_url = match.group(1)
        print(f"[OK] GAS 웹앱 URL 추출 성공: {gas_url}")
    except Exception as e:
        print(f"[오류] index.html을 읽는 중 에러가 발생했습니다: {e}")
        input("엔터키를 누르면 종료됩니다...")
        sys.exit(1)

    # 2. 날짜 자동 감지 및 입력
    today = datetime.date.today()
    default_date = today - datetime.timedelta(days=1)
    default_date_str = default_date.strftime("%Y-%m-%d")
    
    print(f"\n기본 대상 날짜 (최근 야자일): {default_date_str}")
    
    target_date_str = default_date_str
    if len(sys.argv) > 1:
        date_arg = sys.argv[1].strip()
        try:
            parsed_date = datetime.datetime.strptime(date_arg, "%Y-%m-%d").date()
            target_date_str = parsed_date.strftime("%Y-%m-%d")
            print(f"-> 선택된 날짜: {target_date_str}")
        except ValueError:
            print("[오류] 입력된 날짜 형식이 올바르지 않습니다 (YYYY-MM-DD 필요). 기본 날짜로 진행합니다.")
    else:
        print("-> 추가 명령줄 인자가 없어 기본 날짜로 진행합니다. (원하는 날짜 지정 방법: python 스크립트명 YYYY-MM-DD)")

    days_map = {0: '월', 1: '화', 2: '수', 3: '목', 4: '금', 5: '토', 6: '일'}
    target_date_obj = datetime.datetime.strptime(target_date_str, "%Y-%m-%d").date()
    target_day_name = days_map[target_date_obj.weekday()]
    
    if target_day_name in ('토', '일'):
        print("경고: 주말(토/일)은 야간자율학습 출결 정보가 없을 수 있습니다.")

    # 3. 학생 명단 API 호출
    print("\n[1/3] 학생 명단을 구글 시트에서 가져오는 중...")
    try:
        student_url = f"{gas_url}?action=getStudents"
        students = fetch_with_retry(student_url)
        if not students:
            raise Exception("학생 명단을 읽어오지 못했습니다.")
        print(f"[OK] 학생 {len(students)}명 명단 로드 성공")
    except Exception as e:
        print(f"[오류] 학생 명단을 가져오는 데 실패했습니다: {e}")
        input("엔터키를 누르면 종료됩니다...")
        sys.exit(1)

    # 4. 출결 로그 병렬 호출 및 병합
    print("\n[2/3] 야자 출결 로그를 구글 시트에서 가져오는 중...")
    attendance_data = {}
    rooms = ['2-3', '2-4', '2-5', '2-6']
    periods = ['1교시', '2교시']
    
    fetch_tasks = []
    for room in rooms:
        for period in periods:
            params = {
                'date': target_date_str,
                'day': target_day_name,
                'period': period,
                'room': room
            }
            fetch_tasks.append((room, period, params))
            
    total_requests = len(fetch_tasks)
    completed_requests = 0
    failed_requests = []
    
    def do_fetch(task):
        room, period, params = task
        query_str = urllib.parse.urlencode(params)
        url = f"{gas_url}?{query_str}"
        data = fetch_with_retry(url, max_retries=3)
        return (room, period, data)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(do_fetch, t) for t in fetch_tasks]
        for future in as_completed(futures):
            completed_requests += 1
            try:
                room, period, res_data = future.result()
                label = f"{room}실 {period}"
                
                if res_data and isinstance(res_data, dict) and 'error' not in res_data:
                    for s_id, att in res_data.items():
                        s_id = str(s_id).strip()
                        if not s_id or s_id in ("error", "supervisor"):
                            continue
                            
                        if s_id not in attendance_data:
                            attendance_data[s_id] = {
                                'p1_status': None, 'p1_remark': '', 'p1_supervisor': '',
                                'p2_status': None, 'p2_remark': '', 'p2_supervisor': ''
                            }
                            
                        status_val = att.get('status')
                        status_str = '출석' if (status_val is True or str(status_val).lower() == 'true' or status_val == '출석') else '결석'
                        remark = att.get('remark', '').strip()
                        supervisor = att.get('supervisor', '').strip()
                        
                        if period == '1교시':
                            attendance_data[s_id]['p1_status'] = status_str
                            attendance_data[s_id]['p1_remark'] = remark
                            attendance_data[s_id]['p1_supervisor'] = supervisor
                        else:
                            attendance_data[s_id]['p2_status'] = status_str
                            attendance_data[s_id]['p2_remark'] = remark
                            attendance_data[s_id]['p2_supervisor'] = supervisor
                else:
                    failed_requests.append(label)
            except Exception as e:
                failed_requests.append("Unknown Task Error")
                
    if failed_requests:
        print(f"\n[경고] 다음 항목의 출결 데이터를 가져오지 못했습니다: {', '.join(failed_requests)}")
        print("       해당 교실/교시의 학생은 '미체크'로 표시됩니다.")
    print(f"[OK] 출결 로그 병합 완료 (체크된 학생: {len(attendance_data)}명)")

    # 5. 야자실 배정 로직 시뮬레이션
    print("\n[3/3] 야자실 배정 결과 시뮬레이션 및 결석자 필터링 중...")
    col1 = f"{target_day_name}1"
    col2 = f"{target_day_name}2"
    override_col = f"{target_day_name}_배정"
    
    room_lists = { '2-3': [], '2-4': [], '2-5': [], '2-6': [] }
    unassigned_students = []
    
    # 2학년 학생만 필터링
    valid_students = [s for s in students if str(s.get('학번', '')).strip().startswith('2') and len(str(s.get('학번', '')).strip()) >= 5]
    
    for s in valid_students:
        s_id = str(s.get('학번', '')).strip()
        manual_room = s.get(override_col, '').strip()
        has_p1 = s.get(col1, '').strip() != ''
        has_p2 = s.get(col2, '').strip() != ''
        
        if manual_room in room_lists:
            room_lists[manual_room].append(s_id)
        else:
            if has_p1 or has_p2:
                unassigned_students.append(s)
                
    # 미배정 학생 자동 분배
    both_p = [s for s in unassigned_students if s.get(col1, '').strip() != '' and s.get(col2, '').strip() != '']
    p1_only = [s for s in unassigned_students if s.get(col1, '').strip() != '' and s.get(col2, '').strip() == '']
    p2_only = [s for s in unassigned_students if s.get(col1, '').strip() == '' and s.get(col2, '').strip() != '']
    
    both_p.sort(key=lambda x: int(x.get('학번', 0)))
    p1_only.sort(key=lambda x: int(x.get('학번', 0)))
    p2_only.sort(key=lambda x: int(x.get('학번', 0)))
    
    for s in p1_only:
        room_lists['2-5'].append(str(s['학번']).strip())
    for s in p2_only:
        room_lists['2-6'].append(str(s['학번']).strip())
        
    half = (len(both_p) + 1) // 2
    for s in both_p[:half]:
        room_lists['2-3'].append(str(s['학번']).strip())
    for s in both_p[half:]:
        room_lists['2-4'].append(str(s['학번']).strip())
        
    # 배정된 방 매핑
    assigned_rooms = {}
    for room, s_ids in room_lists.items():
        for s_id in s_ids:
            assigned_rooms[s_id] = room

    # 6. 결석자 필터링 및 학번 순 정렬 (2-1반~2-9반 순서대로)
    absentees_list = []
    scheduled_total_count = len(assigned_rooms)
    
    for s in valid_students:
        s_id = str(s.get('학번', '')).strip()
        name = s.get('이름', '').strip()
        
        # 야자 배정된 학생인지 확인
        room_assigned = assigned_rooms.get(s_id, "")
        if not room_assigned:
            continue
            
        has_p1_sched = s.get(col1, '').strip() != ''
        has_p2_sched = s.get(col2, '').strip() != ''
        
        # 1교시 또는 2교시 출결 상태에서 '결석'인지 판정
        is_p1_absent = has_p1_sched and s_id in attendance_data and attendance_data[s_id]['p1_status'] == '결석'
        is_p2_absent = has_p2_sched and s_id in attendance_data and attendance_data[s_id]['p2_status'] == '결석'
        
        if is_p1_absent or is_p2_absent:
            # 출결 상태 정보 정리
            p1_badge = '<span class="badge-none">-</span>'
            p1_remark = ""
            if has_p1_sched:
                if s_id in attendance_data:
                    p1_status = attendance_data[s_id]['p1_status']
                    p1_remark = attendance_data[s_id]['p1_remark']
                    if p1_status == '결석':
                        p1_badge = '<span class="badge badge-absent">결석</span>'
                    elif p1_status == '출석':
                        p1_badge = '<span class="badge badge-present">출석</span>'
                    else:
                        p1_badge = '<span class="badge badge-unchecked">미체크</span>'
                else:
                    p1_badge = '<span class="badge badge-unchecked">미체크</span>'
            else:
                p1_badge = '<span class="badge-none">야자 없음</span>'
                
            p2_badge = '<span class="badge-none">-</span>'
            p2_remark = ""
            if has_p2_sched:
                if s_id in attendance_data:
                    p2_status = attendance_data[s_id]['p2_status']
                    p2_remark = attendance_data[s_id]['p2_remark']
                    if p2_status == '결석':
                        p2_badge = '<span class="badge badge-absent">결석</span>'
                    elif p2_status == '출석':
                        p2_badge = '<span class="badge badge-present">출석</span>'
                    else:
                        p2_badge = '<span class="badge badge-unchecked">미체크</span>'
                else:
                    p2_badge = '<span class="badge badge-unchecked">미체크</span>'
            else:
                p2_badge = '<span class="badge-none">야자 없음</span>'
                
            # 비고 문구 생성
            remarks = []
            if p1_remark and is_p1_absent:
                remarks.append(f"1교시: {p1_remark}")
            if p2_remark and is_p2_absent:
                remarks.append(f"2교시: {p2_remark}")
            remark_text = ", ".join(remarks) if remarks else ""
            
            absentees_list.append({
                'id': s_id,
                'name': name,
                'room': room_assigned,
                'p1_badge': p1_badge,
                'p2_badge': p2_badge,
                'remark': remark_text
            })
            
    # 학번 순서대로 정렬 (201xx -> 209xx 오름차순)
    absentees_list.sort(key=lambda x: int(x['id']))
    
    absent_total_count = len(absentees_list)
    present_total_count = scheduled_total_count - absent_total_count
    absent_rate = (absent_total_count / scheduled_total_count * 100) if scheduled_total_count > 0 else 0

    # 7. HTML 보고서 렌더링
    table_rows_html = ""
    for idx, item in enumerate(absentees_list, 1):
        class_num = int(item['id'][2:3])
        table_rows_html += f"""
        <tr>
            <td>{idx:02d}</td>
            <td>{item['id']}</td>
            <td style="font-weight: bold;">{item['name']}</td>
            <td>2학년 {class_num}반</td>
            <td>{item['room']}실</td>
            <td>{item['p1_badge']}</td>
            <td>{item['p2_badge']}</td>
            <td class="remark-text" title="{item['remark']}">{item['remark']}</td>
        </tr>
        """
        
    if not absentees_list:
        table_rows_html = """
        <tr>
            <td colspan="8" style="padding: 40px; color: #9AA0A6; font-size: 1rem;">금일 발생한 결석자가 없습니다.</td>
        </tr>
        """

    html_output = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>{target_date_str} 야자 결석자 현황 보고서</title>
    <!-- Pretendard font -->
    <link rel="stylesheet" as="style" crossorigin href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" />
    <style>
        :root {{
            --primary: #4361EE;
            --primary-light: #EBF0FF;
            --success-bg: #E6F4EA;
            --success-text: #137333;
            --danger-bg: #FCE8E6;
            --danger-text: #C5221F;
            --muted-bg: #F1F3F4;
            --muted-text: #5F6368;
            --border: #DADCE0;
            --text-main: #202124;
        }}
        * {{
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Pretendard', sans-serif;
            background-color: #525659;
            margin: 0;
            padding: 20px;
            color: var(--text-main);
        }}
        .class-page {{
            background: white;
            max-width: 850px;
            margin: 0 auto 30px;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.2);
            border: 1px solid var(--border);
            position: relative;
            min-height: 297mm; /* A4 height guideline */
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }}
        @media print {{
            @page {{
                size: A4 portrait;
                margin: 15mm 15mm 15mm 15mm;
            }}
            body {{
                background: white;
                padding: 0;
                margin: 0;
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            }}
            .class-page {{
                margin: 0;
                padding: 0;
                box-shadow: none;
                border: none;
                min-height: auto;
                page-break-after: avoid;
                display: block;
            }}
        }}
        .content-wrap {{
            width: 100%;
        }}
        .header-container {{
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            margin-bottom: 25px;
            border-bottom: 2px solid var(--primary);
            padding-bottom: 12px;
        }}
        .header-title-section {{
            text-align: left;
        }}
        .header-title-section h1 {{
            font-size: 1.7rem;
            margin: 0 0 8px 0;
            color: var(--primary);
            font-weight: 800;
        }}
        .header-title-section .date-info {{
            font-size: 1rem;
            color: #5F6368;
            font-weight: 600;
        }}
        .summary-container {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 25px;
            gap: 10px;
        }}
        .summary-card {{
            flex: 1;
            background: #F8F9FA;
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 10px;
            text-align: center;
        }}
        .summary-card .title {{
            font-size: 0.8rem;
            color: #5F6368;
            margin-bottom: 4px;
            font-weight: 600;
        }}
        .summary-card .value {{
            font-size: 1.3rem;
            font-weight: 800;
            color: var(--text-main);
        }}
        .summary-card.active-card .value {{
            color: var(--primary);
        }}
        .summary-card.present-card .value {{
            color: var(--success-text);
        }}
        .summary-card.absent-card .value {{
            color: var(--danger-text);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 25px;
            font-size: 0.85rem;
        }}
        thead {{
            display: table-header-group;
        }}
        tr {{
            page-break-inside: avoid;
        }}
        th {{
            background-color: #F1F3F4;
            font-weight: 700;
            border-top: 1px solid var(--border);
            border-bottom: 2px solid var(--border);
            padding: 10px 5px;
            text-align: center;
            color: #3C4043;
        }}
        td {{
            border-bottom: 1px solid var(--border);
            padding: 10px 5px;
            text-align: center;
        }}
        .badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.78rem;
            font-weight: 700;
        }}
        .badge-present {{
            background-color: var(--success-bg);
            color: var(--success-text);
        }}
        .badge-absent {{
            background-color: var(--danger-bg);
            color: var(--danger-text);
        }}
        .badge-none {{
            color: #9AA0A6;
            font-weight: normal;
        }}
        .badge-unchecked {{
            background-color: #FFF4E5;
            color: #B06000;
        }}
        .remark-text {{
            font-size: 0.8rem;
            text-align: left;
            padding-left: 8px;
            max-width: 180px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .signature-box {{
            border: 1px solid var(--border);
            padding: 10px 25px;
            border-radius: 4px;
            text-align: center;
            font-size: 0.85rem;
            min-width: 140px;
        }}
        .signature-title {{
            font-weight: bold;
            color: #5F6368;
            margin-bottom: 35px;
        }}
        .signature-line {{
            border-bottom: 1px dashed #DADCE0;
            width: 90px;
            margin: 0 auto;
        }}
    </style>
</head>
<body>

    <div class="class-page">
        <div class="content-wrap">
            <table>
                <thead>
                    <!-- Row 1: Header title and signature -->
                    <tr>
                        <td colspan="8" style="padding: 0; border: none !important; text-align: left;">
                            <div class="header-container" style="margin-top: 0;">
                                <div class="header-title-section">
                                    <h1>2학년 야간자율학습 결석자 현황 보고서</h1>
                                    <div class="date-info">{target_date_str} ({target_day_name}요일) 야간자율학습</div>
                                </div>
                                <div class="signature-box" style="margin-bottom: 2px;">
                                    <div class="signature-title">학년부장</div>
                                    <div class="signature-line"></div>
                                </div>
                            </div>
                        </td>
                    </tr>
                    <!-- Row 2: Summary cards -->
                    <tr>
                        <td colspan="8" style="padding: 0; border: none !important;">
                            <div class="summary-container" style="margin-top: 15px;">
                                <div class="summary-card active-card">
                                    <div class="title">야자 대상 총원</div>
                                    <div class="value">{scheduled_total_count}명</div>
                                </div>
                                <div class="summary-card present-card">
                                    <div class="title">출석 총원</div>
                                    <div class="value">{present_total_count}명</div>
                                </div>
                                <div class="summary-card absent-card">
                                    <div class="title">결석 총원</div>
                                    <div class="value">{absent_total_count}명</div>
                                </div>
                                <div class="summary-card">
                                    <div class="title">결석률</div>
                                    <div class="value" style="color: #C5221F;">{absent_rate:.1f}%</div>
                                </div>
                            </div>
                        </td>
                    </tr>
                    <!-- Row 3: Table Column Headers -->
                    <tr>
                        <th style="width: 8%;">연번</th>
                        <th style="width: 12%;">학번</th>
                        <th style="width: 12%;">이름</th>
                        <th style="width: 12%;">소속 학급</th>
                        <th style="width: 12%;">배정 자습실</th>
                        <th style="width: 14%;">1교시 출결</th>
                        <th style="width: 14%;">2교시 출결</th>
                        <th style="width: 16%;">비고 (결석 사유)</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows_html}
                </tbody>
            </table>
        </div>
        

    </div>
    
</body>
</html>
"""

    report_html_path = os.path.join(script_dir, '3. 일일 결석자 원페이지 만들기.html')
    with open(report_html_path, 'w', encoding='utf-8') as f:
        f.write(html_output)
        
    print(f"\n[OK] 결석자 현황 보고서 HTML 생성 성공: {report_html_path}")
    print("브라우저로 화면을 열어 시각적으로 확인합니다...")
    
    # 크롬 브라우저를 최우선으로 앱 모드로 열고, 없으면 엣지, 둘 다 없으면 기본 브라우저로 엶
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(os.environ.get('LOCALAPPDATA', ''), r"Google\Chrome\Application\chrome.exe") if os.environ.get('LOCALAPPDATA') else ""
    ]
    
    browser_opened = False
    for chrome_path in chrome_paths:
        if chrome_path and os.path.exists(chrome_path):
            subprocess.Popen([chrome_path, f"--app=file:///{report_html_path}"])
            browser_opened = True
            break
            
    if not browser_opened:
        edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        if os.path.exists(edge_path):
            subprocess.Popen([edge_path, f"--app=file:///{report_html_path}", "--no-first-run"])
            browser_opened = True
            
    if not browser_opened:
        os.startfile(report_html_path)

if __name__ == '__main__':
    main()
