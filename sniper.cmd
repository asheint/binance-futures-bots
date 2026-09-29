@echo off
title Sniper Bot (demo)
cd /d "%~dp0"
netstat -ano | findstr /r /c:"127.0.0.1:8000 .*LISTENING" >nul
if errorlevel 1 (
  echo Starting the dashboard in a separate minimized window...
  start "Bot dashboard" /min ".venv\Scripts\python.exe" dashboard.py
  timeout /t 4 /nobreak >nul
)
start "" "http://127.0.0.1:8000/sniper"
echo ================================================================
echo  Sniper bot: trend + key level + closed trigger candle. DEMO only.
echo  Draws its lines every 15 minutes and fires only when price reaches them.
echo  To stop: close this window or Ctrl+C. Open trades keep their stop and target.
echo  Sniper's page: http://127.0.0.1:8000/sniper
echo ================================================================
echo.
".venv\Scripts\python.exe" sniper_bot.py run
echo.
echo Sniper bot stopped.
pause
