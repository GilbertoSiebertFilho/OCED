@echo off
rem OCED - Olds College Extract Data: update this folder to the newest version on GitHub (branch main).
rem Downloads https://github.com/GilbertoSiebertFilho/OCED/archive/refs/heads/main.zip, moves the current app,
rem engine, docs, assets, .streamlit and tests folders (and the root files README.md, INSTALAR.txt,
rem requirements.txt, constraints.txt, run_oced.bat, install_oced.bat) to _backup\<date-time>, puts the new ones in
rem their place and checks that the code compiles; on any failure the previous version is put back. The tests come
rem with the version they test (python -m pytest -q tests in this folder). Never touched: the work folder
rem (workspace), the Python environment (.venv) and this file itself: when the new version has another
rem updater it is saved beside it as atualizar_oced.new.bat (a running .bat cannot replace itself), with a message.
rem Close the app (its black window) before running this. Messages in Portuguese without accents (any code page).
setlocal EnableExtensions
cd /d "%~dp0"
set "URL=https://github.com/GilbertoSiebertFilho/OCED/archive/refs/heads/main.zip"
set "TMPZIP=%TEMP%\oced_main.zip"
set "TMPDIR=%TEMP%\oced_update"
set "DIRS=app engine docs assets .streamlit tests"
set "FILES=README.md INSTALAR.txt requirements.txt constraints.txt run_oced.bat install_oced.bat"
set "BAK="
echo.
echo  OCED - atualizacao a partir do GitHub, versao main
echo  Pasta: %CD%
echo.
echo  Feche a janela preta do app antes de continuar. A pasta de trabalho (workspace) nao e mexida.
echo.
pause

if not exist "app\oced.py" goto notoced
rem the app listens on port 8502 while it is open (a listening socket: remote address 0.0.0.0:0 or [::]:0)
netstat -ano | findstr /r /c:":8502  *0\.0\.0\.0:0 " /c:":8502  *\[::\]:0 " >nul
if not errorlevel 1 goto running

echo.
echo  1/4 baixando a versao nova ...
if exist "%TMPZIP%" del /f /q "%TMPZIP%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri '%URL%' -OutFile '%TMPZIP%'"
if not exist "%TMPZIP%" curl.exe -L -s -o "%TMPZIP%" "%URL%"
if not exist "%TMPZIP%" goto nodownload

echo  2/4 abrindo o zip ...
if exist "%TMPDIR%" rmdir /s /q "%TMPDIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; Expand-Archive -Force -LiteralPath '%TMPZIP%' -DestinationPath '%TMPDIR%'"
set "SRC=%TMPDIR%\OCED-main"
if not exist "%SRC%\app\oced.py" goto badzip
if not exist "%SRC%\engine\clean\yield_clean.py" goto badzip

for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%t"
if not defined STAMP set "STAMP=anterior"
set "BAK=_backup\%STAMP%"
if not exist "%BAK%" mkdir "%BAK%"
if not exist "%BAK%" goto nobackup

set "NEEDPIP=0"
fc /b "requirements.txt" "%SRC%\requirements.txt" >nul 2>nul || set "NEEDPIP=1"
fc /b "constraints.txt" "%SRC%\constraints.txt" >nul 2>nul || set "NEEDPIP=1"

echo  3/4 guardando a versao atual em %BAK% e copiando a nova ...
for %%d in (%DIRS%) do if exist "%%d" move "%%d" "%BAK%\%%d" >nul
for %%d in (%DIRS%) do if exist "%%d" goto locked
for %%f in (%FILES%) do if exist "%%f" copy /y "%%f" "%BAK%\%%f" >nul
for %%d in (%DIRS%) do if exist "%SRC%\%%d" robocopy "%SRC%\%%d" "%%d" /E /NFL /NDL /NJH /NJS /NP >nul
for %%f in (%FILES%) do if exist "%SRC%\%%f" copy /y "%SRC%\%%f" "%%f" >nul
if not exist "app\oced.py" goto rollback
if not exist "engine\clean\yield_clean.py" goto rollback

echo  4/4 conferindo o codigo novo ...
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" --version >nul 2>nul
if errorlevel 1 goto nocheck
"%PY%" -m compileall -q app engine >nul
if errorlevel 1 goto rollback
:checked

rem a new updater is saved beside this one (a running .bat must not be replaced)
set "NEWBAT=0"
if not exist "%SRC%\atualizar_oced.bat" goto batdone
fc /b "atualizar_oced.bat" "%SRC%\atualizar_oced.bat" >nul 2>nul || set "NEWBAT=1"
if "%NEWBAT%"=="1" copy /y "%SRC%\atualizar_oced.bat" "atualizar_oced.new.bat" >nul
:batdone

set "VER=?"
for /f "tokens=3" %%v in ('findstr /b /c:"VERSION = " app\brand.py') do set "VER=%%~v"
rmdir /s /q "%TMPDIR%" >nul 2>nul
del /f /q "%TMPZIP%" >nul 2>nul
echo.
echo  Pronto: OCED %VER% instalado nesta pasta.
echo  A versao anterior ficou guardada em %BAK% - pode apagar essa pasta quando quiser.
if "%NEWBAT%"=="1" echo  O atualizador tambem mudou: depois de fechar esta janela, apague atualizar_oced.bat e renomeie atualizar_oced.new.bat para atualizar_oced.bat.
if "%NEEDPIP%"=="1" goto needpip
echo  Nenhum pacote novo do Python: abra o app com run_oced.bat como sempre.
echo.
pause
exit /b 0

:nocheck
echo  Python nao encontrado aqui: a conferencia do codigo foi pulada - o app abre com run_oced.bat como sempre.
goto checked

:needpip
echo  ATENCAO: os pacotes do Python mudaram nesta versao. Rode install_oced.bat uma vez e depois run_oced.bat.
echo.
pause
exit /b 0

:locked
echo  Nao consegui mover uma das pastas - o app ainda esta aberto? Voltando ao que estava ...
goto rollback

:rollback
echo  A atualizacao falhou: voltando para a versao anterior ...
if not defined BAK goto fail
for %%d in (%DIRS%) do if exist "%BAK%\%%d" if exist "%%d" rmdir /s /q "%%d"
for %%d in (%DIRS%) do if exist "%BAK%\%%d" move "%BAK%\%%d" "%%d" >nul
for %%f in (%FILES%) do if exist "%BAK%\%%f" copy /y "%BAK%\%%f" "%%f" >nul
echo  A versao anterior foi restaurada: nada mudou.
goto fail

:notoced
echo  Esta pasta nao parece ser a do OCED - falta app\oced.py. Ponha este arquivo ao lado do run_oced.bat.
goto fail

:running
echo  O app parece estar aberto - a porta 8502 esta em uso. Feche a janela preta do app e rode de novo.
goto fail

:nodownload
echo  Nao consegui baixar %URL%
echo  Verifique a internet ou o proxy da rede.
goto fail

:badzip
echo  O arquivo baixado nao tem o app completo: atualizacao cancelada, nada foi mudado.
goto fail

:nobackup
echo  Nao consegui criar a pasta de backup %BAK%: sem permissao de escrita nesta pasta? Nada foi mudado.
goto fail

:fail
echo.
pause
exit /b 1
