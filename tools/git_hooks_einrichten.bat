@echo off
rem Aktiviert die Git-Hooks aus .githooks (Branch-Namen nur als typ/name). Einmal je Klon ausfuehren.
cd /d "%~dp0.."
git config core.hooksPath .githooks || (echo Git nicht gefunden. & pause & exit /b 1)
echo Git-Hooks aktiv: Branch-Namen nur noch als typ/name, z. B. fix/garmin-tokens.
echo Regeln und erlaubte Typen: .githooks\branch-rules.json
pause
