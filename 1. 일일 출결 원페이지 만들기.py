import os
import re
import sys
import json
import time
import datetime
import urllib.request
import urllib.parse
import subprocess

def get_korean_holidays(year):
    """해당 연도의 한국 법정 공휴일 목록을 반환 (고정 공휴일 + 음력 기반 공휴일)"""
    holidays = set()
    
    # 고정 공휴일
    fixed = [
        (1, 1),   # 신정
        (3, 1),   # 삼일절
        (5, 5),   # 어린이날
        (6, 6),   # 현충일
        (8, 15),  # 광복절
        (10, 3),  # 개천절
        (10, 9),  # 한글날
        (12, 25), # 성탄절
    ]
    for m, d in fixed:
        holidays.add(f"{year}-{m:02d}-{d:02d}")
    
    # 음력 기반 공휴일 (설날·추석·부처님오신날)은 미리 계산된 테이블 사용
    # 각 연도별 (설날 당일, 추석 당일, 부처님오신날) 양력 날짜
    lunar_dates = {
        2025: {"seol": "2025-01-29", "chuseok": "2025-10-06", "buddha": "2025-05-05"},
        2026: {"seol": "2026-02-17", "chuseok": "2026-09-25", "buddha": "2026-05-24"},
        2027: {"seol": "2027-02-06", "chuseok": "2027-09-15", "buddha": "2027-05-13"},
        2028: {"seol": "2028-01-26", "chuseok": "2028-10-03", "buddha": "2028-05-02"},
        2029: {"seol": "2029-02-13", "chuseok": "2029-09-22", "buddha": "2029-05-20"},
        2030: {"seol": "2030-02-03", "chuseok": "2030-09-12", "buddha": "2030-05-09"},
    }
    
    if year in lunar_dates:
        ld = lunar_dates[year]
        # 설날 연휴 (전날, 당일, 다음날)
        seol = datetime.datetime.strptime(ld["seol"], "%Y-%m-%d").date()
        for delta in [-1, 0, 1]:
            holidays.add((seol + datetime.timedelta(days=delta)).strftime("%Y-%m-%d"))
        # 추석 연휴 (전날, 당일, 다음날)
        chuseok = datetime.datetime.strptime(ld["chuseok"], "%Y-%m-%d").date()
        for delta in [-1, 0, 1]:
            holidays.add((chuseok + datetime.timedelta(days=delta)).strftime("%Y-%m-%d"))
        # 부처님오신날
        holidays.add(ld["buddha"])
    
    # 대체공휴일: 공휴일이 일요일이면 다음 월요일 추가
    extra = set()
    for h_str in holidays:
        h_date = datetime.datetime.strptime(h_str, "%Y-%m-%d").date()
        if h_date.weekday() == 6:  # 일요일
            extra.add((h_date + datetime.timedelta(days=1)).strftime("%Y-%m-%d"))
    holidays.update(extra)
    
    return holidays

def sort_room_names(rooms):
    """교실명을 2-3, 2-4 … 순으로 정렬. 숫자형이 아닌 이름(도서관 등)은 뒤에 가나다순."""
    def key(name):
        m = re.match(r'^(\d+)\s*-\s*(\d+)$', str(name).strip())
        if m:
            return (0, int(m.group(1)), int(m.group(2)), '')
        return (1, 0, 0, str(name))
    return sorted(set(r for r in rooms if str(r).strip()), key=key)


def parse_date_arg(text):
    """날짜 입력을 너그럽게 읽는다.

    20260831 / 2026-08-31 / 2026.8.31 / 2026 08 31 모두 같은 날로 본다.
    읽을 수 없으면 ValueError 를 낸다.
    """
    raw = str(text).strip()

    # ① 구분자를 뺀 숫자 8자리 (20260831)
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if len(digits) == 8:
        try:
            return datetime.datetime.strptime(digits, "%Y%m%d").date()
        except ValueError:
            raise ValueError("없는 날짜입니다: %s" % raw)

    # ② 한 자리 월/일을 쓴 경우 (2026-8-31, 2026.8.5 …)
    sep = raw.replace('.', '-').replace('/', '-').replace(' ', '-')
    parts = [p for p in sep.split('-') if p]
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        y, m, d = (int(p) for p in parts)
        try:
            return datetime.date(y, m, d)
        except ValueError:
            raise ValueError("없는 날짜입니다: %s" % raw)

    raise ValueError("날짜를 알아볼 수 없습니다: %s (예: 20260831)" % raw)


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
            # 최종 예비 수단: <input 태그 내부의 GAS URL만 매칭
            match = re.search(r'<input[^>]*value=["\'](https://script\.google\.com/macros/s/[a-zA-Z0-9_-]+/exec)["\']', html_content)
            
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

    # 2. 날짜 자동 감지 및 입력 (주말 및 공휴일 제외)
    today = datetime.date.today()
    
    # 연도별 공휴일 자동 생성
    holidays = get_korean_holidays(today.year)
    
    # 오늘 이전의 날들 중 평일(월~금)이면서 공휴일이 아닌 가장 최근의 날 탐색
    default_date = today - datetime.timedelta(days=1)
    while True:
        is_weekend = default_date.weekday() >= 5 # 5: 토요일, 6: 일요일
        default_date_str = default_date.strftime("%Y-%m-%d")
        is_holiday = default_date_str in holidays
        
        if not is_weekend and not is_holiday:
            break
        default_date -= datetime.timedelta(days=1)
    
    print(f"\n기본 대상 날짜 (최근 야자일): {default_date_str}")
    
    target_date_str = default_date_str
    # 명령줄 인자가 제공되었는지 확인 (예: python print_yaja_report.py 2026-05-20)
    if len(sys.argv) > 1:
        date_arg = sys.argv[1].strip()
        try:
            # 20260831 / 2026-08-31 둘 다 받는다
            parsed_date = parse_date_arg(date_arg)
            target_date_str = parsed_date.strftime("%Y-%m-%d")
            print(f"-> 선택된 날짜: {target_date_str}")
        except ValueError:
            print("[오류] 입력된 날짜 형식이 올바르지 않습니다 (20260831 또는 2026-08-31). 기본 날짜로 진행합니다.")
    else:
        print("-> 추가 명령줄 인자가 없어 기본 날짜로 진행합니다. (원하는 날짜 지정 방법: python 스크립트명 20260831)")

    # 요일 구하기
    days_map = {0: '월', 1: '화', 2: '수', 3: '목', 4: '금', 5: '토', 6: '일'}
    target_date_obj = datetime.datetime.strptime(target_date_str, "%Y-%m-%d").date()
    target_day_name = days_map[target_date_obj.weekday()]
    
    if target_day_name in ('토', '일'):
        print("경고: 주말(토/일)은 야간자율학습 출결 정보가 없을 수 있습니다.")

    # 3. 학생 명단 API 호출
    print("\n[1/3] 학생 명단을 구글 시트에서 가져오는 중...")
    try:
        student_url = f"{gas_url}?action=getSecondStudents"
        req = urllib.request.Request(student_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as res:
            students = json.loads(res.read().decode('utf-8'))
        if not isinstance(students, list):
            raise Exception(f"API 응답이 학생 목록(list)이 아닙니다. 응답 타입: {type(students).__name__}")
        print(f"[OK] 학생 {len(students)}명 명단 로드 성공")
    except Exception as e:
        print(f"[오류] 학생 명단을 가져오는 데 실패했습니다: {e}")
        input("엔터키를 누르면 종료됩니다...")
        sys.exit(1)

    # 3-1. 교실 배정 정보 계산
    #  [2학기 정책] 자동 배정을 하지 않는다. 시트의 [요일_배정] 칸에 적힌 교실만 따르고,
    #  교실 목록도 그 칸에 실제로 적힌 값에서 만든다. (2-3, 2-7, 도서관 … 무엇이든 가능)
    col1 = f"{target_day_name}1"
    col2 = f"{target_day_name}2"
    override_col = f"{target_day_name}_배정"

    # 2학년 학생만 필터링
    valid_students = [s for s in students if str(s.get('학번', '')).strip().startswith('2') and len(str(s.get('학번', '')).strip()) >= 5]

    assigned_rooms = {}      # 학번 -> 교실
    unassigned_ids = set()   # 신청은 했지만 아직 배정 안 된 학번
    for s in valid_students:
        s_id = str(s.get('학번', '')).strip()
        has_p1 = s.get(col1, '').strip() != ''
        has_p2 = s.get(col2, '').strip() != ''
        if not has_p1 and not has_p2:
            continue
        manual_room = s.get(override_col, '').strip()
        if manual_room:
            assigned_rooms[s_id] = manual_room
        else:
            unassigned_ids.add(s_id)

    rooms = sort_room_names(set(assigned_rooms.values()))
    if rooms:
        print(f"[OK] {target_day_name}요일 배정 교실: {', '.join(rooms)} (배정 {len(assigned_rooms)}명, 미배정 {len(unassigned_ids)}명)")
    else:
        print(f"[경고] {target_day_name}요일에 교실이 배정된 학생이 없습니다. 시트의 [{override_col}] 칸을 확인해주세요.")
        if unassigned_ids:
            print(f"       ({target_day_name}요일 신청자 {len(unassigned_ids)}명이 모두 미배정 상태입니다.)")

    # 4. 출결 로그 호출 및 병합 (재시도 로직 포함)
    print("\n[2/3] 야자 출결 로그를 구글 시트에서 가져오는 중...")
    attendance_data = {}
    periods = ['1교시', '2교시']
    
    total_requests = len(rooms) * len(periods)
    completed_requests = 0
    failed_requests = []
    MAX_RETRIES = 3
    
    for room in rooms:
        for period in periods:
            params = {
                'sheetTarget': 'second',   # -> "2학기 야자 출석" 시트
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

    # 5. 보고서 작성
    print("\n[3/3] 학급별 보고서 작성 및 파일 생성 중...")

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
                page-break-after: always;
                display: block;
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
        unassigned_count = 0
        
        table_rows_html = ""
        
        for s in class_students:
            s_id = str(s.get('학번', '')).strip()
            name = s.get('이름', '').strip()
            num = s_id[-2:] # 마지막 2자리 번호
            
            # 야자 배정 정보 확인
            room_assigned = assigned_rooms.get(s_id, "")
            is_unassigned = (s_id in unassigned_ids)   # 신청했지만 교실 미배정
            is_scheduled = (room_assigned != "")
            if is_unassigned:
                unassigned_count += 1
            
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
                <td>{room_assigned if room_assigned else ('<span style="color:#B06000; font-weight:700;">미배정</span>' if is_unassigned else '-')}</td>
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
            <div class="summary-card">
                <div class="title">교실 미배정</div>
                <div class="value" style="color: #B06000;">{unassigned_count}명</div>
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

    report_html_path = os.path.join(script_dir, '1. 일일 출결 원페이지 만들기.html')
    with open(report_html_path, 'w', encoding='utf-8') as f:
        f.write(html_output)
        
    print(f"\n[OK] 원페이퍼 출결 보고서 HTML 생성 성공: {report_html_path}")
    print("브라우저로 화면을 열어 시각적으로 확인합니다...")
    
    # 공백 및 한글, 백슬래시 경로를 브라우저가 인식 가능한 URL로 인코딩
    report_html_url = "file:" + urllib.request.pathname2url(report_html_path)
    
    # 크롬 브라우저를 최우선으로 앱 모드로 열고, 없으면 엣지, 둘 다 없으면 기본 브라우저로 엶
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(os.environ.get('LOCALAPPDATA', ''), r"Google\Chrome\Application\chrome.exe") if os.environ.get('LOCALAPPDATA') else ""
    ]
    
    browser_opened = False
    for chrome_path in chrome_paths:
        if chrome_path and os.path.exists(chrome_path):
            subprocess.Popen([chrome_path, f"--app={report_html_url}"])
            browser_opened = True
            break
            
    if not browser_opened:
        edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        if os.path.exists(edge_path):
            subprocess.Popen([edge_path, f"--app={report_html_url}", "--no-first-run"])
            browser_opened = True
            
    if not browser_opened:
        os.startfile(report_html_path)

if __name__ == '__main__':
    main()
