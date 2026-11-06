@echo off
setlocal enabledelayedexpansion

rem vOidnet - start the local site + search log on port 4173
chcp 65001 >nul
rem usage: start.bat              start, wait until it answers, open the browser
rem        start.bat /nobrowser   start without opening a browser window

set "PORT=4173"
set "OPEN=1"
if /i "%~1"=="/nobrowser" set "OPEN=0"

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

call :listening
if defined PIDS (
  echo vOidnet is already running on port %PORT%.
  call :openbrowser
  goto finish
)

set "PY="
where python >nul 2>&1
if not errorlevel 1 set "PY=python"
if not defined PY (
  where py >nul 2>&1
  if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
  where python3 >nul 2>&1
  if not errorlevel 1 set "PY=python3"
)

if not defined PY (
  echo python was not found on PATH - install python 3, or serve the folder another way.
  goto finish
)

if not exist "%~dp0server.py" (
  echo server.py is missing next to this file - restore it and try again.
  goto finish
)

echo starting vOidnet on http://127.0.0.1:%PORT%/ ...
start "vOidnet log" /D "%~dp0." cmd /c "%PY% server.py"

set "READY=0"
for /l %%I in (1,1,20) do (
  if "!READY!"=="0" (
    call :listening
    if defined PIDS set "READY=1"
    if "!READY!"=="0" "%SystemRoot%\System32\ping.exe" -n 2 127.0.0.1 >nul 2>&1
  )
)

if "!READY!"=="1" (
  echo server is up - searches appear in the "vOidnet log" window.
  call :openbrowser
) else (
  echo could not confirm the server on port %PORT%.
  echo look at the "vOidnet log" window for the real error.
)

:finish
pause
exit /b 0

:openbrowser
if "%OPEN%"=="1" start "" "http://127.0.0.1:%PORT%/"
exit /b 0

:listening
set "PIDS="
for /f "tokens=2,3,5" %%A in ('netstat -ano -p TCP ^| findstr /C:":%PORT%"') do (
  if "%%B"=="0.0.0.0:0" call :add %%C
  if "%%B"=="[::]:0" call :add %%C
)
exit /b 0

:add
set "KNOWN=0"
if defined PIDS for %%X in (!PIDS!) do if "%%X"=="%~1" set "KNOWN=1"
if "!KNOWN!"=="0" set "PIDS=!PIDS! %~1"
exit /b 0
