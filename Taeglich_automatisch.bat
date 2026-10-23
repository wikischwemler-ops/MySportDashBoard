@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Legt eine Windows-Aufgabe an, die die Daten jeden Morgen um 06:40 aktualisiert.
schtasks /Create /F /SC DAILY /ST 06:40 /TN "Garmin Dashboard Update" /TR "\"%~dp0Nur_aktualisieren.bat\""
echo.
echo Fertig. Entfernen mit:  schtasks /Delete /TN "Garmin Dashboard Update" /F
pause
