@echo off
rem Aktiviert die Git-Hooks aus .githooks (neue Branches nur als Windows-Benutzer/name). Einmal je Klon ausfuehren.
cd /d "%~dp0.."
git config core.hooksPath .githooks || (echo Git nicht gefunden. & pause & exit /b 1)
echo Git-Hooks aktiv: neue Branches nur noch als %USERNAME%/name (klein geschrieben).
echo Regeln: .githooks\branch-rules.json
pause
