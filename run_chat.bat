@echo off
title AI Screenshot Assistant Ultimate
color 0B
echo ==============================================================
echo    Start AI Screenshot Assistant Ultimate
echo ==============================================================

:: Проверка, запущен ли уже процесс
tasklist /FI "IMAGENAME eq chat_gui_ultimate.exe" | find /I "chat_gui_ultimate.exe" >nul
if %errorlevel%==0 (
    echo The app is already running. A second instance will not be opened.
    timeout /t 3 >nul
    exit /b
)

:: Проверка существования exe
if exist "%~dp0chat_gui_ultimate.exe" (
    echo ✅ Запуск программы...
    start "" "%~dp0chat_gui_ultimate.exe"
) else (
    echo chat_gui_ultimate.exe was not found in the current folder:
    echo    %~dp0
)

timeout /t 2 >nul
exit /b
