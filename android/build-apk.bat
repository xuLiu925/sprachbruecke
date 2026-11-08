@echo off
rem Build the Android app locally (low priority, one worker) and copy it to static\tongde.apk;
rem deploy.bat then uploads it to the server with the rest of static\.
rem Needs: D:\android-sdk (SDK + gradle-8.7), Java 17, android\release.jks + android\keystore.properties
setlocal
if "%JAVA_HOME%"=="" set "JAVA_HOME=D:\java\java-17.0.1"
cd /d "%~dp0"
start "" /low /wait /b cmd /c "D:\android-sdk\gradle-8.7\bin\gradle.bat --no-daemon --max-workers=1 -q assembleRelease"
if not exist app\build\outputs\apk\release\app-release.apk (echo == BUILD FAILED & exit /b 1)
copy /y app\build\outputs\apk\release\app-release.apk ..\static\tongde.apk >nul
rem Version info for the in-app update prompt: static\tongde.json, read by /api/app/version
..\.venv\Scripts\python.exe ..\tools\apk_version.py || (echo == VERSION FILE FAILED & exit /b 1)
echo == OK: static\tongde.apk
