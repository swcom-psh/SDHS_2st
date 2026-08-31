@echo off
chcp 65001 >nul 2>&1
title 주간 출결 보고서
cd /d "%~dp0"

echo ============================================================
echo  원하는 주간 날짜를 입력하세요 (예: 20260831)
echo  그 주 아무 날이나 적으면 해당 주 월요일로 맞춰집니다.
echo  [엔터]를 그냥 누르면 최근 주간이 자동 설정됩니다.
echo ============================================================
set /p USER_DATE="날짜 입력: "

REM Python 실행 명령 자동 탐색: py -3 우선, 없으면 python
where py >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py -3
) else (
    set PYTHON_CMD=python
)

if "%USER_DATE%"=="" (
    %PYTHON_CMD% "2. 주간 출결 원페이지 만들기.py"
) else (
    %PYTHON_CMD% "2. 주간 출결 원페이지 만들기.py" %USER_DATE%
)

pause