@echo off
setlocal
rem Fabrique dist\<NomDuProgramme>.exe. Prerequis : Python 3.11+ et Node.js 20+ dans le PATH.
rem   build_exe.bat              exe avec transcription faster-whisper et identification des intervenants
rem                              (pyannote et PyTorch : exe tres gros ; le modele est fourni par Studio Dock)
rem   build_exe.bat gpu          + runtimes CUDA (cuBLAS, cuDNN) : exe beaucoup plus gros
rem                              (hors ligne : fichiers nvidia_*.whl dans le dossier wheels)
rem   build_exe.bat leger        sans l'identification des intervenants (exe beaucoup plus petit)
rem   Les options se combinent : build_exe.bat gpu leger

if not exist .venv\Scripts\python.exe (
    python -m venv .venv
    if errorlevel 1 goto :erreur
)
call .venv\Scripts\activate.bat
set "AVEC_INTERVENANTS=1"
for %%o in (%*) do if /I "%%o"=="leger" set "AVEC_INTERVENANTS="

echo [1/3] Dependances Python...
python -m pip install --upgrade pip
pip install --no-index --find-links backend\vendor comtypes psutil
pip install -r backend\requirements-stt.txt pyinstaller
if errorlevel 1 goto :erreur
for %%o in (%*) do (
    if /I "%%o"=="gpu" if exist "wheels\nvidia_cu*.whl" (pip install --no-index --find-links wheels nvidia-cublas-cu12 nvidia-cudnn-cu12) else (pip install -r backend\requirements-gpu.txt)
    if /I "%%o"=="diarisation" set "AVEC_INTERVENANTS=1"
)
if errorlevel 1 goto :erreur
if defined AVEC_INTERVENANTS pip install -r backend\requirements-diarization.txt
if errorlevel 1 goto :erreur

echo [2/3] Interface...
copy /Y icone\app.svg frontend\public\icone.svg >nul
pushd frontend
call npm ci
if errorlevel 1 ( popd & goto :erreur )
call npm run build
if errorlevel 1 ( popd & goto :erreur )
popd

echo [3/3] Executable...
pyinstaller --noconfirm app.spec
if errorlevel 1 goto :erreur

echo.
echo Termine : l'exe est dans le dossier dist.
pause
exit /b 0

:erreur
echo.
echo Une erreur est survenue pendant la fabrication.
pause
exit /b 1
