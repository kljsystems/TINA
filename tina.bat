@echo off
REM Launch TINA backend + frontend from one command. Usage:  .\tina
cd /d "%~dp0"
".venv\Scripts\python.exe" tina.py %*
