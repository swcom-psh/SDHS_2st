import os
import re
import sys
import json
import time
import datetime
import urllib.request
import urllib.parse
import subprocess

# Windows console input with timeout using msvcrt
def input_with_timeout(prompt, timeout=3.0):
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
                # Once a key is pressed, disable timeout and get the rest of the input
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
        # Fallback for non-Windows or standard systems if msvcrt is not available
        print(prompt)
        return None

def main():
    print("=" * 60)
    print(" 2학년 야간자율학습 '원페이퍼' 출결 결과 보고서 생성기 ")
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
        
        # gasUrl input 태그 검색 (멀티라인 대응)
        match = re.search(r'id=["\']gasUrl["\'][\s\S]*?value=["\'](https://script\.google\.com/macros/s/[^"\']+/exec)["\']', html_content)
        if not match:
            match = re.search(r'value=["\'](https://script\.google\.com/macros/s/[^"\']+/exec)["\'][\s\S]*?id=["\']gasUrl["\']', html_content)
        if not match:
            # 최종 예비 수단
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
    weekday = today.weekday()
    
    # 0:월, 1:화, 2:수, 3:목, 4:금, 5:토, 6:일
    if weekday == 0:  # 월요일이면 지난주 금요일 야자
        default_date = today - datetime.timedelta(days=3)
    elif weekday == 6:  # 일요일이면 금요일 야자
        default_date = today - datetime.timedelta(days=2)
    elif weekday == 5:  # 토요일이면 금요일 야자
        default_date = today - datetime.timedelta(days=1)
    else:  # 화~금요일이면 어제 야자
        default_date = today - datetime.timedelta(days=1)
        
    default_date_str = default_date.strftime("%Y-%m-%d")
    
    print(f"\n기본 대상 날짜 (최근 야자일): {default_date_str}")
    
    target_date_str = default_date_str
    # 명령줄 인자가 제공되었는지 확인 (예: python print_yaja_report.py 2026-05-20)
    if len(sys.argv) > 1:
        date_arg = sys.argv[1].strip()
        try:
            # 날짜 형식 검증
            parsed_date = datetime.datetime.strptime(date_arg, "%Y-%m-%d").date()
            target_date_str = parsed_date.strftime("%Y-%m-%d")
            print(f"-> 선택된 날짜: {target_date_str}")
        except ValueError:
            print("[오류] 입력된 날짜 형식이 올바르지 않습니다 (YYYY-MM-DD 필요). 기본 날짜로 진행합니다.")
    else:
        print("-> 추가 명령줄 인자가 없어 기본 날짜로 진행합니다. (원하는 날짜 지정 방법: python 스크립트명 YYYY-MM-DD)")

    # 요일 구하기
    days_map = {0: '월', 1: '화', 2: '수', 3: '목', 4: '금', 5: '토', 6: '일'}
    target_date_obj = datetime.datetime.strptime(target_date_str, "%Y-%m-%d").date()
    target_day_name = days_map[target_date_obj.weekday()]
    
    if target_day_name in ('토', '일'):
        print("경고: 주말(토/일)은 야간자율학습 출결 정보가 없을 수 있습니다.")

    # 3. 학생 명단 API 호출
    print("\n[1/3] 학생 명단을 구글 시트에서 가져오는 중...")
    try:
        student_url = f"{gas_url}?action=getStudents"
        req = urllib.request.Request(student_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as res:
            students = json.loads(res.read().decode('utf-8'))
        print(f"[OK] 학생 {len(students)}명 명단 로드 성공")
    except Exception as e:
        print(f"[오류] 학생 명단을 가져오는 데 실패했습니다: {e}")
        input("엔터키를 누르면 종료됩니다...")
        sys.exit(1)

    # 4. 출결 로그 호출 및 병합 (재시도 로직 포함)
    print("\n[2/3] 야자 출결 로그를 구글 시트에서 가져오는 중...")
    attendance_data = {}
    rooms = ['2-3', '2-4', '2-5', '2-6']
    periods = ['1교시', '2교시']
    
    total_requests = len(rooms) * len(periods)
    completed_requests = 0
    failed_requests = []
    MAX_RETRIES = 3
    
    for room in rooms:
        for period in periods:
            params = {
                'date': target_date_str,
                'day': target_day_name,
                'period': period,
                'room': room
            }
            query_str = urllib.parse.urlencode(params)
            url = f"{gas_url}?{query_str}"
            
            completed_requests += 1
            label = f"{room}실 {period}"
            success = False
            
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    attempt_msg = f" (재시도 {attempt}/{MAX_RETRIES})" if attempt > 1 else ""
                    print(f" -> 출결 정보 조회 중 ({completed_requests}/{total_requests}): {label}...{attempt_msg}")
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    
                    with urllib.request.urlopen(req, timeout=15) as res:
                        res_data = json.loads(res.read().decode('utf-8'))
                        
                        if isinstance(res_data, dict) and 'error' not in res_data:
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
                    success = True
                    break  # 성공하면 재시도 루프 탈출
                except Exception as e:
                    if attempt < MAX_RETRIES:
                        print(f"    [!] 네트워크 오류 발생, {2 * attempt}초 후 재시도... ({e})")
                        time.sleep(2 * attempt)
                    else:
                        print(f"    [실패] {label} 데이터 조회 실패 (3회 시도): {e}")
                        failed_requests.append(label)
                
    if failed_requests:
        print(f"\n[경고] 다음 항목의 출결 데이터를 가져오지 못했습니다: {', '.join(failed_requests)}")
        print("       해당 교실/교시의 학생은 '미체크'로 표시됩니다.")
    print(f"[OK] 출결 로그 병합 완료 (체크된 학생: {len(attendance_data)}명)")

    # 5. 야자실 배정 로직 시뮬레이션
    print("\n[3/3] 학급별 보고서 작성 및 파일 생성 중...")
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

    # 학급별 그룹화 (201 ~ 209)
    classes = {f"20{i}": [] for i in range(1, 10)}
    for s in valid_students:
        s_id = str(s.get('학번', '')).strip()
        class_key = s_id[:3]
        if class_key in classes:
            classes[class_key].append(s)

    # HTML 템플릿 렌더링
    html_output = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>{target_date_str} 야자 출결 보고서</title>
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
            max-width: 800px;
            margin: 0 auto 30px;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.2);
            border: 1px solid var(--border);
            position: relative;
        }}
        @media print {{
            body {{
                background: white;
                padding: 0;
            }}
            .class-page {{
                margin: 0;
                padding: 0;
                box-shadow: none;
                border: none;
                page-break-after: always;
            }}
            .class-page:last-child {{
                page-break-after: avoid;
            }}
        }}
        .header {{
            text-align: center;
            margin-bottom: 25px;
            border-bottom: 2px solid var(--primary);
            padding-bottom: 12px;
        }}
        .header h1 {{
            font-size: 1.7rem;
            margin: 0 0 8px 0;
            color: var(--primary);
            font-weight: 800;
        }}
        .header .date-info {{
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
        th {{
            background-color: #F1F3F4;
            font-weight: 700;
            border-top: 1px solid var(--border);
            border-bottom: 2px solid var(--border);
            padding: 8px 5px;
            text-align: center;
            color: #3C4043;
        }}
        td {{
            border-bottom: 1px solid var(--border);
            padding: 8px 5px;
            text-align: center;
        }}
        .inactive-row {{
            color: #A0A4A8;
            background-color: #FAFAFA;
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
            max-width: 150px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .footer-signatures {{
            display: flex;
            justify-content: flex-end;
            margin-top: 40px;
            gap: 20px;
        }}
        .signature-box {{
            border: 1px solid var(--border);
            padding: 8px 20px;
            border-radius: 4px;
            text-align: center;
            font-size: 0.85rem;
            min-width: 130px;
        }}
        .signature-title {{
            font-weight: bold;
            color: #5F6368;
            margin-bottom: 25px;
        }}
        .signature-line {{
            border-bottom: 1px dashed #DADCE0;
            width: 80px;
            margin: 0 auto;
        }}
    </style>
</head>
<body>
"""

    for class_key in sorted(classes.keys()):
        class_num = int(class_key[2:])
        class_students = classes[class_key]
        class_students.sort(key=lambda x: int(x.get('학번', 0)))
        
        total_students = len(class_students)
        scheduled_count = 0
        present_count = 0
        absent_count = 0
        unchecked_count = 0
        
        table_rows_html = ""
        
        for s in class_students:
            s_id = str(s.get('학번', '')).strip()
            name = s.get('이름', '').strip()
            num = s_id[-2:] # 마지막 2자리 번호
            
            # 야자 배정 정보 확인
            room_assigned = assigned_rooms.get(s_id, "")
            is_scheduled = (room_assigned != "")
            
            p1_status_badge = '<span class="badge-none">-</span>'
            p2_status_badge = '<span class="badge-none">-</span>'
            p1_remark = ""
            p2_remark = ""
            row_class = "inactive-row"
            
            if is_scheduled:
                scheduled_count += 1
                row_class = ""
                
                # 교시별 스케줄 여부
                has_p1_sched = s.get(col1, '').strip() != ''
                has_p2_sched = s.get(col2, '').strip() != ''
                
                # 1교시 출결
                if has_p1_sched:
                    if s_id in attendance_data and attendance_data[s_id]['p1_status'] is not None:
                        status = attendance_data[s_id]['p1_status']
                        p1_remark = attendance_data[s_id]['p1_remark']
                        if status == '출석':
                            p1_status_badge = '<span class="badge badge-present">출석</span>'
                            present_count += 1
                        else:
                            p1_status_badge = '<span class="badge badge-absent">결석</span>'
                            absent_count += 1
                    else:
                        p1_status_badge = '<span class="badge badge-unchecked">미체크</span>'
                        unchecked_count += 1
                else:
                    p1_status_badge = '<span class="badge-none">야자 없음</span>'
                    
                # 2교시 출결
                if has_p2_sched:
                    if s_id in attendance_data and attendance_data[s_id]['p2_status'] is not None:
                        status = attendance_data[s_id]['p2_status']
                        p2_remark = attendance_data[s_id]['p2_remark']
                        if status == '출석':
                            p2_status_badge = '<span class="badge badge-present">출석</span>'
                        else:
                            p2_status_badge = '<span class="badge badge-absent">결석</span>'
                    else:
                        p2_status_badge = '<span class="badge badge-unchecked">미체크</span>'
                else:
                    p2_status_badge = '<span class="badge-none">야자 없음</span>'
            
            # 비고 병합 표시
            remarks = []
            if p1_remark:
                remarks.append(f"1교시: {p1_remark}")
            if p2_remark:
                remarks.append(f"2교시: {p2_remark}")
            remark_text = ", ".join(remarks) if remarks else ""
            
            table_rows_html += f"""
            <tr class="{row_class}">
                <td>{num}</td>
                <td>{s_id}</td>
                <td style="font-weight: bold;">{name}</td>
                <td>{room_assigned if room_assigned else '-'}</td>
                <td>{p1_status_badge}</td>
                <td>{p2_status_badge}</td>
                <td class="remark-text" title="{remark_text}">{remark_text}</td>
            </tr>
            """
            
        html_output += f"""
    <div class="class-page">
        <div class="header">
            <h1>2학년 {class_num}반 야자 출결 결과 보고서</h1>
            <div class="date-info">{target_date_str} ({target_day_name}요일) 야간자율학습</div>
        </div>
        
        <div class="summary-container">
            <div class="summary-card">
                <div class="title">학급 총원</div>
                <div class="value">{total_students}명</div>
            </div>
            <div class="summary-card active-card">
                <div class="title">야자 대상</div>
                <div class="value">{scheduled_count}명</div>
            </div>
            <div class="summary-card present-card">
                <div class="title">출석 (1교시 기준)</div>
                <div class="value">{present_count}명</div>
            </div>
            <div class="summary-card absent-card">
                <div class="title">결석 (1교시 기준)</div>
                <div class="value">{absent_count}명</div>
            </div>
            <div class="summary-card">
                <div class="title">출결 미체크</div>
                <div class="value" style="color: #B06000;">{unchecked_count}명</div>
            </div>
        </div>
        
        <table>
            <thead>
                <tr>
                    <th style="width: 8%;">번호</th>
                    <th style="width: 15%;">학번</th>
                    <th style="width: 15%;">이름</th>
                    <th style="width: 12%;">야자실</th>
                    <th style="width: 15%;">1교시</th>
                    <th style="width: 15%;">2교시</th>
                    <th style="width: 20%;">비고 (결석 사유)</th>
                </tr>
            </thead>
            <tbody>
                {table_rows_html}
            </tbody>
        </table>
        
        <div class="footer-signatures">
            <div class="signature-box">
                <div class="signature-title">감독교사 확인</div>
                <div class="signature-line"></div>
            </div>
            <div class="signature-box">
                <div class="signature-title">담임교사 확인</div>
                <div class="signature-line"></div>
            </div>
        </div>
    </div>
    """

    html_output += """
</body>
</html>
"""

    report_html_path = os.path.join(script_dir, 'yaja_report.html')
    with open(report_html_path, 'w', encoding='utf-8') as f:
        f.write(html_output)
        
    print(f"\n[OK] 원페이퍼 출결 보고서 HTML 생성 성공: {report_html_path}")
    print("브라우저로 화면을 열어 시각적으로 확인합니다...")
    
    # Edge 브라우저를 앱 모드로 열어서 사용자에게 보여줌
    edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if os.path.exists(edge_path):
        subprocess.Popen([edge_path, f"--app=file:///{report_html_path}", "--no-first-run"])
    else:
        # Edge 경로가 다른 경우 기본 브라우저로 엶
        os.startfile(report_html_path)

if __name__ == '__main__':
    main()
