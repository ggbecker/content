#!/usr/bin/env python3
"""
Complete NIST 800-53 Control File Builder

This script orchestrates the complete workflow:
1. Harvests CIS→NIST mappings from benchmark documents
2. Generates control file from OSCAL catalog
3. Applies product-specific guards for multi-product support

Usage:
  # Full workflow with guards for specific products
  ./build_nist_control.py --products rhel8 rhel9 rhel10 --guards

  # Without guards (single product or manual mapping)
  ./build_nist_control.py

  # Family-based guards
  ./build_nist_control.py --target rhel --guards
"""

import sys
from pathlib import Path
import argparse

# Import our existing modules
from harvest_cis_nist_mappings import CISNISTHarvester
from sync_nist import NISTControlSync

try:
    from generate_product_family_guards import ProductFamilyGuardGenerator
    GUARDS_AVAILABLE = True
except ImportError:
    GUARDS_AVAILABLE = False
    print("Warning: generate_product_family_guards.py not available")

try:
    from generate_nist_based_cis_profile import NISTBasedCISProfileGenerator
    PROFILE_GEN_AVAILABLE = True
except ImportError:
    PROFILE_GEN_AVAILABLE = False
    print("Warning: generate_nist_based_cis_profile.py not available")


def main():
    """Complete NIST control file generation workflow."""
    parser = argparse.ArgumentParser(
        description='Build NIST 800-53 control file with CIS mappings and product guards',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Full workflow with guards for RHEL products
  %(prog)s --products rhel8 rhel9 rhel10 --guards

  # Without guards (simpler, single product)
  %(prog)s

  # With product family guards
  %(prog)s --target rhel --guards

  # Harvest only (skip OSCAL sync)
  %(prog)s --harvest-only --products rhel9

  # Sync only (use existing cache)
  %(prog)s --sync-only --products rhel8 rhel9 rhel10 --guards
        '''
    )

    parser.add_argument(
        '--products',
        nargs='+',
        default=['rhel8', 'rhel9', 'rhel10'],
        help='Products to harvest from and guard for (default: rhel8 rhel9 rhel10)'
    )
    parser.add_argument(
        '--target',
        nargs='+',
        help='Product families for guards (e.g., rhel ocp)'
    )
    parser.add_argument(
        '--guards',
        action='store_true',
        help='Apply product-specific Jinja2 guards'
    )
    parser.add_argument(
        '--harvest-only',
        action='store_true',
        help='Only harvest CIS mappings, skip OSCAL sync'
    )
    parser.add_argument(
        '--sync-only',
        action='store_true',
        help='Only sync from OSCAL + cache, skip harvesting'
    )
    parser.add_argument(
        '--repo-root',
        type=Path,
        default=Path(__file__).parent.parent.parent,
        help='Path to repository root (default: auto-detect)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--generate-cis-profile',
        action='store_true',
        help='Generate NIST-based CIS profile after sync'
    )
    parser.add_argument(
        '--cis-level',
        default='l2_server',
        choices=['l1_server', 'l2_server', 'l1_workstation', 'l2_workstation'],
        help='CIS level for profile generation (default: l2_server)'
    )

    args = parser.parse_args()

    print("╔════════════════════════════════════════════════════════════╗")
    print("║   NIST 800-53 Control File Builder                        ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()

    repo_root = args.repo_root

    try:
        # Step 1: Harvest CIS→NIST mappings (unless sync-only)
        if not args.sync_only:
            print("STEP 1: Harvesting CIS→NIST Mappings")
            print("=" * 60)

            harvester = CISNISTHarvester(repo_root)

            # Product to RHEL version mapping
            product_to_version = {
                'rhel8': '8',
                'rhel9': '9',
                'rhel10': '10'
            }

            all_rule_mappings = []
            all_var_mappings = []
            for product in args.products:
                if product not in product_to_version:
                    print(f"Warning: Unknown product {product}, skipping")
                    continue

                rhel_version = product_to_version[product]
                rule_mapping, var_mapping = harvester.harvest_from_product(product, rhel_version)
                all_rule_mappings.append(rule_mapping)
                all_var_mappings.append(var_mapping)

            # Merge and save
            print("\nMerging mappings from all products...")
            merged_rules = harvester.merge_rule_mappings(*all_rule_mappings)
            merged_vars = harvester.merge_rule_mappings(*all_var_mappings)
            print(f"  ✓ Total unique rules: {len(merged_rules)}")
            print(f"  ✓ Total unique variables: {len(merged_vars)}")

            harvester.save_mapping_cache(merged_rules, merged_vars)
            print()

        # Stop if harvest-only
        if args.harvest_only:
            print("✓ Harvest complete (harvest-only mode)")
            return 0

        # Step 2: Generate control file from OSCAL + mappings
        print("STEP 2: Generating Control File from OSCAL")
        print("=" * 60)

        syncer = NISTControlSync(repo_root)
        changed = syncer.sync_controls(verbose=args.verbose)
        print()

        # Step 3: Apply product guards (if requested)
        if args.guards:
            if not GUARDS_AVAILABLE:
                print("Error: Product guards requested but generate_product_family_guards.py not available")
                return 1

            print("STEP 3: Applying Product Guards")
            print("=" * 60)

            guard_gen = ProductFamilyGuardGenerator(repo_root)

            # Use target families if specified, otherwise use products
            if args.target:
                targets = guard_gen.expand_product_targets(args.target)
                print(f"Target families: {', '.join(args.target)}")
                print(f"Expanded to products: {', '.join(targets)}")
            else:
                targets = args.products
                print(f"Target products: {', '.join(targets)}")

            print()

            # Build rule→products mapping
            rule_to_products = guard_gen.build_rule_to_products_map(
                targets,
                verbose=args.verbose
            )

            print()

            # Apply guards to control file (update in place)
            control_file = repo_root / "controls" / "nist_800_53.yml"
            guard_gen.apply_guards_to_control_file(
                control_file,
                rule_to_products,
                output_file=control_file,  # Update in place by specifying same file
                use_family_guards=True,
                verbose=args.verbose
            )
            print()

        # Step 4: Generate CIS profile (if requested)
        if args.generate_cis_profile:
            if not PROFILE_GEN_AVAILABLE:
                print("Error: Profile generation requested but generate_nist_based_cis_profile.py not available")
                return 1

            print("STEP 4: Generating NIST-based CIS Profile")
            print("=" * 60)

            profile_gen = NISTBasedCISProfileGenerator(repo_root)

            # Generate profile for each product
            for product in args.products:
                output_file = repo_root / "products" / product / "profiles" / "cis_nist.profile"

                print(f"\nGenerating profile for {product}...")
                profile_gen.generate_profile(product, args.cis_level, output_file)

            print()

        # Final summary
        print("╔════════════════════════════════════════════════════════════╗")
        print("║   Build Complete! ✓                                        ║")
        print("╚════════════════════════════════════════════════════════════╝")
        print()
        print(f"Control file: {repo_root / 'controls' / 'nist_800_53.yml'}")
        print(f"Mapping cache: {repo_root / 'utils' / 'nist_sync' / 'data' / 'cis_nist_mappings.json'}")

        if args.guards:
            print()
            print("Product guards applied:")
            print(f"  Products: {', '.join(args.products)}")
            print(f"  Guards use: product in [...] and product.startswith(...)")

        print()
        print("Next steps:")
        print("  1. Review: git diff controls/nist_800_53.yml")
        print("  2. Add reference_type: nist to enable build system integration")
        print("  3. Build products to test: ./build_product <product> --datastream-only")

        return 0

    except Exception as e:
        print(f"\n✗ Build failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
