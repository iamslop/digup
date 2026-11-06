@echo off
setlocal enabledelayedexpansion

rem vOidnet - stop the local preview server (python -m http.server on port 4173)
rem Finds whatever is listening on the port and ends that process.

set "PORT=4173"
set "PIDS="

rem --- administrator check: High integrity SID, so it works on any locale ---
whoami /groups 2>nul | findstr /C:"S-1-16-12288" >nul 2>&1
if errorlevel 1 (
  echo asking windows for administrator rights...
  if "%~1"=="" (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs" >nul 2>&1
  ) else (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -WorkingDirectory '%~dp0' -Verb RunAs" >nul 2>&1
  )
  if errorlevel 1 echo   elevation was cancelled or blocked - right-click this file and pick "Run as administrator".
  exit /b 0
)

rem netstat state names are localized, so find the listener by its wildcard
rem foreign address (0.0.0.0:0 / [::]:0) instead of the word LISTENING.
for /f "tokens=2,3,5" %%A in ('netstat -ano -p TCP ^| findstr /C:":%PORT%"') do (
  if "%%B"=="0.0.0.0:0" call :add %%C
  if "%%B"=="[::]:0" call :add %%C
)

if not defined PIDS (
  echo vOidnet is not running on port %PORT%.
  echo nothing to stop.
  goto finish
)

for %%P in (!PIDS!) do (
  echo stopping vOidnet server ^(pid %%P^)...
  taskkill /PID %%P /F >nul 2>&1
  if errorlevel 1 (
    echo   could not stop pid %%P - run this file as administrator and try again.
  ) else (
    echo   stopped pid %%P.
  )
)

echo.
echo vOidnet stopped. port %PORT% is free.

:finish
pause
exit /b 0

:add
set "KNOWN=0"
if defined PIDS for %%X in (!PIDS!) do if "%%X"=="%~1" set "KNOWN=1"
if "!KNOWN!"=="0" set "PIDS=!PIDS! %~1"
exit /b 0
