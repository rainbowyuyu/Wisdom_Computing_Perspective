@echo off
setlocal
where pwsh.exe >nul 2>nul
if errorlevel 1 (
  echo PowerShell 7 is required. Install it, then run Stop.cmd again.
  exit /b 1
)
pwsh.exe -NoLogo -NoProfile -NonInteractive -File "%~dp0Stop.ps1" %*
exit /b %errorlevel%
