@echo off
chcp 65001 >nul
title Garmin Dashboard
cd /d "%~dp0"
if exist "GarminDashboard.exe" ( "GarminDashboard.exe" & goto :eof )
call "%~dp0_umgebung.bat" || ( pause & goto :eof )
%RUN% garmin_dashboard.py
pause
