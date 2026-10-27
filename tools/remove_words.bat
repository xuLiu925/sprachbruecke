@echo off
rem Remove words from the wordbook for good. Usage: double-click, or run "tools\remove_words.bat ahh hmm"
chcp 65001 >nul
cd /d "%~dp0.."
set PY=python
if exist .venv\Scripts\python.exe set PY=.venv\Scripts\python.exe
%PY% tools\remove_words.py %*
pause
