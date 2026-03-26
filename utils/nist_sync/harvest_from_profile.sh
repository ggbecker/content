#!/bin/bash
#
# Profile-Aware NIST Harvesting - Wrapper Script
#
# This script makes it easy to harvest NIST mappings from built profiles.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Find repo root (go up two levels from utils/nist_sync/)
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$REPO_ROOT/build"
CONTROLS_DIR="$REPO_ROOT/controls"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${BLUE}▶${NC} $1"; }
log_success() { echo -e "${GREEN}✓${NC} $1"; }

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 required"
    exit 1
fi

# Parse arguments
PROFILE_PATH=""
PRODUCT=""
PROFILE_NAME=""
OUTPUT_FILE=""

show_usage() {
    cat << EOF
Profile-Aware NIST Harvesting

Usage: $0 [OPTIONS]

Quick Usage:
  $0 rhel8 cis                    # Harvest from RHEL 8 CIS profile
  $0 rhel9 stig --create-new      # Create nist_rhel9_stig.yml

Options:
  PRODUCT PROFILE                 Quick mode: specify product and profile name
  --profile PATH                  Full path to built profile
  --create-new                    Create new control file instead of updating existing
  --output FILE                   Specify output file path
  --control-file FILE             Existing control file to update (used with --strategy)
  --strategy append|replace       Merge strategy (default: append)
  --verbose                       Verbose output
  --dry-run                       Show what would be done

Examples:
  # Update main control file from RHEL 8 CIS profile
  $0 rhel8 cis

  # Create STIG-specific control file
  $0 rhel9 stig --create-new

  # Custom output location
  $0 rhel8 cis --output controls/nist_rhel8_cis.yml

  # Append to existing control file
  $0 rhel8 cis --control-file ../../controls/nist_800_53.yml --strategy append

  # Replace all mappings (careful!)
  $0 rhel8 cis --strategy replace --verbose

Available Profiles:
$(ls $BUILD_DIR/*/profiles/*.profile 2>/dev/null | sed 's|.*/\([^/]*\)/profiles/\(.*\)\.profile|  \1/\2|' | sort || echo "  (No built profiles found - run ./build_product first)")

EOF
}

# Check for help
if [[ "$1" == "-h" || "$1" == "--help" || "$1" == "help" ]]; then
    show_usage
    exit 0
fi

# Quick mode: product + profile name
if [[ -n "$1" && "$1" != --* ]]; then
    PRODUCT="$1"
    shift

    if [[ -n "$1" && "$1" != --* ]]; then
        PROFILE_NAME="$1"
        shift
        PROFILE_PATH="$BUILD_DIR/${PRODUCT}/profiles/${PROFILE_NAME}.profile"
    else
        echo "Error: Must specify both PRODUCT and PROFILE"
        echo "Example: $0 rhel8 cis"
        exit 1
    fi
fi

# Parse remaining options
CREATE_NEW=false
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile)
            PROFILE_PATH="$2"
            shift 2
            ;;
        --create-new)
            CREATE_NEW=true
            shift
            ;;
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --control-file|--strategy|--verbose|--dry-run)
            EXTRA_ARGS+=("$1")
            if [[ "$1" == "--strategy" || "$1" == "--control-file" ]]; then
                EXTRA_ARGS+=("$2")
                shift
            fi
            shift
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate profile path
if [[ -z "$PROFILE_PATH" ]]; then
    echo "Error: Must specify profile"
    show_usage
    exit 1
fi

if [[ ! -f "$PROFILE_PATH" ]]; then
    echo "Error: Profile not found: $PROFILE_PATH"
    echo ""
    echo "Available profiles:"
    ls $BUILD_DIR/*/profiles/*.profile 2>/dev/null | sed 's|$BUILD_DIR/||' || echo "  (none - run ./build_product first)"
    exit 1
fi

# Determine output
if [[ -n "$OUTPUT_FILE" ]]; then
    EXTRA_ARGS+=(--output "$OUTPUT_FILE")
elif $CREATE_NEW; then
    # Auto-generate output filename
    if [[ -n "$PRODUCT" && -n "$PROFILE_NAME" ]]; then
        OUTPUT_FILE="$CONTROLS_DIR/nist_${PRODUCT}_${PROFILE_NAME}.yml"
        EXTRA_ARGS+=(--output "$OUTPUT_FILE")
    else
        echo "Error: --create-new requires either PRODUCT/PROFILE or --output"
        exit 1
    fi
fi

# Display what we're doing
echo "╔════════════════════════════════════════════════════════════╗"
echo "║   Profile-Aware NIST Harvesting                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
log_info "Profile: $PROFILE_PATH"
if [[ -n "$OUTPUT_FILE" ]]; then
    log_info "Output:  $OUTPUT_FILE (new file)"
else
    log_info "Output:  controls/nist_800_53.yml (update)"
fi
echo ""

# Run the harvester
python3 harvest_from_profile.py --profile "$PROFILE_PATH" "${EXTRA_ARGS[@]}"

echo ""
log_success "Done!"
echo ""

if [[ -n "$OUTPUT_FILE" ]]; then
    log_info "Review: git diff $OUTPUT_FILE"
else
    log_info "Review: git diff $CONTROLS_DIR/nist_800_53.yml"
fi
