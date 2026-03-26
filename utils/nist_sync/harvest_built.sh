#!/bin/bash
#
# Fast NIST Harvesting from Built Profiles
#
# This script harvests NIST mappings by scanning all profiles in built products.
# Much faster than scanning rule.yml files (10x speed improvement)!
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Find repo root (go up two levels from utils/nist_sync/)
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$REPO_ROOT/build"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}▶${NC} $1"; }
log_success() { echo -e "${GREEN}✓${NC} $1"; }
log_warning() { echo -e "${YELLOW}!${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }

# Check Python
if ! command -v python3 &> /dev/null; then
    log_error "Python 3 required"
    exit 1
fi

show_usage() {
    cat << EOF
Fast NIST Harvesting from Built Profiles

This script harvests NIST mappings by scanning all profiles in built products.
It iterates through each product and harvests from all their built profiles.

When using --guards, it generates product-specific Jinja2 conditionals so rules
only apply to products where they exist (e.g., {%- if product in ["rhel8", "rhel9"] %}}).

Usage: $0 [OPTIONS] [PRODUCTS...]

Quick Usage:
  $0 rhel9                       # Single product, all profiles
  $0 rhel8 rhel9 rhel10          # Multiple products
  $0 --all                       # All built products
  $0 rhel8 rhel9 --guards        # With product-specific guards

Options:
  --all                          Use all built products
  --guards                       Add product-specific Jinja2 guards
  --output FILE                  Custom output path
  --verbose, -v                  Verbose output
  --profile NAME                 Only harvest from specific profile (e.g., cis, stig)

Examples:
  # Harvest from all RHEL 9 profiles
  $0 rhel9

  # All RHEL versions with guards
  $0 rhel8 rhel9 rhel10 --guards

  # All built products
  $0 --all --guards

  # Only CIS profiles
  $0 rhel9 --profile cis

Available Built Products:
$(ls $BUILD_DIR/*/profiles 2>/dev/null | sed 's|.*/\([^/]*\)/profiles|  \1|' || echo "  (none - run ./build_product first)")

EOF
}

# Parse arguments
PRODUCTS=()
ADD_GUARDS=false
OUTPUT=""
VERBOSE=""
ALL_PRODUCTS=false
PROFILE_FILTER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help|help)
            show_usage
            exit 0
            ;;
        --all)
            ALL_PRODUCTS=true
            shift
            ;;
        --guards)
            ADD_GUARDS=true
            shift
            ;;
        --output)
            OUTPUT="$2"
            shift 2
            ;;
        --profile)
            PROFILE_FILTER="$2"
            shift 2
            ;;
        --verbose|-v)
            VERBOSE="--verbose"
            shift
            ;;
        -*)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
        *)
            PRODUCTS+=("$1")
            shift
            ;;
    esac
done

# Determine products to scan
if $ALL_PRODUCTS; then
    PRODUCTS=()
    for product_dir in $BUILD_DIR/*/profiles; do
        if [ -d "$product_dir" ]; then
            product=$(basename $(dirname "$product_dir"))
            PRODUCTS+=("$product")
        fi
    done

    if [ ${#PRODUCTS[@]} -eq 0 ]; then
        log_error "No built products found in $BUILD_DIR"
        log_info "Build products first: ./build_product <product> --datastream-only"
        exit 1
    fi
elif [ ${#PRODUCTS[@]} -eq 0 ]; then
    log_error "Must specify products or --all"
    show_usage
    exit 1
fi

# Display header
echo "╔════════════════════════════════════════════════════════════╗"
echo "║   Fast NIST Harvesting from Built Profiles                ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

log_info "Products: ${PRODUCTS[*]}"
if [ -n "$PROFILE_FILTER" ]; then
    log_info "Profile filter: $PROFILE_FILTER"
fi
if $ADD_GUARDS; then
    log_info "Guards: Enabled"
fi

echo ""

# Temporary file for merged output
TEMP_CONTROL=$(mktemp)
OUTPUT_FILE="${OUTPUT:-$REPO_ROOT/controls/nist_800_53.yml}"
FIRST_RUN=true

# Harvest from each product
for product in "${PRODUCTS[@]}"; do
    profiles_dir="$BUILD_DIR/$product/profiles"

    if [ ! -d "$profiles_dir" ]; then
        log_warning "Product $product not built (no profiles directory)"
        continue
    fi

    # Find profiles
    profile_files=()
    if [ -n "$PROFILE_FILTER" ]; then
        # Specific profile
        profile_path="$profiles_dir/${PROFILE_FILTER}.profile"
        if [ -f "$profile_path" ]; then
            profile_files+=("$profile_path")
        fi
    else
        # All profiles
        for profile_file in "$profiles_dir"/*.profile; do
            if [ -f "$profile_file" ]; then
                profile_files+=("$profile_file")
            fi
        done
    fi

    if [ ${#profile_files[@]} -eq 0 ]; then
        log_warning "No profiles found for $product"
        continue
    fi

    log_info "Processing $product (${#profile_files[@]} profiles)"

    # Harvest from each profile
    for profile_file in "${profile_files[@]}"; do
        profile_name=$(basename "$profile_file" .profile)

        if [ "$VERBOSE" = "--verbose" ]; then
            echo "  - $profile_name"
        fi

        # Harvest from this profile
        if $FIRST_RUN; then
            # First run - create new file
            python3 harvest_from_profile.py \
                --profile "$profile_file" \
                --output "$TEMP_CONTROL" \
                $VERBOSE
            FIRST_RUN=false
        else
            # Subsequent runs - append
            python3 harvest_from_profile.py \
                --profile "$profile_file" \
                --control-file "$TEMP_CONTROL" \
                --strategy append \
                $VERBOSE
        fi
    done
done

# Apply guards if requested
if $ADD_GUARDS && [ ${#PRODUCTS[@]} -gt 1 ]; then
    log_info "Generating product guards..."

    TEMP_GUARDED=$(mktemp)

    python3 generate_product_guards.py \
        --control-file "$TEMP_CONTROL" \
        --output "$TEMP_GUARDED" \
        --products "${PRODUCTS[@]}" \
        $VERBOSE

    mv "$TEMP_GUARDED" "$TEMP_CONTROL"
fi

# Move to final location
mkdir -p "$(dirname "$OUTPUT_FILE")"
mv "$TEMP_CONTROL" "$OUTPUT_FILE"

echo ""
log_success "Harvesting complete!"
log_info "Output saved to: $OUTPUT_FILE"
echo ""
