@echo off
rem Build de l'app portable nextevents (Windows)
rem Prerequis : Python 3.11+ installe, git clone --recurse-submodules
setlocal
cd /d "%~dp0"

git submodule update --init
if errorlevel 1 goto err

python -m pip install -r requirements-desktop.txt
if errorlevel 1 goto err

rem Chromium embarque (hors GPO/proxy du navigateur gere) ~170 Mo
set PLAYWRIGHT_BROWSERS_PATH=ms-playwright
python -m playwright install chromium
if errorlevel 1 goto err

pyinstaller --clean --noconfirm app.spec
if errorlevel 1 goto err

echo.
echo OK — dossier portable : dist\nextevents\
echo Copiez-le tel quel ; lancer dist\nextevents\nextevents.exe
echo (les donnees sont ecrites dans dist\nextevents\data\)
goto end
:err
echo BUILD ECHOUE
:end
endlocal
