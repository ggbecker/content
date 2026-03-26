#!/usr/bin/env python3
"""
DEPRECATED: Harvest existing NIST 800-53 mappings from rule.yml files.

⚠️  WARNING: This script is DEPRECATED and should not be used!

This script scans source rule.yml files which contain Jinja2 syntax that
causes parsing errors. It is also 10x slower than the new workflow.

INSTEAD, USE ONE OF THESE:
  1. harvest_from_profile.sh - Profile-aware harvesting from built profiles
  2. harvest_built.sh - Generic harvesting from all built rules

These scripts read from build/<product>/rules/*.json which are already
processed and contain no Jinja2 syntax.

Example:
  ./build_product rhel9 --datastream-only
  ./harvest_built.sh rhel9

See BUILT_RULES_WORKFLOW.md for details.
"""

import sys
from pathlib import Path
from typing import Dict, Set, List
import re

try:
    from ruamel.yaml import YAML
except ImportError:
    print("Error: ruamel.yaml is required. Install it with:", file=sys.stderr)
    print("  pip install ruamel.yaml", file=sys.stderr)
    sys.exit(1)


class MappingHarvester:
    """Harvests NIST mappings from rule.yml files."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.control_file = repo_root / "controls" / "nist_800_53.yml"

        # Setup YAML parser
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.default_flow_style = False
        self.yaml.indent(mapping=2, sequence=4, offset=2)
        self.yaml.width = 4096

    def find_all_rules(self) -> List[Path]:
        """Find all rule.yml files in the repository."""
        rule_files = []

        # Search in linux_os/guide
        linux_guide = self.repo_root / "linux_os" / "guide"
        if linux_guide.exists():
            rule_files.extend(linux_guide.rglob("rule.yml"))

        # Search in applications (e.g., OpenShift)
        apps_dir = self.repo_root / "applications"
        if apps_dir.exists():
            rule_files.extend(apps_dir.rglob("rule.yml"))

        return rule_files

    def extract_nist_references(self, rule_file: Path) -> Set[str]:
        """Extract NIST 800-53 control IDs from a rule file."""
        nist_refs = set()

        try:
            with open(rule_file, 'r', encoding='utf-8') as f:
                rule_data = self.yaml.load(f)

            if not rule_data:
                return nist_refs

            # Look for references.nist field
            if 'references' in rule_data and 'nist' in rule_data['references']:
                nist_value = rule_data['references']['nist']

                # Handle both string and list formats
                if isinstance(nist_value, str):
                    # Parse comma-separated control IDs
                    # Example: "CM-6,CM-6(1),SI-2(6)"
                    controls = [c.strip() for c in nist_value.split(',')]
                    nist_refs.update(controls)
                elif isinstance(nist_value, list):
                    nist_refs.update(nist_value)

        except Exception as e:
            print(f"Warning: Failed to parse {rule_file}: {e}", file=sys.stderr)

        return nist_refs

    def normalize_control_id(self, control_id: str) -> str:
        """
        Normalize NIST control ID to standard format.

        Examples:
          CM-6 -> CM-6
          CM-6(1) -> CM-6(1)
          cm-6 -> CM-6
          CM-6a -> CM-6(a)  (some legacy formats)
        """
        # Convert to uppercase
        ctrl_id = control_id.upper().strip()

        # Handle legacy format like "CM-6A" -> "CM-6(A)"
        # Match pattern like AC-2A or CM-11B
        if re.match(r'^[A-Z]+-\d+[A-Z]$', ctrl_id):
            ctrl_id = ctrl_id[:-1] + '(' + ctrl_id[-1] + ')'

        return ctrl_id

    def harvest_mappings(self, verbose: bool = False) -> Dict[str, Set[str]]:
        """
        Scan all rules and build control_id -> rule_ids mapping.

        Returns a dict mapping normalized NIST control IDs to sets of rule IDs.
        """
        print("Scanning repository for rule.yml files...")
        rule_files = self.find_all_rules()
        print(f"  Found {len(rule_files)} rule files")

        # Build mapping: control_id -> set of rule_ids
        control_to_rules: Dict[str, Set[str]] = {}

        print("Harvesting NIST references from rules...")
        rules_with_nist = 0

        for rule_file in rule_files:
            # Extract rule ID from directory name
            rule_id = rule_file.parent.name

            # Extract NIST references
            nist_refs = self.extract_nist_references(rule_file)

            if nist_refs:
                rules_with_nist += 1
                if verbose:
                    print(f"  {rule_id}: {', '.join(nist_refs)}")

                for control_id in nist_refs:
                    normalized_id = self.normalize_control_id(control_id)

                    if normalized_id not in control_to_rules:
                        control_to_rules[normalized_id] = set()

                    control_to_rules[normalized_id].add(rule_id)

        print(f"  ✓ Found {rules_with_nist} rules with NIST references")
        print(f"  ✓ Mapped to {len(control_to_rules)} unique NIST controls")

        return control_to_rules

    def apply_mappings_to_control_file(
        self,
        control_to_rules: Dict[str, Set[str]],
        merge_strategy: str = 'append',
        verbose: bool = False
    ) -> bool:
        """
        Apply harvested mappings to the nist_800_53.yml control file.

        Args:
            control_to_rules: Mapping of control IDs to rule IDs
            merge_strategy: 'append' (add new rules) or 'replace' (overwrite)
            verbose: Enable verbose output

        Returns:
            True if changes were made
        """
        if not self.control_file.exists():
            print(f"Error: Control file not found at {self.control_file}", file=sys.stderr)
            print("Run sync_nist.py first to create the control file.", file=sys.stderr)
            return False

        print("Loading control file...")
        with open(self.control_file, 'r', encoding='utf-8') as f:
            control_data = self.yaml.load(f)

        if not control_data or 'controls' not in control_data:
            print("Error: Invalid control file format", file=sys.stderr)
            return False

        # Build lookup for controls
        controls_by_id = {
            ctrl['id'].upper(): ctrl
            for ctrl in control_data['controls']
        }

        print(f"Applying mappings using '{merge_strategy}' strategy...")
        changes_made = False
        mapped_count = 0
        unmapped_count = 0

        for control_id, rule_ids in sorted(control_to_rules.items()):
            normalized_id = control_id.upper()

            if normalized_id not in controls_by_id:
                if verbose:
                    print(f"  Warning: Control {normalized_id} not found in control file (has {len(rule_ids)} rules)")
                unmapped_count += 1
                continue

            control = controls_by_id[normalized_id]

            # Ensure rules field exists
            if 'rules' not in control:
                control['rules'] = []

            existing_rules = set(control['rules'])
            new_rules = rule_ids - existing_rules

            if merge_strategy == 'append':
                if new_rules:
                    if verbose:
                        print(f"  {normalized_id}: Adding {len(new_rules)} new rules")
                    # Add new rules, preserving existing order
                    control['rules'].extend(sorted(new_rules))
                    mapped_count += 1
                    changes_made = True

                    # Update status if it was 'pending'
                    if control.get('status') == 'pending':
                        control['status'] = 'automated'
                        changes_made = True

            elif merge_strategy == 'replace':
                sorted_rules = sorted(rule_ids)
                if control['rules'] != sorted_rules:
                    if verbose:
                        print(f"  {normalized_id}: Replacing with {len(sorted_rules)} rules")
                    control['rules'] = sorted_rules
                    mapped_count += 1
                    changes_made = True

                    # Update status
                    if sorted_rules:
                        control['status'] = 'automated'
                    changes_made = True

        print(f"  ✓ Mapped {mapped_count} controls")
        if unmapped_count > 0:
            print(f"  ! {unmapped_count} control references not found in control file")
            print(f"    (These may be control enhancements - run sync_nist.py to add them)")

        if changes_made:
            print("Saving updated control file...")
            temp_file = self.control_file.with_suffix('.yml.tmp')

            with open(temp_file, 'w', encoding='utf-8') as f:
                self.yaml.dump(control_data, f)

            temp_file.replace(self.control_file)
            print(f"  ✓ Saved to {self.control_file}")

        return changes_made


def main():
    """Main entry point."""
    import argparse

    # Print deprecation warning
    print("=" * 70, file=sys.stderr)
    print("⚠️  WARNING: This script is DEPRECATED!", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print("", file=sys.stderr)
    print("This script scans source rule.yml files which contain Jinja2 syntax", file=sys.stderr)
    print("that causes parsing errors. It is also 10x slower than the new workflow.", file=sys.stderr)
    print("", file=sys.stderr)
    print("INSTEAD, USE ONE OF THESE:", file=sys.stderr)
    print("  1. ./harvest_from_profile.sh rhel9 cis   # Profile-aware", file=sys.stderr)
    print("  2. ./harvest_built.sh rhel9              # All rules", file=sys.stderr)
    print("", file=sys.stderr)
    print("See BUILT_RULES_WORKFLOW.md for details.", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print("", file=sys.stderr)

    response = input("Continue anyway? [y/N] ")
    if response.lower() not in ['y', 'yes']:
        print("Aborted.", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(
        description='[DEPRECATED] Harvest NIST 800-53 mappings from rule.yml files'
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
        '--strategy',
        choices=['append', 'replace'],
        default='append',
        help='Merge strategy: append (add new rules) or replace (overwrite all rules)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without saving'
    )

    args = parser.parse_args()

    harvester = MappingHarvester(args.repo_root)

    try:
        # Step 1: Harvest mappings
        mappings = harvester.harvest_mappings(verbose=args.verbose)

        if not mappings:
            print("\nNo NIST references found in rules.", file=sys.stderr)
            return 1

        # Step 2: Apply to control file (unless dry-run)
        if args.dry_run:
            print("\nDRY RUN MODE - Showing what would be mapped:")
            for control_id, rules in sorted(mappings.items()):
                print(f"  {control_id}: {len(rules)} rules")
            return 0

        changed = harvester.apply_mappings_to_control_file(
            mappings,
            merge_strategy=args.strategy,
            verbose=args.verbose
        )

        if changed:
            print("\n✓ Harvest complete! Mappings applied to control file.")
            return 0
        else:
            print("\n✓ No changes needed - all mappings already exist.")
            return 0

    except Exception as e:
        print(f"\n✗ Harvest failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
