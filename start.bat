@echo off
cd /d %~dp0
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
if errorlevel 1 exit /b 1
.venv\Scripts\python app.py
