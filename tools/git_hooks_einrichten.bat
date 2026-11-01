@echo off
rem Aktiviert die Git-Hooks aus .githooks (neue Branches nur zweistufig als xxx/yyy). Einmal je Klon ausfuehren.
cd /d "%~dp0.."
git config core.hooksPath .githooks || (echo Git nicht gefunden. & pause & exit /b 1)
echo Git-Hooks aktiv: neue Branches nur noch zweistufig, z. B. fix/garmin-tokens oder %USERNAME%/hf-zonen.
echo Regeln: .githooks\branch-rules.json
pause
