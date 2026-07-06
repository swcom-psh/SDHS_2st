/**
 * Google Apps Script for Yaja Attendance Management (v30 - Apply API via static page + Google Sign-In)
 *
 * [적용 방법]
 * 1. 구글 스프레드시트의 [확장 프로그램] -> [Apps Script] 창을 엽니다.
 * 2. 기존의 모든 코드를 지우고 이 스크립트로 덮어씁니다. (Code.gs)
 * 3. OAUTH_CLIENT_ID 값을 Google Cloud Console에서 발급받은 OAuth 클라이언트 ID로 교체합니다.
 * 4. 스프레드시트에 "신청설정" 시트를 만들고 B1에 신청 시작일시, B2에 마감일시를 입력합니다.
 *    (둘 다 비워두면 기본적으로 신청이 닫힌 상태로 동작합니다 - 안전 기본값)
 * 5. 오른쪽 상단의 [배포] -> [배포 관리]에서 기존 웹앱 버전을 "새 버전"으로 올려서 다시 배포합니다.
 *    - 출결 체크 시스템(index.html)과 신청 페이지(apply.html) 모두 같은 웹앱 URL의 doPost/doGet을 함께 사용합니다.
 * 6. apply.html의 GAS_URL, GOOGLE_CLIENT_ID 값을 실제 값으로 교체하고 정적 호스팅(GitHub Pages 등)에 올립니다.
 */

// =========================================================
// ================  기존 출결 체크 시스템  ===================
// =========================================================

function doPost(e) {
  var data = JSON.parse(e.postData.contents);

  // --- [학생 야자 신청 API] apply.html(정적 페이지 + 구글 로그인)에서 호출 ---
  if (data.type === "apply_status" || data.type === "apply_submit") {
    return handleApplyRequest_(data);
  }
  // ----------------------------------------------------------------------

  var lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) {
    return ContentService.createTextOutput(JSON.stringify({ "result": "error", "message": "서버가 바쁩니다. 잠시 후 다시 시도해주세요." }))
      .setMimeType(ContentService.MimeType.JSON);
  }
  try {
    var sheetName = (data.sheetTarget === "summer") ? "하계 야자 출석" : "Attendance_Log";
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName(sheetName);

    if (!sheet) {
      sheet = ss.insertSheet(sheetName);
      sheet.appendRow(["체크시간", "감독교사", "날짜", "요일", "교시", "반", "학번", "이름", "상태", "비고"]);
    }

    var timestamp = new Date();

    // --- [과거 메모 일괄 전송 처리 (배열 형태)] ---
    if (data.type === "past_memos") {
      var memos = data.memos;
      var dataRange = sheet.getDataRange();
      var allValues = dataRange.getValues();
      var displayValues = dataRange.getDisplayValues();
      var newRows = [];

      memos.forEach(function (m) {
        var s = m.student;
        var found = false;

        for (var i = 1; i < displayValues.length; i++) {
          var r = displayValues[i];
          if (cleanDate(r[2]) === cleanDate(m.date) &&
            r[3].toString().trim() === m.day.trim() &&
            r[4].toString().trim() === m.period.trim() &&
            r[5].toString().trim() === m.room.trim() &&
            cleanId(r[6]) === cleanId(s.id)) {

            // 기존 데이터가 있으면 '비고'와 '체크시간'만 업데이트 (출결 및 감독교사 철저히 보존)
            allValues[i][0] = timestamp;
            allValues[i][9] = s.remark;
            found = true;
            break;
          }
        }

        if (!found) {
          // 아예 빈 기록이었다면 "결석" 처리와 함께 메모를 추가
          newRows.push([
            timestamp, m.supervisor || "", m.date, m.day, m.period, m.room,
            s.id, s.name, "결석", s.remark
          ]);
        }
      });

      // 변경된 기존 배열 쓰기
      dataRange.setValues(allValues);

      // [변경 사항] 새로 추가된 행이 있다면 최상단(헤더 바로 아래인 2행)에 삽입
      if (newRows.length > 0) {
        sheet.insertRowsBefore(2, newRows.length);
        sheet.getRange(2, 1, newRows.length, newRows[0].length).setValues(newRows);
      }

      return ContentService.createTextOutput(JSON.stringify({ "result": "success" }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    // ----------------------------------------------------

    // 기존의 일괄(배치) 처리 로직
    var incomingStudents = (data.type === "single") ? [data.student] : data.students;

    var incomingMap = {};
    incomingStudents.forEach(function (s) {
      var statusText = s.status ? "출석" : "결석";
      var key = cleanId(s.id) + "_" + (s.name || "").toString().trim();
      incomingMap[key] = {
        status: statusText,
        remark: s.remark || "",
        student: s,
        handled: false
      };
    });

    var dataRange = sheet.getDataRange();
    var allValues = dataRange.getValues();
    var displayValues = dataRange.getDisplayValues();

    var anyStatusChanged = false;
    var matchingRowIndices = [];

    for (var i = 1; i < displayValues.length; i++) {
      var row = displayValues[i];
      var key = cleanId(row[6]) + "_" + row[7].toString().trim();

      if (cleanDate(row[2]) === cleanDate(data.date) &&
        row[3].toString().trim() === data.day.trim() &&
        row[4].toString().trim() === data.period.trim() &&
        row[5].toString().trim() === data.room.trim() &&
        incomingMap[key]) {

        var incoming = incomingMap[key];
        matchingRowIndices.push({
          index: i,
          incoming: incoming
        });

        if (row[8].toString().trim() !== incoming.status) {
          anyStatusChanged = true;
        }
      }
    }

    var isDataModified = false;

    matchingRowIndices.forEach(function (match) {
      var idx = match.index;
      var incoming = match.incoming;
      var row = displayValues[idx];
      incoming.handled = true;

      if (anyStatusChanged) {
        allValues[idx][0] = timestamp;
        var finalSupervisor = (incoming.student && incoming.student.supervisor) ? incoming.student.supervisor : (data.supervisor || "");
        allValues[idx][1] = finalSupervisor;
        allValues[idx][8] = incoming.status;
        allValues[idx][9] = incoming.remark;
        isDataModified = true;
      } else {
        if (row[8].toString().trim() !== incoming.status || row[9].toString().trim() !== incoming.remark) {
          allValues[idx][8] = incoming.status;
          allValues[idx][9] = incoming.remark;
          isDataModified = true;
        }
      }
    });

    if (isDataModified) {
      dataRange.setValues(allValues);
    }

    var newRows = [];
    incomingStudents.forEach(function (s) {
      var key = cleanId(s.id) + "_" + (s.name || "").toString().trim();
      if (!incomingMap[key].handled) {
        var finalSupervisor = s.supervisor || data.supervisor || "";
        newRows.push([
          timestamp, finalSupervisor, data.date, data.day, data.period, data.room,
          s.id, s.name, (s.status ? "출석" : "결석"), s.remark || ""
        ]);
      }
    });

    // [변경 사항] 새로 추가된 행이 있다면 최상단(헤더 바로 아래인 2행)에 삽입
    if (newRows.length > 0) {
      sheet.insertRowsBefore(2, newRows.length);
      sheet.getRange(2, 1, newRows.length, newRows[0].length).setValues(newRows);
    }

    return ContentService.createTextOutput(JSON.stringify({ "result": "success" }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ "result": "error", "message": err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  } finally {
    lock.releaseLock();
  }
}

function doGet(e) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var action = e.parameter.action;

  if (action === 'getTeachers') {
    var teacherSheet = ss.getSheetByName('감독교사명단');
    if (!teacherSheet) return ContentService.createTextOutput(JSON.stringify([])).setMimeType(ContentService.MimeType.JSON);
    var values = teacherSheet.getDataRange().getDisplayValues();
    var teachers = [];
    for (var i = 1; i < values.length; i++) {
      if (values[i][0]) teachers.push(values[i][0].toString().trim());
    }
    return ContentService.createTextOutput(JSON.stringify(teachers)).setMimeType(ContentService.MimeType.JSON);
  }

  if (action === 'getStudents') {
    var studentSheet = ss.getSheetByName("학생명단");
    if (!studentSheet) return ContentService.createTextOutput("[]").setMimeType(ContentService.MimeType.JSON);
    var values = studentSheet.getDataRange().getDisplayValues();
    var headers = values[0];
    var jsonArray = values.slice(1).map(function (row) {
      var obj = {};
      headers.forEach(function (header, j) { obj[header] = row[j]; });
      return obj;
    });
    return ContentService.createTextOutput(JSON.stringify(jsonArray)).setMimeType(ContentService.MimeType.JSON);
  }

  if (action === 'getSummerStudents') {
    var summerSheet = ss.getSheetByName("하계 학생명단");
    if (!summerSheet) return ContentService.createTextOutput("[]").setMimeType(ContentService.MimeType.JSON);
    var sValues = summerSheet.getDataRange().getDisplayValues();
    var sHeaders = sValues[0];
    var sJsonArray = sValues.slice(1)
      .filter(function (row) { return row[1] && row[1].toString().trim() !== ""; }) // 학번이 있는 행만
      .map(function (row) {
        var obj = {};
        sHeaders.forEach(function (header, j) { obj[header.toString().trim()] = row[j]; });
        return obj;
      });
    return ContentService.createTextOutput(JSON.stringify(sJsonArray)).setMimeType(ContentService.MimeType.JSON);
  }

  var sheetName = (e.parameter.sheetTarget === "summer") ? "하계 야자 출석" : "Attendance_Log";
  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) return ContentService.createTextOutput("{}").setMimeType(ContentService.MimeType.JSON);
  var displayValues = sheet.getDataRange().getDisplayValues();
  var results = {};
  var roomFilter = e.parameter.room ? e.parameter.room.toString().trim() : null;
  for (var i = 1; i < displayValues.length; i++) {
    var row = displayValues[i];
    if (cleanDate(row[2]) === cleanDate(e.parameter.date) &&
      row[3].toString().trim() === e.parameter.day.toString().trim() &&
      row[4].toString().trim() === e.parameter.period.toString().trim() &&
      (!roomFilter || row[5].toString().trim() === roomFilter)) {

      var studentId = cleanId(row[6]);
      // 최신 기록이 최상단에 기록되므로, 동일 날짜/교시에 중복된 학생 기록이 존재할 경우
      // 이미 담긴 데이터(가장 최근 데이터)를 유지하고, 더 아래에 위치한 이전 기록으로 덮어쓰지 않습니다.
      if (!results.hasOwnProperty(studentId)) {
        results[studentId] = {
          status: (row[8].toString().trim() == "출석"),
          remark: row[9] || "",
          supervisor: row[1] || ""
        };
      }
    }
  }
  return ContentService.createTextOutput(JSON.stringify(results)).setMimeType(ContentService.MimeType.JSON);
}

// === 🟢 데이터 정규화 유틸리티 함수 ===

/**
 * 어떤 날짜 포맷이든 "YYYY.M.D" 형태로 일체화하여 비교합니다.
 * 예) "2026. 5. 21.", "2026. 05. 21", "2026-5-21" 등 모두 "2026.5.21"로 변환
 */
function cleanDate(dateVal) {
  if (!dateVal) return "";
  if (dateVal instanceof Date) {
    return dateVal.getFullYear() + "." + (dateVal.getMonth() + 1) + "." + dateVal.getDate();
  }
  var str = dateVal.toString().trim();
  var match = str.match(/(\d{4})[^\d]+(\d{1,2})[^\d]+(\d{1,2})/);
  if (match) {
    return match[1] + "." + parseInt(match[2], 10) + "." + parseInt(match[3], 10);
  }
  return str.replace(/\s+/g, "").replace(/\.+$/, "");
}

/**
 * 학번의 공백을 제거하고 온전한 문자열로 통일하여 타입 불일치 비교 에러를 방지합니다.
 */
function cleanId(idVal) {
  if (idVal === null || idVal === undefined) return "";
  return idVal.toString().trim();
}

// =========================================================
// ================  학생 야자 신청 시스템  ===================
// =========================================================
//
// apply.html(정적 페이지) -> 구글 로그인(Google Identity Services)으로 ID 토큰 발급
//   -> doPost({ type: "apply_status" | "apply_submit", idToken, selection }) 호출
//   -> 이 서버에서 idToken을 구글 서버에 직접 검증(tokeninfo) 후 이메일/도메인 확인
//
// [신청 대상 시트] "2학기 학생명단"
// 열 구성: 순번, 학번, 이름, 신청시간, 참여시간,
//          월_배정, 화_배정, 수_배정, 목_배정, 금_배정, 참여횟수,
//          월1, 월2, 화1, 화2, 수1, 수2, 목1, 목2, 금1, 금2
//
// - 월_배정~금_배정 : 해당 요일에 참여하면 "참여", 아니면 ""
// - 월1,월2,... : 해당 요일의 1교시/2교시 참여 여부 ("참여" / "")
// - 참여횟수 : 체크된 교시(월1~금2) 총 개수
// - 신청시간 : 최초 제출 시각 (한번 기록되면 변경 안 함)
// - 참여시간 : 마지막 수정(제출) 시각
//
// [사전 준비]
// - "신청설정" 시트: A1 "시작일시" / B1 <날짜시간>, A2 "종료일시" / B2 <날짜시간>
//   (B1, B2를 비워두면 기본적으로 신청 마감 상태로 동작 - 안전 기본값)
// - 학생 로그인 이메일 형식: 연도(4자리)+학번(4자리)@sdhs.gwe.hs.kr
//   예) 2학년 1반 2번, 2026학년도 입학 기준 -> 20262102@sdhs.gwe.hs.kr -> 학번 "2102"
// - OAUTH_CLIENT_ID : Google Cloud Console에서 발급받은 OAuth 2.0 클라이언트 ID(웹 애플리케이션)로 교체 필요.
//   apply.html의 GOOGLE_CLIENT_ID와 반드시 동일한 값이어야 합니다.

var OAUTH_CLIENT_ID = "783955617247-32toh8t2khrb9l1qj1sbhl5t4it7au54.apps.googleusercontent.com";
var APPLY_SHEET_NAME = "2학기 학생명단";
var APPLY_SETTING_SHEET_NAME = "신청설정";
var ALLOWED_DOMAIN = "sdhs.gwe.hs.kr";

var APPLY_DAYS = [
  { key: "월", dayCol: "F", p1Col: "L", p2Col: "M" },
  { key: "화", dayCol: "G", p1Col: "N", p2Col: "O" },
  { key: "수", dayCol: "H", p1Col: "P", p2Col: "Q" },
  { key: "목", dayCol: "I", p1Col: "R", p2Col: "S" },
  { key: "금", dayCol: "J", p1Col: "T", p2Col: "U" }
];

/** 로그인한 사용자 이메일로 학번을 추출. 형식: 연도(4자리)+학번(4자리)@도메인 */
function getStudentIdFromEmail_(email) {
  var local = email.split('@')[0];
  if (!/^\d{8}$/.test(local)) return null;
  return local.substring(4); // 뒤 4자리가 학번
}

/** 신청 기간 정보를 "신청설정" 시트에서 읽어옴 */
function getApplyPeriod_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(APPLY_SETTING_SHEET_NAME);
  if (!sheet) {
    return { start: null, end: null };
  }
  var start = sheet.getRange("B1").getValue();
  var end = sheet.getRange("B2").getValue();
  return {
    start: (start instanceof Date) ? start : null,
    end: (end instanceof Date) ? end : null
  };
}

function isApplyOpen_() {
  var period = getApplyPeriod_();
  var now = new Date();
  if (!period.start && !period.end) return false; // 설정 안 했으면 기본적으로 닫힘(안전)
  if (period.start && now < period.start) return false;
  if (period.end && now > period.end) return false;
  return true;
}

function formatPeriodText_(d) {
  if (!d) return "";
  return Utilities.formatDate(d, Session.getScriptTimeZone(), "yyyy-MM-dd HH:mm");
}

/** 학생명단 시트에서 학번에 해당하는 행 번호(1-base, 헤더 포함 실제 행번호)를 찾음 */
function findStudentRow_(sheet, studentId) {
  var values = sheet.getDataRange().getDisplayValues();
  for (var i = 1; i < values.length; i++) {
    if (cleanId(values[i][1]) === cleanId(studentId)) {
      return { rowIndex: i + 1, row: values[i] }; // rowIndex: 실제 시트 행 번호
    }
  }
  return null;
}

/**
 * 구글 ID 토큰(JWT)을 구글 서버에 직접 검증 요청하여 신뢰할 수 있는 이메일/이름을 얻어냄.
 * - aud(클라이언트 ID 일치), hd(학교 도메인 일치), email_verified 를 모두 확인합니다.
 * - 반환: { email, name } (name은 구글 프로필 이름; 없으면 이메일 아이디로 대체)
 */
function verifyGoogleIdToken_(idToken) {
  if (!idToken) throw new Error("로그인 토큰이 없습니다. 다시 로그인해주세요.");

  var resp = UrlFetchApp.fetch("https://oauth2.googleapis.com/tokeninfo?id_token=" + encodeURIComponent(idToken), {
    muteHttpExceptions: true
  });
  if (resp.getResponseCode() !== 200) {
    throw new Error("로그인 정보가 유효하지 않습니다. 다시 로그인해주세요.");
  }
  var info = JSON.parse(resp.getContentText());

  if (info.aud !== OAUTH_CLIENT_ID) {
    throw new Error("허용되지 않은 클라이언트입니다.");
  }
  if (info.email_verified !== "true" && info.email_verified !== true) {
    throw new Error("이메일이 인증되지 않은 계정입니다.");
  }
  if (info.hd !== ALLOWED_DOMAIN) {
    throw new Error("학교 계정(@" + ALLOWED_DOMAIN + ")으로 로그인해야 합니다.");
  }

  var name = (info.name || "").toString().trim();
  if (!name) name = info.email.split('@')[0];
  return { email: info.email, name: name };
}

// 학번 형식(8자리 숫자)이 아닌 계정도 로그인/테스트를 허용할 이메일 목록.
// 이 계정들은 이메일 아이디(@ 앞부분)를 학번 대용으로 사용합니다.
// 운영 전환 시 빈 배열로 비워두면, 정상 학번 형식 계정만 신청할 수 있습니다.
var TEST_OVERRIDE_EMAILS = ["pshyun1109@sdhs.gwe.hs.kr"];

// 명단 시트 헤더 (시트가 없거나 비어 있을 때 자동으로 생성)
var APPLY_HEADERS = [
  "순번", "학번", "이름", "신청시간", "참여시간",
  "월_배정", "화_배정", "수_배정", "목_배정", "금_배정", "참여횟수",
  "월1", "월2", "화1", "화2", "수1", "수2", "목1", "목2", "금1", "금2"
];

/** 명단 시트를 반환. 없으면 생성하고, 비어 있으면 헤더를 채운다. */
function getApplySheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(APPLY_SHEET_NAME);
  if (!sheet) sheet = ss.insertSheet(APPLY_SHEET_NAME);
  if (sheet.getLastRow() === 0) sheet.appendRow(APPLY_HEADERS);
  return sheet;
}

/** 학번으로 행을 찾고, 없으면 새 행(순번/학번/이름)을 추가한 뒤 그 행 정보를 반환. */
function findOrCreateStudentRow_(sheet, studentId, name) {
  var found = findStudentRow_(sheet, studentId);
  if (found) return found;

  var newIndex = sheet.getLastRow() + 1;
  var row = new Array(APPLY_HEADERS.length).fill("");
  row[0] = Math.max(0, sheet.getLastRow() - 1) + 1; // A: 순번(헤더 제외)
  row[1] = studentId;                                // B: 학번
  row[2] = name || "";                               // C: 이름

  // 학번 칸은 텍스트로 고정 -> "0101" 같은 앞자리 0 학번이 숫자로 바뀌지 않게
  sheet.getRange(newIndex, 2).setNumberFormat("@");
  sheet.getRange(newIndex, 1, 1, row.length).setValues([row]);

  return { rowIndex: newIndex, row: row };
}

/** doPost에서 apply_status / apply_submit 요청을 처리 */
function handleApplyRequest_(data) {
  try {
    var auth = verifyGoogleIdToken_(data.idToken);
    var studentId = getStudentIdFromEmail_(auth.email);
    if (!studentId) {
      // 학번 형식이 아니면, 허용된 테스트 계정에 한해 이메일 아이디를 학번 대용으로 사용
      if (TEST_OVERRIDE_EMAILS.indexOf(auth.email) !== -1) {
        studentId = auth.email.split('@')[0];
      } else {
        throw new Error("계정 형식에서 학번을 확인할 수 없습니다. 담당 선생님께 문의하세요. (" + auth.email + ")");
      }
    }

    if (data.type === "apply_status") {
      return ContentService.createTextOutput(JSON.stringify(getMyApplicationData_(studentId, auth.name)))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // apply_submit
    var lock = LockService.getScriptLock();
    if (!lock.tryLock(10000)) {
      throw new Error("서버가 바쁩니다. 잠시 후 다시 시도해주세요.");
    }
    try {
      var result = submitApplication_(studentId, data.selection || {}, auth.name);
      return ContentService.createTextOutput(JSON.stringify(result))
        .setMimeType(ContentService.MimeType.JSON);
    } finally {
      lock.releaseLock();
    }
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ result: "error", message: err.message || String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * 본인 정보 + 기존 신청 내용 + 신청 가능 여부를 반환.
 * 아직 신청 행이 없는(최초 로그인) 학생은 빈 신청 폼을 돌려준다. (행은 저장 시 생성)
 * profileName: 구글 프로필 이름 (행이 아직 없을 때 화면에 표시할 이름)
 */
function getMyApplicationData_(studentId, profileName) {
  var sheet = getApplySheet_();

  var found = findStudentRow_(sheet, studentId);
  var period = getApplyPeriod_();

  if (!found) {
    // 최초 로그인: 저장 전이라 행이 없음 -> 빈 폼 반환
    var emptySelection = {};
    APPLY_DAYS.forEach(function (d) { emptySelection[d.key] = { p1: false, p2: false }; });
    return {
      result: "success",
      studentId: studentId,
      name: profileName || "",
      applyTime: "",
      updateTime: "",
      selection: emptySelection,
      isOpen: isApplyOpen_(),
      periodText: formatPeriodText_(period.start) + " ~ " + formatPeriodText_(period.end)
    };
  }

  var row = found.row;
  var name = row[2] || profileName || "";
  var applyTime = row[3] || "";
  var updateTime = row[4] || "";

  var colIdx = { F: 5, G: 6, H: 7, I: 8, J: 9, L: 11, M: 12, N: 13, O: 14, P: 15, Q: 16, R: 17, S: 18, T: 19, U: 20 };
  var selection = {};
  APPLY_DAYS.forEach(function (d) {
    selection[d.key] = {
      p1: row[colIdx[d.p1Col] - 1] === "참여",
      p2: row[colIdx[d.p2Col] - 1] === "참여"
    };
  });

  return {
    result: "success",
    studentId: studentId,
    name: name,
    applyTime: applyTime,
    updateTime: updateTime,
    selection: selection,
    isOpen: isApplyOpen_(),
    periodText: formatPeriodText_(period.start) + " ~ " + formatPeriodText_(period.end)
  };
}

/**
 * 신청/수정 제출. selection: { "월": {p1:bool, p2:bool}, "화": {...}, ... }
 * 호출 전 LockService로 잠겨 있어야 합니다(handleApplyRequest_에서 처리).
 */
function submitApplication_(studentId, selection, name) {
  if (!isApplyOpen_()) {
    throw new Error("신청 기간이 아닙니다. 변경/취소가 불가능합니다.");
  }

  var sheet = getApplySheet_();

  // 행이 없으면(최초 신청) 새로 생성해서 그 행에 기록
  var found = findOrCreateStudentRow_(sheet, studentId, name);
  var rowIndex = found.rowIndex;
  var existingApplyTime = found.row[3];
  var now = new Date();
  var count = 0;

  var colMap = { F: 6, G: 7, H: 8, I: 9, J: 10, L: 12, M: 13, N: 14, O: 15, P: 16, Q: 17, R: 18, S: 19, T: 20, U: 21 };

  APPLY_DAYS.forEach(function (d) {
    var sel = selection[d.key] || { p1: false, p2: false };
    var p1 = !!sel.p1;
    var p2 = !!sel.p2;
    var dayParticipate = (p1 || p2);

    sheet.getRange(rowIndex, colMap[d.dayCol]).setValue(dayParticipate ? "참여" : "");
    sheet.getRange(rowIndex, colMap[d.p1Col]).setValue(p1 ? "참여" : "");
    sheet.getRange(rowIndex, colMap[d.p2Col]).setValue(p2 ? "참여" : "");

    if (p1) count++;
    if (p2) count++;
  });

  sheet.getRange(rowIndex, 11).setValue(count); // 참여횟수
  if (!existingApplyTime) {
    sheet.getRange(rowIndex, 4).setValue(now); // 신청시간(최초 1회만)
  }
  sheet.getRange(rowIndex, 5).setValue(now); // 참여시간(최종 수정시각)

  return { result: "success" };
}
