@echo off
cd /d "%~dp0"

curl.exe -s --max-time 2 "http://127.0.0.1:9222/json/version" >nul 2>&1
if errorlevel 1 call "%~dp0start_baiying_chrome_debug.cmd"

python web_app.py
if errorlevel 1 pause
