@echo off
setlocal
rem Installe Snappy Transcript pour le tester sur ce poste (une seule fois, puis start.bat).
rem   install.bat                               installation normale
rem   install.bat intervenants                  + identification des intervenants (PyTorch, pyannote : plus de 1 Go)
rem   install.bat gpu                           + calcul sur carte graphique NVIDIA (cuBLAS et cuDNN, environ 1 Go)
rem        sans Internet : deposez d'abord les fichiers nvidia_cublas_cu12-*.whl et nvidia_cudnn_cu12-*.whl
rem        dans le dossier "wheels" a cote de ce fichier
rem   install.bat "C:\...\companyCA.crt"        derriere le proxy de l'entreprise (certificat)
rem Les options se combinent : install.bat gpu intervenants "C:\...\companyCA.crt"
rem Prerequis : Python 3.11+ et Node.js 20+ dans le PATH.
cd /d "%~dp0"

set "CERT="
set "AVEC_INTERVENANTS="
set "AVEC_GPU="
for %%A in (%*) do (
    if /I "%%~A"=="intervenants" (set "AVEC_INTERVENANTS=1") else if /I "%%~A"=="gpu" (set "AVEC_GPU=1") else set "CERT=%%~A"
)
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
rem comtypes et psutil (son d'une application) sont fournis avec le projet : rien a telecharger pour eux,
rem meme si le miroir ou le proxy de l'entreprise ne les propose pas.
.venv\Scripts\python.exe -m pip install --no-index --find-links backend\vendor comtypes psutil >nul 2>nul
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt %PIP_CERT_OPT%
if errorlevel 1 goto :erreur
if defined AVEC_INTERVENANTS call :intervenants
if errorlevel 1 goto :erreur
if defined AVEC_GPU call :gpu
if errorlevel 1 goto :erreur

echo [3/3] Interface...
pushd frontend
call npm ci
if errorlevel 1 (
    popd
    echo.
    echo Si npm parle de EPERM : fermez les fenetres start.bat / start_dev.bat et VS Code, puis relancez.
    echo Si npm parle de ENOTFOUND ou de proxy : le registre npm n'est pas joignable depuis ce poste.
    goto :erreur
)
call npm run build
if errorlevel 1 ( popd & goto :erreur )
popd

echo.
echo Installation terminee. Lancez start.bat pour ouvrir Snappy Transcript.
echo Sans modele de transcription : Reglages avances, Moteur "Simulation".
if not defined AVEC_INTERVENANTS echo Pour identifier les intervenants : install.bat intervenants
if not defined AVEC_GPU echo Avec une carte graphique NVIDIA : install.bat gpu
echo.
pause
exit /b 0

:intervenants
echo [2b] Identification des intervenants : PyTorch et pyannote, plus de 1 Go, plusieurs minutes...
.venv\Scripts\python.exe -m pip install -r backend\requirements-diarization.txt %PIP_CERT_OPT%
exit /b %errorlevel%

:gpu
rem Les fichiers deposes dans "wheels" sont utilises en priorite (poste sans acces a Internet) ;
rem sinon les memes paquets sont telecharges (versions validees de backend\requirements-gpu.txt).
if exist "wheels\nvidia_cu*.whl" (
    echo [2c] Carte graphique NVIDIA : installation depuis le dossier wheels...
    .venv\Scripts\python.exe -m pip install --no-index --find-links wheels nvidia-cublas-cu12 nvidia-cudnn-cu12
) else (
    echo [2c] Carte graphique NVIDIA : telechargement de cuBLAS et cuDNN, environ 1 Go...
    .venv\Scripts\python.exe -m pip install -r backend\requirements-gpu.txt %PIP_CERT_OPT%
)
if errorlevel 1 (
    echo Les fichiers CUDA ne se sont pas installes. Hors ligne, il faut les deux fichiers .whl :
    echo nvidia_cublas_cu12-...-win_amd64.whl et nvidia_cudnn_cu12-...-win_amd64.whl, dans le dossier wheels.
    exit /b 1
)
echo      Verification de la carte graphique...
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'backend'); from snappy.transcription.cuda_runtime import prepare_cuda_runtime as p; s = p(); print('      ' + (s.message or s.detail))"
exit /b 0

:erreur
echo.
echo L'installation n'a pas abouti : lisez le message ci-dessus.
pause
exit /b 1
