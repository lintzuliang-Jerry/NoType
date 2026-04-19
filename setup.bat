@echo off
pushd "%~dp0"
setlocal

if exist .venv (
    echo [info] .venv already exists, skipping creation
) else (
    echo [info] Creating virtual environment...
    python -m venv .venv || goto :error
)

echo [info] Installing dependencies...
call .venv\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip || goto :error
pip install -r requirements.txt || goto :error

echo.
echo [done] Setup complete. Run run.bat to start.
pause
popd
exit /b 0

:error
echo.
echo [error] Setup failed. See messages above.
pause
popd
exit /b 1
