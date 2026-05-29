/**
 * Google Apps Script for Yaja Attendance Management (v28 - Top Insertion with Duplicate Protection)
 * 
 * [적용 방법]
 * 1. 구글 스프레드시트의 [확장 프로그램] -> [Apps Script] 창을 엽니다.
 * 2. 기존의 doPost(e) 및 기타 코드를 모두 지우고 이 스크립트로 덮어씁니다.
 * 3. 오른쪽 상단의 [배포] -> [배포 관리]에서 기존 웹앱 버전을 "새 버전"으로 올려서 다시 배포합니다.
 * 4. 새로 생성된 웹앱 URL을 복사하여 index.html의 gasUrl 및 gasBackupUrl에 업데이트합니다.
 */

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.tryLock(10000);
  try {
    var data = JSON.parse(e.postData.contents);
    var sheetName = "Attendance_Log";
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
      
      memos.forEach(function(m) {
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
                           .setMimeType(ContentService.MimeType.JSON)
                           .setHeaders({
                             "Access-Control-Allow-Origin": "*",
                             "Access-Control-Allow-Methods": "POST, GET, OPTIONS"
                           });
    }
    // ----------------------------------------------------

    // 기존의 일괄(배치) 처리 로직
    var incomingStudents = (data.type === "single") ? [data.student] : data.students;

    var incomingMap = {};
    incomingStudents.forEach(function(s) {
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

    matchingRowIndices.forEach(function(match) {
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
    incomingStudents.forEach(function(s) {
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
                         .setMimeType(ContentService.MimeType.JSON)
                         .setHeaders({
                           "Access-Control-Allow-Origin": "*",
                           "Access-Control-Allow-Methods": "POST, GET, OPTIONS"
                         });
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ "result": "error", "message": err.toString() }))
                         .setMimeType(ContentService.MimeType.JSON)
                         .setHeaders({
                           "Access-Control-Allow-Origin": "*",
                           "Access-Control-Allow-Methods": "POST, GET, OPTIONS"
                         });
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
    var jsonArray = values.slice(1).map(function(row) {
      var obj = {};
      headers.forEach(function(header, j) { obj[header] = row[j]; });
      return obj;
    });
    return ContentService.createTextOutput(JSON.stringify(jsonArray)).setMimeType(ContentService.MimeType.JSON);
  }

  var sheet = ss.getSheetByName("Attendance_Log");
  if (!sheet) return ContentService.createTextOutput("{}").setMimeType(ContentService.MimeType.JSON);
  var displayValues = sheet.getDataRange().getDisplayValues();
  var results = {};
  for (var i = 1; i < displayValues.length; i++) {
    var row = displayValues[i];
    if (cleanDate(row[2]) === cleanDate(e.parameter.date) && 
        row[3].toString().trim() === e.parameter.day.toString().trim() && 
        row[4].toString().trim() === e.parameter.period.toString().trim() && 
        row[5].toString().trim() === e.parameter.room.toString().trim()) {
      
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
