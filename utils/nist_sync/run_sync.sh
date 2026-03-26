#!/bin/bash
#
# NIST 800-53 Control File Synchronization - Master Script
#
# This script runs the complete workflow to build and maintain the nist_800_53.yml file.
#

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}▶${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}!${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    log_error "Python 3 is required but not found. Please install Python 3.8 or later."
    exit 1
fi

# Check if required packages are installed
if ! python3 -c "import ruamel.yaml" 2>/dev/null; then
    log_warning "Required packages not installed. Installing..."
    pip install -r requirements.txt || {
        log_error "Failed to install requirements. Try manually: pip install -r requirements.txt"
        exit 1
    }
fi

# Parse command line arguments
MODE="${1:-full}"

case "$MODE" in
    download|fetch)
        log_info "Downloading NIST OSCAL catalog and baselines..."
        python3 download_oscal.py
        log_success "Download complete"
        ;;

    sync)
        log_info "Synchronizing control file with OSCAL catalog..."
        python3 sync_nist.py --verbose
        log_success "Sync complete"
        ;;

    harvest)
        log_info "Profile-aware NIST harvesting from built rules..."
        log_warning "This requires products to be built first!"
        log_info "Example: ./build_product rhel9 --datastream-only"
        echo ""
        log_info "Profile-aware harvesting is now a manual workflow."
        log_info "See BUILT_RULES_WORKFLOW.md for detailed instructions."
        echo ""
        log_info "Quick example:"
        echo "  ./harvest_from_profile.sh rhel9 cis --create-new"
        echo "  ./harvest_from_profile.sh rhel8 cis --strategy append --control-file controls/nist_rhel9_cis.yml"
        echo ""
        ;;

    full|bootstrap)
        echo ""
        echo "╔════════════════════════════════════════════════════════════╗"
        echo "║   NIST 800-53 Control File Synchronization - Full Build   ║"
        echo "╚════════════════════════════════════════════════════════════╝"
        echo ""

        # Step 1: Download OSCAL data
        log_info "Step 1/2: Downloading NIST OSCAL catalog..."
        if python3 download_oscal.py; then
            log_success "OSCAL data downloaded"
        else
            log_error "Failed to download OSCAL data"
            exit 1
        fi

        echo ""

        # Step 2: Sync control file
        log_info "Step 2/2: Synchronizing control file..."
        if python3 sync_nist.py --verbose; then
            log_success "Control file synchronized"
        else
            log_error "Failed to sync control file"
            exit 1
        fi

        echo ""
        echo "╔════════════════════════════════════════════════════════════╗"
        echo "║                Sync Complete! ✓                            ║"
        echo "╚════════════════════════════════════════════════════════════╝"
        echo ""
        log_info "Control file location: ../../controls/nist_800_53.yml"
        log_info "Review the changes with: git diff ../../controls/nist_800_53.yml"
        echo ""
        log_info "Next step: Harvest rule mappings from profiles"
        log_info "See BUILT_RULES_WORKFLOW.md for harvesting instructions."
        echo ""
        ;;

    validate)
        log_info "Validating control file..."
        CONTROL_FILE="../../controls/nist_800_53.yml"

        if [ ! -f "$CONTROL_FILE" ]; then
            log_error "Control file not found: $CONTROL_FILE"
            exit 1
        fi

        # Check if file is valid YAML
        if python3 -c "
from ruamel.yaml import YAML
yaml = YAML()
with open('$CONTROL_FILE', 'r') as f:
    yaml.load(f)
print('YAML syntax: OK')
        "; then
            log_success "Control file is valid YAML"
        else
            log_error "Control file has YAML syntax errors"
            exit 1
        fi

        # Count controls
        CONTROL_COUNT=$(python3 -c "
from ruamel.yaml import YAML
yaml = YAML()
with open('$CONTROL_FILE', 'r') as f:
    data = yaml.load(f)
print(len(data.get('controls', [])))
        ")

        log_info "Total controls: $CONTROL_COUNT"

        # Count rules
        RULE_COUNT=$(python3 -c "
from ruamel.yaml import YAML
yaml = YAML()
with open('$CONTROL_FILE', 'r') as f:
    data = yaml.load(f)
total = sum(len(ctrl.get('rules', [])) for ctrl in data.get('controls', []))
print(total)
        ")

        log_info "Total rule mappings: $RULE_COUNT"

        # Count by status
        python3 -c "
from ruamel.yaml import YAML
from collections import Counter
yaml = YAML()
with open('$CONTROL_FILE', 'r') as f:
    data = yaml.load(f)
statuses = Counter(ctrl.get('status', 'unknown') for ctrl in data.get('controls', []))
print('Controls by status:')
for status, count in sorted(statuses.items()):
    print(f'  {status}: {count}')
        "

        log_success "Validation complete"
        ;;

    help|--help|-h)
        cat << EOF
NIST 800-53 Control File Synchronization

Usage: ./run_sync.sh [MODE]

Modes:
  full (default)  - Run complete workflow: download and sync control file
  bootstrap       - Alias for 'full'
  download        - Download NIST OSCAL catalog and baselines
  sync            - Synchronize control file with OSCAL catalog
  harvest         - Show instructions for profile-aware harvesting
  validate        - Validate control file and show statistics
  help            - Show this help message

Examples:
  ./run_sync.sh                    # Full workflow (download + sync)
  ./run_sync.sh download           # Just download OSCAL data
  ./run_sync.sh sync               # Just sync control file
  ./run_sync.sh harvest            # Show harvesting instructions
  ./run_sync.sh validate           # Validate control file

Harvesting NIST Mappings:
  Harvesting is now profile-aware and requires specifying which profile
  to harvest from. This is a separate manual workflow.

  # 1. Build products first
  cd ../.. && ./build_product rhel9 rhel8 rhel10 --datastream-only
  cd utils/nist_sync

  # 2. Harvest from a profile (e.g., CIS)
  ./harvest_from_profile.sh rhel9 cis --create-new

  # 3. Add other products
  ./harvest_from_profile.sh rhel8 cis --strategy append --control-file controls/nist_rhel9_cis.yml
  ./harvest_from_profile.sh rhel10 cis --strategy append --control-file controls/nist_rhel9_cis.yml

  # Or use the convenience script (harvests and guards in one step)
  ./harvest_built.sh rhel8 rhel9 rhel10 --profile cis --guards

  See BUILT_RULES_WORKFLOW.md for complete documentation.
EOF
        ;;

    *)
        log_error "Unknown mode: $MODE"
        echo "Use './run_sync.sh help' for usage information"
        exit 1
        ;;
esac
