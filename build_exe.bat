@echo off
rem Build TW1QuestCreator.exe with PyInstaller (one file, no console).
rem Needs Python with PyInstaller; on Marco's PC that is Python 3.13.
rem Result: dist\TW1QuestCreator.exe
cd /d "%~dp0"
py -3.13 -m PyInstaller --noconfirm --clean build_exe.spec
if errorlevel 1 (
    echo BUILD FAILED
    exit /b 1
)
echo.
echo Built: %~dp0dist\TW1QuestCreator.exe
