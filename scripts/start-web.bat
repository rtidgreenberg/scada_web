@echo off
REM start-web.bat — Start the SCADA web gateway (scada_web) on Windows
REM
REM Automatically discovers the RTI Connext DDS installation, sets up the
REM environment (NDDSHOME, PATH, RTI_LICENSE_FILE), and launches the
REM scada_web gateway on domain 16 (presentation).
REM
REM Usage:
REM   scripts\start-web.bat [--config FILE] [--host HOST] [--port PORT]
REM                         [--connext-home DIR] [--dry-run]

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."

REM ─── Defaults ──────────────────────────────────────────────────────────────
set "CONNEXT_HOME_ARG="
set "DRY_RUN=false"
set "EXTRA_ARGS="

REM ─── Parse arguments ───────────────────────────────────────────────────────
:parse_args
if "%~1"=="" goto done_args
if /i "%~1"=="--connext-home" (
    set "CONNEXT_HOME_ARG=%~2"
    shift & shift & goto parse_args
)
if /i "%~1"=="--dry-run" (
    set "DRY_RUN=true"
    shift & goto parse_args
)
set "EXTRA_ARGS=!EXTRA_ARGS! %~1"
shift
goto parse_args
:done_args

REM ─── Auto-detect Connext installation ──────────────────────────────────────
if defined CONNEXT_HOME_ARG (
    if exist "!CONNEXT_HOME_ARG!" (
        set "NDDSHOME=!CONNEXT_HOME_ARG!"
        goto found_connext
    )
    echo ERROR: --connext-home '!CONNEXT_HOME_ARG!' does not exist >&2
    exit /b 1
)

if defined NDDSHOME (
    if exist "!NDDSHOME!" goto found_connext
)

set "NDDSHOME="
for /d %%D in ("%USERPROFILE%\rti_connext_dds-*") do set "NDDSHOME=%%D"
if defined NDDSHOME goto found_connext

for /d %%D in ("C:\Program Files\rti_connext_dds-*") do set "NDDSHOME=%%D"
if defined NDDSHOME goto found_connext

echo ERROR: No RTI Connext DDS installation found. >&2
echo        Set NDDSHOME or pass --connext-home. >&2
exit /b 1

:found_connext

REM ─── Find rtisetenv script ────────────────────────────────────────────────
set "RTISETENV="
for %%F in ("%NDDSHOME%\resource\scripts\rtisetenv_*.bat") do set "RTISETENV=%%F"
if not defined RTISETENV (
    echo ERROR: No rtisetenv_*.bat found in %NDDSHOME%\resource\scripts >&2
    exit /b 1
)

REM ─── Find license file ────────────────────────────────────────────────────
if defined RTI_LICENSE_FILE (
    if exist "!RTI_LICENSE_FILE!" goto found_license
)
if exist "%NDDSHOME%\rti_license.dat" (
    set "RTI_LICENSE_FILE=%NDDSHOME%\rti_license.dat"
    goto found_license
)
if exist "%USERPROFILE%\rti_license.dat" (
    set "RTI_LICENSE_FILE=%USERPROFILE%\rti_license.dat"
    goto found_license
)
echo WARNING: No RTI license file found. DDS will fail to create participants. >&2
:found_license

REM ─── Banner ────────────────────────────────────────────────────────────────
echo.
echo   SCADA Web Gateway (scada_web)
echo   Connext:  %NDDSHOME%
echo   Setenv:   %RTISETENV%
echo   License:  %RTI_LICENSE_FILE%
echo.

REM ─── Source the Connext environment ────────────────────────────────────────
call "%RTISETENV%"

if "%DRY_RUN%"=="true" (
    echo [dry-run] Would execute:
    echo   python -m scada_web %EXTRA_ARGS%
    echo.
    echo Environment:
    echo   NDDSHOME=%NDDSHOME%
    echo   RTI_LICENSE_FILE=%RTI_LICENSE_FILE%
    echo   PATH=%PATH%
    exit /b 0
)

cd /d "%PROJECT_DIR%"

REM ─── Ensure Python dependencies are installed ─────────────────────────────
if exist requirements.txt (
    python -m pip install --quiet -r requirements.txt
)

python -m scada_web %EXTRA_ARGS%
