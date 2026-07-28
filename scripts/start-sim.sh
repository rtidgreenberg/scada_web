#!/usr/bin/env bash
# start-sim.sh — Start the SCADA field simulator (plc_publisher)
#
# Automatically discovers the RTI Connext DDS installation, sets up the
# environment (NDDSHOME, LD_LIBRARY_PATH, RTI_LICENSE_FILE), and launches
# the PLC publisher on domain 15.
#
# Usage:
#   ./start-sim.sh [--domain-id N] [--tags N] [--connext-home /path]
#
# Options:
#   --domain-id N       DDS domain ID (default: 15 = PLC::FIELD_DOMAIN_ID)
#   --tags N            Number of tags to publish (passed to plc_publisher)
#   --connext-home DIR  Explicit Connext install dir (skips auto-detection)
#   --dry-run           Print environment and command without executing

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIM_SCRIPT="$SCRIPT_DIR/sim/plc_publisher.py"

# ─── Defaults ────────────────────────────────────────────────────────────────
DOMAIN_ID=15
CONNEXT_HOME=""
DRY_RUN=false
EXTRA_ARGS=()

# ─── Parse arguments ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain-id)   DOMAIN_ID="$2"; shift 2 ;;
        --connext-home) CONNEXT_HOME="$2"; shift 2 ;;
        --dry-run)     DRY_RUN=true; shift ;;
        *)             EXTRA_ARGS+=("$1"); shift ;;
    esac
done

# ─── Auto-detect Connext installation ────────────────────────────────────────
# Search order: explicit flag > NDDSHOME env > well-known paths (newest first)
find_connext_home() {
    # 1. Already provided via flag
    if [[ -n "$CONNEXT_HOME" ]]; then
        if [[ -d "$CONNEXT_HOME" ]]; then
            echo "$CONNEXT_HOME"
            return 0
        fi
        echo >&2 "ERROR: --connext-home '$CONNEXT_HOME' does not exist"
        return 1
    fi

    # 2. NDDSHOME already set in environment
    if [[ -n "${NDDSHOME:-}" && -d "$NDDSHOME" ]]; then
        echo "$NDDSHOME"
        return 0
    fi

    # 3. Scan well-known locations (newest version first)
    local candidates=()
    for dir in "$HOME"/rti_connext_dds-*; do
        [[ -d "$dir" ]] && candidates+=("$dir")
    done
    # Also check /opt
    for dir in /opt/rti_connext_dds-*; do
        [[ -d "$dir" ]] && candidates+=("$dir")
    done

    if [[ ${#candidates[@]} -eq 0 ]]; then
        echo >&2 "ERROR: No RTI Connext DDS installation found."
        echo >&2 "       Searched: ~/rti_connext_dds-*, /opt/rti_connext_dds-*"
        echo >&2 "       Set NDDSHOME or pass --connext-home."
        return 1
    fi

    # Sort descending (newest version first) and pick the first
    local newest
    newest=$(printf '%s\n' "${candidates[@]}" | sort -rV | head -1)
    echo "$newest"
}

# ─── Find rtisetenv script for this platform ────────────────────────────────
find_rtisetenv() {
    local connext_dir="$1"
    local scripts_dir="$connext_dir/resource/scripts"

    if [[ ! -d "$scripts_dir" ]]; then
        echo >&2 "ERROR: $scripts_dir not found — is this a valid Connext install?"
        return 1
    fi

    # Match rtisetenv_*.bash for this OS
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

    # Already set
    if [[ -n "${RTI_LICENSE_FILE:-}" && -f "${RTI_LICENSE_FILE}" ]]; then
        echo "$RTI_LICENSE_FILE"
        return 0
    fi

    # Check inside the Connext install
    if [[ -f "$connext_dir/rti_license.dat" ]]; then
        echo "$connext_dir/rti_license.dat"
        return 0
    fi

    # Check home directory
    if [[ -f "$HOME/rti_license.dat" ]]; then
        echo "$HOME/rti_license.dat"
        return 0
    fi

    echo >&2 "WARNING: No RTI license file found. DDS will fail to create participants."
    echo >&2 "         Set RTI_LICENSE_FILE or place rti_license.dat in $connext_dir/"
    return 0
}

# ─── Main ────────────────────────────────────────────────────────────────────
CONNEXT_HOME=$(find_connext_home)
RTISETENV=$(find_rtisetenv "$CONNEXT_HOME")
LICENSE=$(find_license "$CONNEXT_HOME")

echo "┌─────────────────────────────────────────────────"
echo "│ SCADA Field Simulator (plc_publisher)"
echo "├─────────────────────────────────────────────────"
echo "│ Connext:  $CONNEXT_HOME"
echo "│ Setenv:   $RTISETENV"
echo "│ License:  ${LICENSE:-<not found>}"
echo "│ Domain:   $DOMAIN_ID"
echo "│ Script:   $SIM_SCRIPT"
echo "└─────────────────────────────────────────────────"

# Source the environment (unset -u temporarily — rtisetenv references
# LD_LIBRARY_PATH which may not be set yet)
# shellcheck disable=SC1090
set +u
source "$RTISETENV"
set -u

# Export license
if [[ -n "$LICENSE" ]]; then
    export RTI_LICENSE_FILE="$LICENSE"
fi

if [[ "$DRY_RUN" == "true" ]]; then
    echo ""
    echo "[dry-run] Would execute:"
    echo "  python3 $SIM_SCRIPT --domain-id $DOMAIN_ID ${EXTRA_ARGS[*]+${EXTRA_ARGS[*]}}"
    echo ""
    echo "Environment:"
    echo "  NDDSHOME=$NDDSHOME"
    echo "  RTI_LICENSE_FILE=${RTI_LICENSE_FILE:-}"
    echo "  LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-}"
    exit 0
fi

if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
    exec python3 "$SIM_SCRIPT" --domain-id "$DOMAIN_ID" "${EXTRA_ARGS[@]}" 2>&1 | tee -a "$SCRIPT_DIR/logs/sim.log"
else
    exec python3 "$SIM_SCRIPT" --domain-id "$DOMAIN_ID" 2>&1 | tee -a "$SCRIPT_DIR/logs/sim.log"
fi
