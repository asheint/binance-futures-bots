@echo off
title Copy Bot (shadow)
cd /d "%~dp0"
netstat -ano | findstr /r /c:"127.0.0.1:8000 .*LISTENING" >nul
if errorlevel 1 (
  echo Starting the dashboard in a separate minimized window...
  start "Bot dashboard" /min ".venv\Scripts\python.exe" dashboard.py
  timeout /t 4 /nobreak >nul
)
start "" "http://127.0.0.1:8000/copy"
echo ================================================================
echo  Copy bot: ranks Binance lead traders by their real history and
echo  copies the best ones ON PAPER. It places no orders at all.
echo  First scout takes a few minutes. To stop: close this window or Ctrl+C.
echo  Copy bot's page: http://127.0.0.1:8000/copy   All bots: http://127.0.0.1:8000
echo ================================================================
echo.
".venv\Scripts\python.exe" copy_bot.py run
echo.
echo Copy bot stopped.
pause
