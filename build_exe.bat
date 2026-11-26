@echo off
setlocal
rem Fabrique dist\<NomDuProgramme>.exe. Prerequis : Python 3.11+ et Node.js 20+ dans le PATH.
rem   build_exe.bat              exe avec transcription faster-whisper (CPU, et GPU si les DLL sont deja installees)
rem   build_exe.bat gpu          + runtimes CUDA (cuBLAS, cuDNN) : exe beaucoup plus gros
rem                              (hors ligne : fichiers nvidia_*.whl dans le dossier wheels)
rem   build_exe.bat diarisation  + pyannote et PyTorch (diarisation des locuteurs) : exe tres gros
rem   Les options se combinent : build_exe.bat gpu diarisation

if not exist .venv\Scripts\python.exe (
    python -m venv .venv
    if errorlevel 1 goto :erreur
)
call .venv\Scripts\activate.bat

echo [1/3] Dependances Python...
python -m pip install --upgrade pip
pip install -r backend\requirements-stt.txt pyinstaller
if errorlevel 1 goto :erreur
for %%o in (%*) do (
    if /I "%%o"=="gpu" if exist "wheels\nvidia_cu*.whl" (pip install --no-index --find-links wheels nvidia-cublas-cu12 nvidia-cudnn-cu12) else (pip install -r backend\requirements-gpu.txt)
    if /I "%%o"=="diarisation" pip install -r backend\requirements-diarization.txt
)
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
