@echo off
setlocal
cd /d "%~dp0"
echo ==========================================
echo BidLens - Starting the Streamlit app
echo ==========================================
if not exist .venv\Scripts\python.exe (
  echo Creating a local Python environment...
  where py >nul 2>nul
  if %errorlevel%==0 (
    py -3.12 -m venv .venv 2>nul
    if errorlevel 1 py -3.11 -m venv .venv 2>nul
    if errorlevel 1 py -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 goto error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto error
python -m streamlit run app.py
if errorlevel 1 goto error
goto end
:error
echo.
echo BidLens could not start. Check that Python 3.11, 3.12, or a compatible newer version is installed and internet access is available for package installation.
pause
:end
endlocal
