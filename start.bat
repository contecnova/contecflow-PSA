@echo off
setlocal
cd /d "%~dp0"

if "%~1"=="" (
    call ".\setup.bat" start
) else (
    call ".\setup.bat" %*
)

exit /b %ERRORLEVEL%
