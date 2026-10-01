@echo off
REM ===================================================================
REM  AI Overlay - launcher
REM  Double-click to start the floating AI assistant.
REM ===================================================================
setlocal

set "AIEXE=%USERPROFILE%\.local\bin\ai-overlay.exe"

if exist "%AIEXE%" (
    "%AIEXE%" run
) else (
    REM Fall back to the command on PATH (works in a fresh terminal).
    ai-overlay run
)

if errorlevel 1 (
    echo.
    echo Could not start AI Overlay.
    echo If you have not installed it yet, run install.bat first.
    echo.
    pause
)
endlocal
