@echo off
title Crazy Bot (demo)
cd /d "%~dp0"
netstat -ano | findstr /r /c:"127.0.0.1:8000 .*LISTENING" >nul
if errorlevel 1 (
  echo Starting the dashboard in a separate minimized window...
  start "Bot dashboard" /min ".venv\Scripts\python.exe" dashboard.py
  timeout /t 4 /nobreak >nul
)
start "" "http://127.0.0.1:8000/bot"
echo ================================================================
echo  Crazy bot: longs + shorts on every liquid coin, DEMO account only.
echo  Starts in MANUAL mode: press Scan now on the bot page (or switch to Auto). Ctrl+C to stop.
echo  Open trades keep their TP/SL orders on Binance when stopped.
echo  Bot page: http://127.0.0.1:8000/bot   Dashboard: http://127.0.0.1:8000
echo ================================================================
echo.
".venv\Scripts\python.exe" crazy_bot.py run %*
echo.
echo Bot stopped.
pause
