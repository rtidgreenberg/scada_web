@echo off
REM Start RTI Web Integration Service with the scada-web WIS config.
REM Adjust NDDSHOME to your RTI installation if it is not already set.
setlocal
if "%NDDSHOME%"=="" (
  echo ERROR: NDDSHOME is not set. Please set NDDSHOME to your RTI Connext installation path.
  exit /b 1
)
set "RTI_HOME=%NDDSHOME%"
set "PATH=%RTI_HOME%\bin;%PATH%"

set "SCRIPT_DIR=%~dp0"
set "CONFIG_FILE=%SCRIPT_DIR%wis-config.xml"
set "UI_DIR=%SCRIPT_DIR%..\UI"

if not exist "%CONFIG_FILE%" (
  echo ERROR: Config file not found: %CONFIG_FILE%
  exit /b 1
)

echo Starting RTI Web Integration Service...
echo Serving UI from %UI_DIR% at http://localhost:8080/
REM -enableWebSockets is a valueless switch (do NOT pass "yes" — that's only for -enableKeepAlive)
REM -documentRoot serves the browser UI same-origin with WIS, so the REST/WebSocket calls need no CORS.
"%RTI_HOME%\bin\rtiwebintegrationservice.bat" -cfgFile "%CONFIG_FILE%" -cfgName "ScadaWeb" -listeningPorts 8080 -enableWebSockets -verbosity 3 -documentRoot "%UI_DIR%"
echo WIS exited with %ERRORLEVEL%
endlocal
