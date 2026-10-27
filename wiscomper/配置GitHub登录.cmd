@echo off
chcp 65001 >nul
setlocal
title GitHub Local Login Setup
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Project Python environment is missing. Please install workspace dependencies first.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\configure_github.py"
set "githubSetupExit=%ERRORLEVEL%"
echo.
pause
exit /b %githubSetupExit%
