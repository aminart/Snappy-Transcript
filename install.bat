@echo off
setlocal
rem Installe Snappy Transcript pour le tester sur ce poste (une seule fois, puis start.bat).
rem   install.bat                               installation normale
rem   install.bat "C:\...\companyCA.crt"        derriere le proxy de l'entreprise (certificat)
rem Prerequis : Python 3.11+ et Node.js 20+ dans le PATH.
cd /d "%~dp0"

set "CERT=%~1"
set "PIP_CERT_OPT="
if not "%CERT%"=="" (
    if not exist "%CERT%" (
        echo Certificat introuvable : %CERT%
        goto :erreur
    )
    set "PIP_CERT_OPT=--cert "%CERT%""
    set "NODE_EXTRA_CA_CERTS=%CERT%"
)

echo.
echo === Snappy Transcript : installation ===
echo.

where python >nul 2>nul || (echo Python est introuvable. Installez Python 3.11 ou plus, en cochant "Add python.exe to PATH". & goto :erreur)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" || (echo Python 3.11 ou plus est necessaire. & python --version & goto :erreur)
where npm >nul 2>nul || (echo Node.js est introuvable. Installez Node.js 20 ou plus. & goto :erreur)

echo [1/3] Environnement Python (.venv)...
if not exist .venv\Scripts\python.exe (
    python -m venv .venv
    if errorlevel 1 goto :erreur
)

echo [2/3] Dependances Python (transcription comprise, quelques minutes la premiere fois)...
.venv\Scripts\python.exe -m pip install --upgrade pip %PIP_CERT_OPT% >nul
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt %PIP_CERT_OPT%
if errorlevel 1 goto :erreur

echo [3/3] Interface...
pushd frontend
call npm ci
if errorlevel 1 ( popd & goto :erreur )
call npm run build
if errorlevel 1 ( popd & goto :erreur )
popd

echo.
echo Installation terminee. Lancez start.bat pour ouvrir Snappy Transcript.
echo Sans modele de transcription : Reglages avances, Moteur "Simulation".
echo.
pause
exit /b 0

:erreur
echo.
echo L'installation n'a pas abouti : lisez le message ci-dessus.
pause
exit /b 1
