#!/usr/bin/env bash
# start-web.sh — Start the SCADA web gateway (scada_web)
#
# Automatically discovers the RTI Connext DDS installation, sets up the
# environment (NDDSHOME, LD_LIBRARY_PATH, RTI_LICENSE_FILE), and launches
# the scada_web gateway on domain 16 (presentation).
#
# Usage:
#   ./start-web.sh [--config path/to/config.yaml] [--host HOST] [--port PORT]
#                  [--connext-home /path] [--dry-run]
#
# Options:
#   --config FILE       YAML config (default: scada_web/config.yaml)
#   --host HOST         Override server host
#   --port PORT         Override server port
#   --connext-home DIR  Explicit Connext install dir (skips auto-detection)
#   --dry-run           Print environment and command without executing

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ─── Defaults ────────────────────────────────────────────────────────────────
CONNEXT_HOME=""
DRY_RUN=false
EXTRA_ARGS=()

# ─── Parse arguments ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --connext-home) CONNEXT_HOME="$2"; shift 2 ;;
        --dry-run)     DRY_RUN=true; shift ;;
        *)             EXTRA_ARGS+=("$1"); shift ;;
    esac
done

# ─── Auto-detect Connext installation ────────────────────────────────────────
find_connext_home() {
    if [[ -n "$CONNEXT_HOME" ]]; then
        if [[ -d "$CONNEXT_HOME" ]]; then
            echo "$CONNEXT_HOME"
            return 0
        fi
        echo >&2 "ERROR: --connext-home '$CONNEXT_HOME' does not exist"
        return 1
    fi

    if [[ -n "${NDDSHOME:-}" && -d "$NDDSHOME" ]]; then
        echo "$NDDSHOME"
        return 0
    fi

    local candidates=()
    for dir in "$HOME"/rti_connext_dds-*; do
        [[ -d "$dir" ]] && candidates+=("$dir")
    done
    for dir in /opt/rti_connext_dds-*; do
        [[ -d "$dir" ]] && candidates+=("$dir")
    done

    if [[ ${#candidates[@]} -eq 0 ]]; then
        echo >&2 "ERROR: No RTI Connext DDS installation found."
        echo >&2 "       Set NDDSHOME or pass --connext-home."
        return 1
    fi

    printf '%s\n' "${candidates[@]}" | sort -rV | head -1
}

# ─── Find rtisetenv script ──────────────────────────────────────────────────
find_rtisetenv() {
    local connext_dir="$1"
    local scripts_dir="$connext_dir/resource/scripts"

    if [[ ! -d "$scripts_dir" ]]; then
        echo >&2 "ERROR: $scripts_dir not found — is this a valid Connext install?"
        return 1
    fi

    local setenv
    setenv=$(find "$scripts_dir" -maxdepth 1 -name 'rtisetenv_*.bash' | sort -rV | head -1)

    if [[ -z "$setenv" ]]; then
        echo >&2 "ERROR: No rtisetenv_*.bash found in $scripts_dir"
        return 1
    fi
    echo "$setenv"
}

# ─── Find license file ──────────────────────────────────────────────────────
find_license() {
    local connext_dir="$1"

    if [[ -n "${RTI_LICENSE_FILE:-}" && -f "${RTI_LICENSE_FILE}" ]]; then
        echo "$RTI_LICENSE_FILE"
        return 0
    fi

    if [[ -f "$connext_dir/rti_license.dat" ]]; then
        echo "$connext_dir/rti_license.dat"
        return 0
    fi

    if [[ -f "$HOME/rti_license.dat" ]]; then
        echo "$HOME/rti_license.dat"
        return 0
    fi

    echo >&2 "WARNING: No RTI license file found. DDS will fail to create participants."
    return 0
}

# ─── Main ────────────────────────────────────────────────────────────────────
CONNEXT_HOME=$(find_connext_home)
RTISETENV=$(find_rtisetenv "$CONNEXT_HOME")
LICENSE=$(find_license "$CONNEXT_HOME")

echo "┌─────────────────────────────────────────────────"
echo "│ SCADA Web Gateway (scada_web)"
echo "├─────────────────────────────────────────────────"
echo "│ Connext:  $CONNEXT_HOME"
echo "│ Setenv:   $RTISETENV"
echo "│ License:  ${LICENSE:-<not found>}"
echo "└─────────────────────────────────────────────────"

# Source the Connext environment
# shellcheck disable=SC1090
set +u
source "$RTISETENV"
set -u

if [[ -n "$LICENSE" ]]; then
    export RTI_LICENSE_FILE="$LICENSE"
fi

if [[ "$DRY_RUN" == "true" ]]; then
    echo ""
    echo "[dry-run] Would execute:"
    echo "  python3 -m scada_web ${EXTRA_ARGS[*]+${EXTRA_ARGS[*]}}"
    echo ""
    echo "Environment:"
    echo "  NDDSHOME=$NDDSHOME"
    echo "  RTI_LICENSE_FILE=${RTI_LICENSE_FILE:-}"
    echo "  LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-}"
    exit 0
fi

cd "$SCRIPT_DIR"

if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
    exec python3 -m scada_web "${EXTRA_ARGS[@]}" 2>&1 | tee -a "$SCRIPT_DIR/logs/scada_web.log"
else
    exec python3 -m scada_web 2>&1 | tee -a "$SCRIPT_DIR/logs/scada_web.log"
fi
