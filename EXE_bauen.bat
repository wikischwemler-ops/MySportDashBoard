@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Baut GarminDashboard.exe - danach braucht ein anderer Rechner weder Python noch uv.
call "%~dp0_umgebung.bat" || ( pause & goto :eof )
echo %RUN% | find "uv" >nul && (
  set "RUN=%RUN:--with garminconnect=--with garminconnect --with pyinstaller%"
) || (
  %RUN% -m pip install --user pyinstaller -r requirements.txt
)
%RUN% -m PyInstaller --noconfirm --onefile --name GarminDashboard --add-data "index.html;." --collect-all garminconnect --collect-all garth garmin_dashboard.py
copy /Y dist\GarminDashboard.exe . >nul && echo. && echo GarminDashboard.exe liegt jetzt in diesem Ordner.
pause
