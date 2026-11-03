@echo off
rem Copy the server's daily backups to this PC (backups\server\). Usage: double-click, or "backup.bat 192.168.1.23"
rem Only files not already here are downloaded. Keeps the newest 30 on the PC.
rem Put "set BACKUP_IP=<server's Tailscale IP>" in deploy.local.bat to skip the prompt (the daily scheduled task needs it).
cd /d "%~dp0"

if exist deploy.local.bat call "%~dp0deploy.local.bat"
if "%PHONE_USER%"=="" set /p PHONE_USER=Termux user name (run whoami in Termux):
if "%PHONE_USER%"=="" goto :eof

set IP=%1
if "%IP%"=="" set IP=%BACKUP_IP%
if "%IP%"=="" set /p IP=Phone IP (e.g. 192.168.1.23):
if "%IP%"=="" goto :eof

rem Run by the scheduled task (NOPAUSE=1): never wait for a password prompt
set SSHOPT=-o ConnectTimeout=20
if not "%NOPAUSE%"=="" set SSHOPT=%SSHOPT% -o BatchMode=yes

if not exist backups\server mkdir backups\server
echo == Listing backups on the server...
ssh %SSHOPT% -p 8022 %PHONE_USER%@%IP% "cd ~/sprachbruecke && python tools/backup_db.py daily && ls backups/daily" > backups\server\.list
if errorlevel 1 goto fail

for /f "usebackq" %%F in ("backups\server\.list") do (
    if "%%~xF"==".gz" if not exist "backups\server\%%F" (
        echo == Downloading %%F
        scp %SSHOPT% -P 8022 %PHONE_USER%@%IP%:~/sprachbruecke/backups/daily/%%F backups\server\%%F
        if errorlevel 1 goto fail
    )
)
del backups\server\.list

rem Keep the newest 30 (names contain the date, so sorting by name = by date)
for /f "skip=30 delims=" %%F in ('dir /b /o-n backups\server\vocab.*.db.gz') do del "backups\server\%%F"

echo.
echo == Done. Backups are in %~dp0backups\server
dir /b /o-n backups\server
if "%NOPAUSE%"=="" pause
goto :eof

:fail
echo.
echo !! Failed. Copy the messages above and send them to Claude.
if "%NOPAUSE%"=="" pause
