@echo off
chcp 65001 >nul
rem Kopiert den Workflow an die Stelle, an der GitHub ihn erwartet: .github\workflows\garmin-sync.yml
cd /d "%~dp0.."
if not exist ".github\workflows" mkdir ".github\workflows"
copy /y "tools\garmin-sync.yml" ".github\workflows\garmin-sync.yml" >nul && echo Workflow liegt jetzt in .github\workflows\garmin-sync.yml
echo Danach committen und pushen, z. B.:
echo   git add -A ^&^& git commit -m "Garmin Sync Workflow" ^&^& git push
pause
