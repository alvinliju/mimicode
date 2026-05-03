@echo off
REM mimicode - Easy launcher for mimicode TUI (Windows version)
REM Automatically sets up environment and runs the application

setlocal enabledelayedexpansion

cd /d "%~dp0"

REM Check for Python 3
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [31m ERROR: Python 3 is required but not found.[0m
    echo Please install Python 3.8 or later from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Check for ripgrep
where rg >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [31m ERROR: ripgrep is required but not found.[0m
    echo.
    echo Install it using one of these methods:
    echo   Chocolatey: choco install ripgrep
    echo   Scoop:      scoop install ripgrep
    echo   Or download from: https://github.com/BurntSushi/ripgrep/releases
    echo.
    pause
    exit /b 1
)

REM Check for API key
if "%ANTHROPIC_API_KEY%"=="" (
    echo [33m WARNING: ANTHROPIC_API_KEY environment variable is not set.[0m
    echo.
    echo To set your API key permanently, run:
    echo   setx ANTHROPIC_API_KEY "your-key-here"
    echo.
    echo Or set it for this session:
    echo   set ANTHROPIC_API_KEY=your-key-here
    echo.
    set /p CONTINUE="Continue anyway? (y/N): "
    if /i not "!CONTINUE!"=="y" exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist ".venv\" (
    echo [34m Creating Python virtual environment...[0m
    python -m venv .venv
    echo [32m Virtual environment created[0m
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Check if dependencies are installed
python -c "import anthropic" >nul 2>nul
if %ERRORLEVEL% NEQ 0 set NEEDS_INSTALL=1

python -c "import textual" >nul 2>nul
if %ERRORLEVEL% NEQ 0 set NEEDS_INSTALL=1

REM Install/update dependencies if needed
if defined NEEDS_INSTALL (
    echo [34m Installing Python dependencies...[0m
    python -m pip install -q --upgrade pip
    python -m pip install -q -r requirements.txt
    echo [32m Dependencies installed[0m
)

REM Run mimicode TUI
echo [34m Starting mimicode TUI...[0m
echo.
python agent.py --tui %*
