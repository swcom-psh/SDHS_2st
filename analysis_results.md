# 🔍 SDHS_2st 프로그램 디버깅 필요 사항 리스트

전체 파일 구성: `index.html`, Python 스크립트 3개, BAT 파일 3개, GAS 코드 1개

> [!NOTE]
> 심각도 분류: 🔴 치명적(기능 장애) / 🟡 중요(데이터 정합성) / 🟢 개선 권장(유지보수)

---

## 1. [index.html](file:///c:/Users/SDHS/Desktop/Anti/SDHS_2st/index.html) — 야자 자리 배치 프로그램 (3735줄)

### 🔴 치명적

| # | 이슈 | 위치 | 설명 |
|---|------|------|------|
| 1 | **`#loadingOverlay` CSS 중복 정의** | L744~L758, L1428~L1442 | `#loadingOverlay`가 두 번 정의되어 첫 번째 정의(`display: none`)가 두 번째(`display: none` + `gap: 20px` 등)에 덮어쓰임. `border-bottom-color` vs `border-top` 불일치로 로딩 스피너 애니메이션이 의도와 다를 수 있음 |
| 2 | **`.loader` CSS 중복 정의** | L760~L768, L1444~L1451 | `@keyframes rotation` vs `@keyframes spin` — 두 개의 다른 키프레임 이름이 사용됨. 둘 중 하나만 실제 적용되어 나머지 하나는 죽은 코드 |
| 3 | **`startAppSession` 함수 시그니처 불일치** | L2409 vs L2396, L2400, L2460 | `startAppSession(name)` 으로 1개 파라미터만 받지만, 호출부에서 `startAppSession(supervisorName, false)`, `startAppSession(supervisorName, true)`, `startAppSession(nameInput, true)`로 2개 파라미터를 넘기고 있음. 두 번째 인자는 무시됨 — 의도한 동작인지 불분명 |

### 🟡 중요

| # | 이슈 | 위치 | 설명 |
|---|------|------|------|
| 4 | **미정의 CSS 변수 참조** | 곳곳 | `--table-border`, `--table-header`, `--table-row-hover` 가 `:root`에 정의되어 있지 않음. 출결 테이블이 보이지 않는 테두리로 렌더링될 수 있음 |
| 5 | **`@keyframes rotation`와 `@keyframes spin` 중복** | L771~L778, L1453~L1461 | 동일한 회전 애니메이션이 다른 이름으로 정의됨. `.loader`가 어느 것을 참조하느냐에 따라 동작이 달라질 수 있음 |
| 6 | **모바일 반응형 그리드 spacer 숨김 문제** | L1223~L1224 | `@media (max-width: 768px)`에서 `.spacer { display: none }` + `grid-template-columns: repeat(6, 1fr)`로 변경하면 6열 그리드가 되지만, 원래 데이터는 8열(spacer 포함) 구조이므로 자리 배치가 어긋날 수 있음 |
| 7 | **`completed[0] += 1` 스레드 안전성** | (Python 2번 파일 동일 패턴이지만 JS에서도 `fetch` 병렬 호출 시 공유 상태 변형 가능) | `ThreadPoolExecutor` 내에서 mutable list로 카운터를 관리하는 패턴이 Python GIL 보호 하에서는 대체로 안전하지만, 명시적 Lock 없이 사용됨 |

### 🟢 개선 권장

| # | 이슈 | 설명 |
|---|------|------|
| 8 | **인라인 스타일 과다 사용** | HTML 본문에 `style="..."` 속성이 다수 포함되어 있어 유지보수성이 떨어짐 |
| 9 | **접근성(A11y) 미비** | 버튼들에 `aria-label`이 없고, 색상만으로 출결 상태를 구분하며, 키보드 내비게이션 미지원 |
| 10 | **html2pdf.js CDN 의존** | CDN 장애 시 PDF 다운로드 기능 전체 불가. 로컬 폴백 필요 |

---

## 2. [1. 일일 출결 원페이지 만들기.py](file:///c:/Users/SDHS/Desktop/Anti/SDHS_2st/1.%20일일%20출결%20원페이지%20만들기.py) (671줄)

### 🟡 중요

| # | 이슈 | 위치 | 설명 |
|---|------|------|------|
| 11 | **출석/결석 카운팅 누락 (2교시)** | L525~L549 | `present_count`와 `absent_count`는 **1교시**에서만 증가시키고, 2교시 결과는 카운팅하지 않음. 요약 카드에 "1교시 기준"이라고 적혀 있어 의도적일 수 있지만, 2교시만 수강하는 학생의 결석이 누락됨 |
| 12 | **공휴일 하드코딩** | L87~L99 | 2026년 공휴일만 하드코딩되어 있어, 2027년이 되면 즉시 동작 불량. 매년 수동 갱신 필요 |
| 13 | **`input_with_timeout` 미사용** | L12~L43 | 이 함수가 정의되어 있으나 `main()` 내에서 한 번도 호출되지 않음 (죽은 코드) |
| 14 | **GAS URL 정규식 폴백이 너무 관대** | L69 | 세 번째 정규식(`(https://script\.google\.com/macros/s/[a-zA-Z0-9_-]+/exec)`)은 HTML 내의 **어떤** GAS URL이든 잡을 수 있어 backup URL을 가져올 위험이 있음 |
| 15 | **API 응답 타입 검증 부족** | L142, L182 | JSON 응답이 `list`가 아닌 `dict`로 올 경우(에러 응답 등) `len(students)` 호출 시 의미 없는 값 반환 |

### 🟢 개선 권장

| # | 이슈 | 설명 |
|---|------|------|
| 16 | **브라우저 경로 Edge 64bit 미탐색** | `C:\Program Files (x86)`만 검사하여 64bit Edge (`C:\Program Files\Microsoft\Edge\...`) 누락 |
| 17 | **에러 시 `input()` 대기** | GUI 없는 환경이나 자동화 파이프라인에서 행(hang)이 걸림 |

---

## 3. [2. 주간 출결 원페이지 만들기.py](file:///c:/Users/SDHS/Desktop/Anti/SDHS_2st/2.%20주간%20출결%20원페이지%20만들기.py) (565줄)

### 🟡 중요

| # | 이슈 | 위치 | 설명 |
|---|------|------|------|
| 18 | **`completed[0] += 1` 비원자적 연산 (ThreadPoolExecutor 내)** | L173 | `completed`는 mutable list(`[0]`)로 카운터를 관리하며, `completed[0] += 1`은 원자적 연산이 아님. Python GIL 덕분에 대부분 안전하지만, 진행률 출력이 부정확할 수 있음 |
| 19 | **40개 동시 GAS API 호출** | L149~L163 | 5일 × 4교실 × 2교시 = 40개 요청을 4개씩 병렬 전송. Google Apps Script의 속도 제한(rate limit)에 걸려 일부 요청이 실패할 수 있음. 실패 시 해당 데이터가 "미체크"로 처리되어 보고서 정확도 하락 |
| 20 | **`input_with_timeout` 미사용** | L28~L56 | 1번 파일과 동일하게 정의만 되어 있고 호출되지 않음 |

### 🟢 개선 권장

| # | 이슈 | 설명 |
|---|------|------|
| 21 | **Edge 64bit 경로 누락** | 1번 파일과 동일한 문제 |

---

## 4. [3. 일일 결석자 원페이지 만들기.py](file:///c:/Users/SDHS/Desktop/Anti/SDHS_2st/3.%20일일%20결석자%20원페이지%20만들기.py) (656줄)

### 🟡 중요

| # | 이슈 | 위치 | 설명 |
|---|------|------|------|
| 22 | **공휴일 하드코딩 (2026년 전용)** | L64~L76 | 1번 파일과 동일한 문제. 연도가 바뀌면 기본 날짜 자동 감지 로직이 잘못된 날짜를 선택할 수 있음 |
| 23 | **`present_total_count` 산정 로직 잠재 오류** | L321 | `present_total_count = scheduled_total_count - absent_total_count`로 계산하지만, "미체크" 상태의 학생도 출석으로 잡힘. 실제로는 미체크 학생 수를 빼야 정확함 |
| 24 | **XSS 취약점** | L337 | `item['remark']`의 사용자 입력 값이 HTML `title` 속성과 `td` 내부에 이스케이핑 없이 삽입됨. 비고란에 `<script>` 태그 등이 입력되면 XSS 공격 가능 |

### 🟢 개선 권장

| # | 이슈 | 설명 |
|---|------|------|
| 25 | **Edge 64bit 경로 누락** | 다른 파일들과 동일 |
| 26 | **`input_with_timeout` 미정의** | 이 파일에서는 아예 `input_with_timeout` 함수가 없는데, 동일 패턴의 다른 파일들에는 존재. 일관성 부재 |

---

## 5. [GAS_출결시트_코드.js](file:///c:/Users/SDHS/Desktop/Anti/SDHS_2st/GAS_출결시트_코드.js) (270줄)

### 🟡 중요

| # | 이슈 | 위치 | 설명 |
|---|------|------|------|
| 27 | **`setHeaders()`는 ContentService에서 미지원** | L75~L78, L174~L177, L181~L184 | Google Apps Script의 `ContentService.TextOutput`에는 `setHeaders()` 메서드가 없음. 이 코드는 **런타임 에러를 발생시킬 수 있음**. CORS 헤더는 GAS 웹앱에서 자동 처리되므로 이 호출을 제거해야 함 |
| 28 | **`tryLock` 실패 시 무시** | L13 | `lock.tryLock(10000)`이 `false`를 반환(10초 내 lock 획득 실패)해도 그대로 진행하여 동시 쓰기 충돌 가능. `if (!lock.tryLock(10000)) throw ...` 패턴 필요 |
| 29 | **전체 시트 읽기/쓰기 성능** | L30~L65, L97~L152 | `getDataRange().getValues()`로 전체 시트를 읽고 `setValues()`로 전체를 다시 쓰는 방식. 데이터가 수천 행으로 늘어나면 6분 실행 제한에 걸릴 수 있음 |

### 🟢 개선 권장

| # | 이슈 | 설명 |
|---|------|------|
| 30 | **doGet 파라미터 검증 부재** | `e.parameter.date`, `.day`, `.period`, `.room`이 없을 때 `toString()` 호출 시 에러 발생 가능. null 체크 필요 |
| 31 | **감독교사 명단 시트명 하드코딩** | `'감독교사명단'`, `'학생명단'`, `'Attendance_Log'` — 시트명이 변경되면 바로 에러 |

---

## 6. BAT 파일 3개

### 🟡 중요

| # | 이슈 | 파일 | 설명 |
|---|------|------|------|
| 32 | **인코딩 깨짐** | 3개 전부 | BAT 파일의 한글이 깨져서 출력됨 (UTF-8로 저장되었으나 `cmd.exe`는 기본 CP949). `chcp 65001` 누락 |
| 33 | **Python 명령어 하드코딩** | 3개 전부 | `python` 명령어만 사용. 시스템에 Python이 `py` 런처로만 설치된 경우 실패. `py -3` 또는 `python3` 폴백 없음 |

---

## 📊 요약 통계

| 심각도 | 개수 | 주요 분류 |
|--------|------|-----------|
| 🔴 치명적 | 3개 | CSS 중복 정의, 함수 시그니처 불일치 |
| 🟡 중요 | 18개 | 미정의 CSS 변수, 공휴일 하드코딩, GAS `setHeaders` 오류, 카운팅 로직, XSS |
| 🟢 개선 권장 | 12개 | 죽은 코드, Edge 경로, 접근성, 인코딩 |
| **합계** | **33개** | |

## 🎯 우선 수정 권장 TOP 5

1. **GAS `setHeaders()` 제거** (#27) — 실제 런타임 에러 가능성 가장 높음
2. **`#loadingOverlay` / `.loader` CSS 중복 해소** (#1, #2) — 시각적 버그
3. **미정의 CSS 변수 추가** (#4) — 출결 테이블 렌더링 오류
4. **공휴일 하드코딩 → 동적 처리** (#12, #22) — 연도 전환 시 즉시 장애
5. **`startAppSession` 함수 시그니처 정리** (#3) — 의도 불명확 코드
