@echo off
powershell -Command "Start-Process cmd -ArgumentList '/c pushd \"%~dp0\" && call .venv\Scripts\activate.bat && python -m src.main' -Verb RunAs -WindowStyle Hidden"
