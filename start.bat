@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "PROJECT_ROOT=%~dp0"
set "POWERSHELL_SCRIPT=%PROJECT_ROOT%start.ps1"

if not exist "%POWERSHELL_SCRIPT%" (
    echo [RAG] ERROR: Internal startup engine not found:
    echo       %POWERSHELL_SCRIPT%
    exit /b 1
)

where powershell.exe >nul 2>&1
if errorlevel 1 (
    echo [RAG] ERROR: powershell.exe was not found.
    exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%POWERSHELL_SCRIPT%" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [RAG] Startup failed with exit code %EXIT_CODE%.
)

exit /b %EXIT_CODE%
