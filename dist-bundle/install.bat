@echo off
REM ===================================================================
REM  AI Overlay - one-click installer for Windows
REM  Installs the tool, then walks you through entering your API key.
REM ===================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   AI Overlay installer
echo ============================================================
echo.

REM --- 1. Find Python ------------------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [ERROR] Python was not found on this computer.
    echo.
    echo Please install Python 3.11 or newer from:
    echo     https://www.python.org/downloads/
    echo During install, tick "Add Python to PATH", then run this again.
    echo.
    pause
    exit /b 1
)
echo Using Python command: %PY%
%PY% --version
echo.

REM --- 2. Locate the bundled wheel -----------------------------------
set "WHEEL="
for %%f in ("%~dp0*.whl") do set "WHEEL=%%f"
if not defined WHEEL (
    echo [ERROR] No .whl file found next to this installer.
    echo Make sure install.bat and the ai_overlay-*.whl file are in the
    echo same folder.
    echo.
    pause
    exit /b 1
)
echo Found package: !WHEEL!
echo.

REM --- 3. Make sure pipx is available ---------------------------------
echo Ensuring pipx is installed...
%PY% -m pipx --version >nul 2>nul
if errorlevel 1 (
    echo Installing pipx...
    %PY% -m pip install --user pipx
    if errorlevel 1 (
        echo [ERROR] Failed to install pipx.
        pause
        exit /b 1
    )
    %PY% -m pipx ensurepath
)
echo.

REM --- 4. Install the tool with full features -------------------------
echo Installing AI Overlay (this includes screen OCR and voice; it is a
echo large download the first time and may take several minutes)...
echo.
%PY% -m pipx install --force "!WHEEL![full]"
if errorlevel 1 (
    echo [ERROR] Installation failed. See the messages above.
    pause
    exit /b 1
)
echo.
echo Installation complete.
echo.

REM --- 5. Interactive setup (API key) --------------------------------
echo ============================================================
echo   Let's set up your OpenAI API key
echo ============================================================

REM pipx installs the command here; call it by full path since the PATH
REM change from "ensurepath" only applies to NEW terminals.
set "AIEXE=%USERPROFILE%\.local\bin\ai-overlay.exe"
if exist "!AIEXE!" (
    "!AIEXE!" setup
) else (
    REM Fall back to whatever is already on PATH.
    ai-overlay setup
)

echo.
echo ============================================================
echo   All done!
echo ============================================================
echo To start the assistant at any time, double-click:
echo     AI-Overlay.bat
echo or open a NEW terminal and run:
echo     ai-overlay run
echo.
echo (Open a new terminal first so the updated PATH takes effect.)
echo.
pause
endlocal
