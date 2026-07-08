@echo off
setlocal

set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"

if not exist "%CHROME%" (
    echo Google Chrome was not found.
    pause
    exit /b 1
)

set "PROFILE=%LOCALAPPDATA%\BaiyingDataTool\chrome_profile_v2"
if not exist "%PROFILE%" mkdir "%PROFILE%"

start "" "%CHROME%" --remote-debugging-port=9222 --user-data-dir="%PROFILE%" --no-first-run "https://buyin.jinritemai.com/"
endlocal
