@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "GarminDashboard.exe" ( "GarminDashboard.exe" --update-only & goto :eof )
call "%~dp0_umgebung.bat" || goto :eof
%RUN% garmin_dashboard.py --update-only
