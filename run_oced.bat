@echo off
rem OCED - Olds College Extract Data: start the app (it opens in the browser at http://localhost:8502).
rem The private environment .venv of install_oced.bat is used when it exists, else the Python on the PATH.
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" -m streamlit run app\oced.py --server.port 8502
pause
