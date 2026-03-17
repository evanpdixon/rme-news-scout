@echo off
REM RME News Scout - Register daily scheduled task
REM Right-click this file and select "Run as administrator"

echo.
echo  RME News Scout - Task Scheduler Setup
echo  ======================================
echo.

schtasks /create /tn "RME News Scout" /xml "%~dp0RMENewsScout.xml" /f

if %errorlevel%==0 (
    echo.
    echo  Task created! RME News Scout will run daily at 6:00 AM.
    echo  If the computer is asleep, it will run on next wake/unlock.
    echo.
    echo  To verify:  schtasks /query /tn "RME News Scout"
    echo  To run now: schtasks /run /tn "RME News Scout"
    echo  To delete:  schtasks /delete /tn "RME News Scout" /f
) else (
    echo.
    echo  ERROR: Could not create task. Make sure you ran this as Administrator.
)

echo.
pause
