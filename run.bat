@echo off
REM ============================================================
REM  Pixel Parkour - Windows launcher  (pure ASCII, no chcp)
REM  1) find a Python that can import pygame
REM  2) install pygame-ce if none of them has it
REM  3) launch the game
REM
REM  ASCII only on purpose: cmd.exe reads this file with the
REM  system code page (GBK on Chinese Windows). UTF-8 Chinese
REM  here would be mis-decoded and shred the command lines.
REM ============================================================
setlocal
cd /d "%~dp0"

REM --- 1) probe every interpreter, prefer the one that really has pygame ---
set "PY="

python -c "import pygame" >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto launch

py -3 -c "import pygame" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto launch

py -c "import pygame" >nul 2>nul
if not errorlevel 1 set "PY=py"
if defined PY goto launch

REM --- 2) nothing has pygame: pick an interpreter and install it ---
where py >nul 2>nul
if not errorlevel 1 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python 3 not found. Please install Python 3.9+ and add it to PATH.
        pause
        exit /b 1
    )
    set "PY=python"
)

echo [INFO] pygame not found, installing pygame-ce ...
%PY% -m pip install --upgrade pip >nul 2>nul
%PY% -m pip install pygame-ce
if errorlevel 1 (
    echo [ERROR] failed to install pygame-ce. Run manually: pip install pygame-ce
    pause
    exit /b 1
)

:launch
%PY% game.py %*
if errorlevel 1 (
    echo.
    echo [ERROR] game exited with an error. Press any key to close.
    pause >nul
)
endlocal
