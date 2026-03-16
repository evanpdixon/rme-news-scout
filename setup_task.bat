@echo off
REM RME News Scout - Register to run on login
REM Right-click this file and select "Run as administrator"

echo.
echo  RME News Scout - Task Scheduler Setup
echo  ======================================
echo.

schtasks /create /tn "RME News Scout" /tr "python C:\Claude\rme_news_scout\main.py" /sc onlogon /rl LIMITED /f

if %errorlevel%==0 (
    echo.
    echo  Task created! RME News Scout will run each time you log in.
    echo.
    echo  To verify:  schtasks /query /tn "RME News Scout"
    echo  To delete:  schtasks /delete /tn "RME News Scout" /f
) else (
    echo.
    echo  ERROR: Could not create task. Make sure you ran this as Administrator.
)

echo.
pause
