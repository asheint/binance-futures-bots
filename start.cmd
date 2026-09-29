@echo off
title Trend Bot
cd /d "%~dp0"
echo Starting the dashboard in a separate minimized window...
start "Trend Bot dashboard" /min ".venv\Scripts\python.exe" dashboard.py
timeout /t 4 /nobreak >nul
start "" "http://127.0.0.1:8000"
echo.
echo ================================================================
echo  Trend bot is RUNNING on the account in .env (demo by default).
echo  To stop: close this window or press Ctrl+C.
echo  Open positions keep their stop orders on Binance when stopped.
echo  Also close the minimized "Trend Bot dashboard" window when done.
echo ================================================================
echo.
".venv\Scripts\python.exe" trend_bot.py run
echo.
echo Bot stopped.
pause
