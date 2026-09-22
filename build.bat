@echo off
rem Build txt-to-epub.exe (single file, no console) with PyInstaller.
rem Usage: build.bat          -> dist\txt-to-epub.exe
setlocal
cd /d "%~dp0"

python -m PyInstaller --version >nul 2>&1 || python -m pip install pyinstaller
python -m pip install -r requirements.txt

python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name txt-to-epub ^
  --add-data "lang;lang" ^
  --add-data "templates;templates" ^
  --add-data "patterns.json;." ^
  --collect-data tkinterdnd2 ^
  main.py

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)
echo.
echo Done: dist\txt-to-epub.exe
endlocal
