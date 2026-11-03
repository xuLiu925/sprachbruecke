@echo off
rem Deploy Sprachbruecke to the phone. Usage: double-click, or run "deploy.bat 192.168.1.23"
rem Put "set PHONE_USER=<your Termux user (whoami)>" in deploy.local.bat to skip the prompt.
cd /d "%~dp0"

if exist deploy.local.bat call "%~dp0deploy.local.bat"
if "%PHONE_USER%"=="" set /p PHONE_USER=Termux user name (run whoami in Termux):
if "%PHONE_USER%"=="" goto :eof

set IP=%1
if "%IP%"=="" set /p IP=Phone IP (e.g. 192.168.1.23):
if "%IP%"=="" goto :eof

echo == Packing...
tar -czf sb.tar.gz app.py alerts.py member_mail.py database.py helpers.py auth.py billing.py email_codes.py feedback.py srs.py vocab.py today.py vocab_seed.py tts.py sentences.py lessons.py custom_lessons.py explain.py dictionary.py form_drills.py grammar.py grammar_seed.py gender_hint.py word_parts.py word_add.py word_store.py lexicon.py noun_quiz.py article_quiz.py plural_quiz.py verb_quiz.py perfekt_quiz.py verb_usage.py verb_sentences.py requirements.txt deploy_phone.sh tunnel.sh boot.sh static content tools/import_wordbook.py tools/backup_db.py tools/watchdog.py data/wordbook.json
if errorlevel 1 goto fail

echo == Uploading (enter phone password if asked)...
scp -P 8022 sb.tar.gz %PHONE_USER%@%IP%:~/
if errorlevel 1 goto fail

rem The dictionary is about 40 MB, so upload it only when it changed. It must arrive before the app restarts.
if not exist data\lexicon.db goto lexicon_done
for %%F in (data\lexicon.db) do set LEXICON_NOW=%%~zF %%~tF
set LEXICON_SENT=
if exist data\.lexicon.sent set /p LEXICON_SENT=<data\.lexicon.sent
if "%LEXICON_NOW%"=="%LEXICON_SENT%" goto lexicon_done
echo == Uploading dictionary...
ssh -p 8022 %PHONE_USER%@%IP% "mkdir -p ~/sprachbruecke/data"
scp -P 8022 data/lexicon.db %PHONE_USER%@%IP%:~/sprachbruecke/data/lexicon.db
if errorlevel 1 goto fail
(echo %LEXICON_NOW%)>data\.lexicon.sent
:lexicon_done

echo == Installing and starting on phone (enter password again if asked)...
ssh -p 8022 %PHONE_USER%@%IP% "mkdir -p ~/sprachbruecke && tar -xzf ~/sb.tar.gz -C ~/sprachbruecke && cd ~/sprachbruecke && sed -i 's/\r$//' deploy_phone.sh tunnel.sh boot.sh && bash deploy_phone.sh"
if errorlevel 1 goto fail

echo.
echo == Done.
pause
goto :eof

:fail
echo.
echo !! Failed. Copy the messages above and send them to Claude.
pause
