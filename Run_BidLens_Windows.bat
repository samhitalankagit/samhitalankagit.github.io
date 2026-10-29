@echo off
setlocal
cd /d "%~dp0"
echo ==========================================
echo BidLens - Starting the Streamlit app
echo ==========================================
where py >nul 2>nul
if %errorlevel%==0 (
  set PYTHON=py
) else (
  set PYTHON=python
)
if not exist .venv\Scripts\python.exe (
  echo Creating a local Python environment...
  %PYTHON% -m venv .venv
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
echo BidLens could not start. Please check that Python 3.11 or 3.12 is installed and internet is available for package installation.
pause
:end
endlocal
