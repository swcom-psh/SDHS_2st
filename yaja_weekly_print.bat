@echo off
chcp 65001 > nul
title 야자 주간 원페이퍼 출결 리포트 생성기
cd /d "%~dp0"

echo ============================================================
echo  조회할 주간의 월요일 날짜를 입력하세요 (형식: YYYY-MM-DD)
echo  예시: 지난주 보고서는 2026-05-11 입력
echo  [엔터]를 그냥 누르면 최근 야자 주간으로 자동 진행합니다.
echo ============================================================
set /p USER_DATE="날짜 입력: "

if "%USER_DATE%"=="" (
    python print_yaja_weekly.py
) else (
    python print_yaja_weekly.py %USER_DATE%
)

pause
