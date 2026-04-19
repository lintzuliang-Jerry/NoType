@echo off
pushd "%~dp0"
call .venv\Scripts\activate.bat || (
    echo [error] venv not found. Run setup.bat first.
    pause
    exit /b 1
)
python -m src.main
popd
