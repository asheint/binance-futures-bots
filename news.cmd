@echo off
title News Bot (demo)
cd /d "%~dp0"
netstat -ano | findstr /r /c:"127.0.0.1:8000 .*LISTENING" >nul
if errorlevel 1 (
  echo Starting the dashboard in a separate minimized window...
  start "Bot dashboard" /min ".venv\Scripts\python.exe" dashboard.py
  timeout /t 4 /nobreak >nul
)
start "" "http://127.0.0.1:8000/news"
echo ================================================================
echo  News bot: shorts coins right after Binance announces a delisting.
echo  DEMO account only. Checks the news every 2 seconds.
echo  To stop: close this window or Ctrl+C. Open shorts keep their stop-loss.
echo  Scoop's page: http://127.0.0.1:8000/news
echo ================================================================
echo.
".venv\Scripts\python.exe" news_bot.py run
echo.
echo News bot stopped.
pause
