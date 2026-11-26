@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set FRONTIER_PORT=8765

if not exist ".venv\Scripts\python.exe" (
    echo The project Python environment is missing.
    echo From this folder run: python -m venv .venv
    echo Then run: .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo Starting Frontier Command at http://127.0.0.1:8765
echo Keep this window open while playing. Press Ctrl+C to stop.
"%~dp0.venv\Scripts\python.exe" "%~dp0visualizer.py"

echo.
echo The server stopped or could not start. Read the error above.
pause
