@echo off
REM start-select.bat — Start the SCADA selector (scada_selector) on Windows
REM
REM Automatically discovers the RTI Connext DDS installation, sets up the
REM environment (NDDSHOME, PATH, RTI_LICENSE_FILE), and launches the
REM scada_selector binary that bridges field domain 15 to presentation domain 16.
REM
REM Usage:
REM   scripts\start-select.bat [--config FILE] [--connext-home DIR] [--dry-run]

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "SELECTOR_BIN=%PROJECT_DIR%\scada_select\build\Release\scada_selector.exe"
set "DEFAULT_CONFIG=%PROJECT_DIR%\scada_select\config.yaml"

REM ─── Defaults ──────────────────────────────────────────────────────────────
set "CONNEXT_HOME_ARG="
set "DRY_RUN=false"
set "CONFIG=%DEFAULT_CONFIG%"
set "EXTRA_ARGS="

REM ─── Parse arguments ───────────────────────────────────────────────────────
:parse_args
if "%~1"=="" goto done_args
if /i "%~1"=="--config" (
    set "CONFIG=%~2"
    shift & shift & goto parse_args
)
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

REM ─── Verify binary exists ─────────────────────────────────────────────────
if not exist "%SELECTOR_BIN%" (
    REM Try Debug build layout too
    set "SELECTOR_BIN=%PROJECT_DIR%\scada_select\build\Debug\scada_selector.exe"
)
if not exist "%SELECTOR_BIN%" (
    REM Try flat build layout (no config subdir)
    set "SELECTOR_BIN=%PROJECT_DIR%\scada_select\build\scada_selector.exe"
)
if not exist "%SELECTOR_BIN%" (
    echo ERROR: Selector binary not found: %SELECTOR_BIN% >&2
    echo        Build it first with CMake. >&2
    exit /b 1
)

REM ─── Banner ────────────────────────────────────────────────────────────────
echo.
echo   SCADA Selector (scada_selector)
echo   Connext:  %NDDSHOME%
echo   Setenv:   %RTISETENV%
echo   License:  %RTI_LICENSE_FILE%
echo   Config:   %CONFIG%
echo   Binary:   %SELECTOR_BIN%
echo.

REM ─── Source the Connext environment ────────────────────────────────────────
call "%RTISETENV%"

if "%DRY_RUN%"=="true" (
    echo [dry-run] Would execute:
    echo   "%SELECTOR_BIN%" --config "%CONFIG%" %EXTRA_ARGS%
    echo.
    echo Environment:
    echo   NDDSHOME=%NDDSHOME%
    echo   RTI_LICENSE_FILE=%RTI_LICENSE_FILE%
    echo   PATH=%PATH%
    exit /b 0
)

"%SELECTOR_BIN%" --config "%CONFIG%" %EXTRA_ARGS%
