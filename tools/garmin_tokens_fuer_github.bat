@echo off
chcp 65001 >nul
rem Packt die Garmin-Tokens (Ordner .garminconnect) in einen Text fuer das GitHub-Secret GARMIN_TOKENS
rem und legt ihn in die Zwischenablage. Die Datei selbst wird nicht gespeichert.
set "TOK=%~1"
if "%TOK%"=="" set "TOK=%USERPROFILE%\.garminconnect"
if not exist "%TOK%\*.json" (
  echo Kein Token-Ordner gefunden: %TOK%
  echo Bitte zuerst einmal Dashboard_starten.bat ausfuehren und bei Garmin anmelden.
  pause & exit /b 1
)
powershell -NoProfile -Command ^
  "$d=@{}; Get-ChildItem -LiteralPath '%TOK%' -Filter *.json | ForEach-Object { $d[$_.Name]=[IO.File]::ReadAllText($_.FullName) };" ^
  "$j=($d | ConvertTo-Json -Compress); $b=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($j)); Set-Clipboard -Value $b;" ^
  "Write-Host ('Fertig: ' + $d.Count + ' Token-Dateien, ' + $b.Length + ' Zeichen in der Zwischenablage.')"
echo.
echo Jetzt in GitHub: Repository ^> Settings ^> Secrets and variables ^> Actions ^> New repository secret
echo   Name:  GARMIN_TOKENS
echo   Wert:  Strg+V
echo.
echo Hinweis: Diese Tokens sind dein Garmin-Zugang. Nirgends sonst einfuegen.
pause
