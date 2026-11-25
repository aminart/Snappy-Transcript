@echo off
setlocal
rem Lance Snappy Transcript et ouvre le navigateur (http://127.0.0.1:8110).
rem Gardez cette fenetre ouverte pendant l'essai ; fermez-la pour arreter l'application.
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo Snappy Transcript n'est pas encore installe : lancez d'abord install.bat.
    pause
    exit /b 1
)
if not exist frontend\dist\index.html (
    echo Interface absente, fabrication...
    pushd frontend
    call npm run build
    if errorlevel 1 ( popd & echo Echec : relancez install.bat. & pause & exit /b 1 )
    popd
)

.venv\Scripts\python.exe backend\launcher.py
if errorlevel 1 pause
