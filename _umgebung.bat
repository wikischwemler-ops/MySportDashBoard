@echo off
rem Sucht ein lauffaehiges Python. Reihenfolge: py, python, uv (laedt Python selbst), sonst uv installieren.
set "RUN="
py -3 -c "import sys" >nul 2>nul && ( set "RUN=py -3" & goto :pkg )
python -c "import sys" >nul 2>nul && ( set "RUN=python" & goto :pkg )
call :finduv
if defined UV goto :uvrun
echo Kein Python gefunden. Installiere einmalig "uv" (kleines Werkzeug, laedt Python automatisch, keine Adminrechte) ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
call :finduv
if not defined UV (
  echo.
  echo uv konnte nicht installiert werden. Bitte Python von https://www.python.org/downloads/ installieren
  echo und dabei "Add python.exe to PATH" anhaken. Danach erneut starten.
  exit /b 1
)
:uvrun
set "RUN="%UV%" run --python 3.12 --with garminconnect python"
exit /b 0
:pkg
%RUN% -c "import garminconnect" >nul 2>nul && exit /b 0
echo Installiere Paket garminconnect ...
%RUN% -m pip install --user -r requirements.txt
exit /b 0
:finduv
set "UV="
for %%X in (uv.exe) do if not "%%~$PATH:X"=="" set "UV=%%~$PATH:X"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "UV=%USERPROFILE%\.cargo\bin\uv.exe"
if not defined UV if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" set "UV=%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe"
exit /b 0
