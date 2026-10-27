@echo off
rem Deploy Sprachbruecke to the phone. Usage: double-click, or run "deploy.bat 192.168.1.23"
rem Put "set PHONE_USER=<your Termux user (whoami)>" in deploy.local.bat to skip the prompt.
cd /d "%~dp0"

if exist deploy.local.bat call deploy.local.bat
if "%PHONE_USER%"=="" set /p PHONE_USER=Termux user name (run whoami in Termux):
if "%PHONE_USER%"=="" goto :eof

set IP=%1
if "%IP%"=="" set /p IP=Phone IP (e.g. 192.168.1.23):
if "%IP%"=="" goto :eof

echo == Packing...
tar -czf sb.tar.gz app.py database.py helpers.py auth.py srs.py vocab.py vocab_seed.py tts.py requirements.txt deploy_phone.sh static tools/import_wordbook.py data/wordbook.json
if errorlevel 1 goto fail

echo == Uploading (enter phone password if asked)...
scp -P 8022 sb.tar.gz %PHONE_USER%@%IP%:~/
if errorlevel 1 goto fail

echo == Installing and starting on phone (enter password again if asked)...
ssh -p 8022 %PHONE_USER%@%IP% "mkdir -p ~/sprachbruecke && tar -xzf ~/sb.tar.gz -C ~/sprachbruecke && cd ~/sprachbruecke && sed -i 's/\r$//' deploy_phone.sh && bash deploy_phone.sh"
if errorlevel 1 goto fail

echo.
echo == Done.
pause
goto :eof

:fail
echo.
echo !! Failed. Copy the messages above and send them to Claude.
pause
