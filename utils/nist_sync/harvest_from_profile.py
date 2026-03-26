#!/usr/bin/env python3
"""
Profile-Aware NIST 800-53 Mapping Harvester

This script extracts NIST 800-53 mappings ONLY for rules that are actually used in a
specific built profile. This creates focused, profile-specific control files without noise
from unused rules.

Workflow:
  1. Read built profile (JSON) to get list of selected rules
  2. Scan only those rule.yml files for NIST references
  3. Map only the active rules to controls

Example:
  # Map only rules used in CIS profile
  ./harvest_from_profile.py --profile build/rhel8/profiles/cis.profile

  # Create a product-specific NIST control file
  ./harvest_from_profile.py --profile build/rhel9/profiles/stig.profile \
                             --output controls/nist_rhel9_stig.yml
"""

import json
import sys
from pathlib import Path
from typing import Dict, Set, List, Optional

try:
    from ruamel.yaml import YAML
except ImportError:
    print("Error: ruamel.yaml is required. Install it with:", file=sys.stderr)
    print("  pip install ruamel.yaml", file=sys.stderr)
    sys.exit(1)


class ProfileAwareHarvester:
    """Harvests NIST mappings only for rules in a specific profile."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

        # Setup YAML parser
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.default_flow_style = False
        self.yaml.indent(mapping=2, sequence=4, offset=2)
        self.yaml.width = 4096

    def load_profile_selections(self, profile_path: Path) -> Set[str]:
        """
        Load the list of selected rules from a built profile.

        Args:
            profile_path: Path to built profile JSON file

        Returns:
            Set of rule IDs selected in the profile
        """
        if not profile_path.exists():
            print(f"Error: Profile not found: {profile_path}", file=sys.stderr)
            sys.exit(1)

        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in profile: {e}", file=sys.stderr)
            sys.exit(1)

        # Extract selections (rule IDs and variable assignments)
        selections_raw = profile_data.get('selections', [])

        # Filter out variable assignments (they contain '=')
        # Keep only rule IDs
        rule_ids = {
            sel for sel in selections_raw
            if '=' not in sel and not sel.startswith('!')
        }

        return rule_ids

    def load_profile_variables(self, profile_path: Path) -> Dict[str, str]:
        """
        Load variable assignments from a built profile.

        Args:
            profile_path: Path to built profile JSON file

        Returns:
            Dictionary mapping variable names to their values
        """
        if not profile_path.exists():
            print(f"Error: Profile not found: {profile_path}", file=sys.stderr)
            sys.exit(1)

        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in profile: {e}", file=sys.stderr)
            sys.exit(1)

        # Extract variable assignments (contain '=', not exclusions)
        selections_raw = profile_data.get('selections', [])

        variables = {}
        for sel in selections_raw:
            if '=' in sel and not sel.startswith('!'):
                var_name, var_value = sel.split('=', 1)
                variables[var_name] = var_value

        return variables

    def find_rule_file(self, rule_id: str, product: str) -> Optional[Path]:
        """
        Find the built rule JSON file for a given rule ID.

        Args:
            rule_id: The rule identifier
            product: Product name (e.g., 'rhel8')

        Returns:
            Path to rule JSON if found, None otherwise
        """
        # Use built rules from build/<product>/rules/
        build_dir = self.repo_root / "build" / product / "rules"
        
        if not build_dir.exists():
            return None
        
        rule_json = build_dir / f"{rule_id}.json"
        if rule_json.exists():
            return rule_json
        
        return None

    def extract_nist_references(self, rule_file: Path) -> Set[str]:
        """Extract NIST 800-53 control IDs from a built rule JSON file."""
        nist_refs = set()

        try:
            import json
            with open(rule_file, 'r', encoding='utf-8') as f:
                rule_data = json.load(f)

            # Look for references.nist field (it's a list in JSON)
            if 'references' in rule_data and 'nist' in rule_data['references']:
                nist_list = rule_data['references']['nist']
                if isinstance(nist_list, list):
                    nist_refs.update(nist_list)

        except Exception as e:
            print(f"Warning: Failed to parse {rule_file}: {e}", file=sys.stderr)

        return nist_refs

    def normalize_control_id(self, control_id: str) -> str:
        """Normalize NIST control ID to standard format."""
        import re

        # Convert to uppercase
        ctrl_id = control_id.upper().strip()

        # Handle legacy format like "CM-6A" -> "CM-6(A)"
        if re.match(r'^[A-Z]+-\d+[A-Z]$', ctrl_id):
            ctrl_id = ctrl_id[:-1] + '(' + ctrl_id[-1] + ')'

        return ctrl_id

    def harvest_from_profile(
        self,
        profile_path: Path,
        product: str,
        verbose: bool = False
    ) -> tuple[Dict[str, Set[str]], Dict[str, str]]:
        """
        Harvest NIST mappings and variables from the specified profile.

        Args:
            profile_path: Path to built profile JSON
            verbose: Enable verbose output

        Returns:
            Tuple of (control_to_rules mapping, variables dict)
        """
        print(f"Loading profile: {profile_path}")
        selected_rules = self.load_profile_selections(profile_path)
        profile_variables = self.load_profile_variables(profile_path)
        print(f"  Found {len(selected_rules)} selected rules")
        if profile_variables:
            print(f"  Found {len(profile_variables)} variable assignments")

        # Build mapping: control_id -> set of rule_ids
        control_to_rules: Dict[str, Set[str]] = {}
        rules_with_nist = 0
        rules_not_found = 0

        print("Harvesting NIST references from selected rules...")

        for rule_id in sorted(selected_rules):
            # Find rule file
            rule_file = self.find_rule_file(rule_id, product)

            if not rule_file:
                if verbose:
                    print(f"  Warning: Rule file not found for {rule_id}")
                rules_not_found += 1
                continue

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

        if rules_not_found > 0:
            print(f"  ! {rules_not_found} rules not found (may be from other products)")

        return control_to_rules, profile_variables

    def create_control_file_from_mappings(
        self,
        control_to_rules: Dict[str, Set[str]],
        variables: Dict[str, str],
        output_path: Path,
        profile_info: Optional[Dict] = None
    ):
        """
        Create a new NIST control file from harvested mappings.

        This creates a standalone control file containing only the controls
        that have rules in the specified profile.

        Args:
            control_to_rules: Mapping of control IDs to rule IDs
            variables: Dictionary of variable assignments from profile
            output_path: Where to write the control file
            profile_info: Optional metadata about the source profile
        """
        # Create control file structure
        control_data = {
            'policy': 'NIST 800-53 Revision 5',
            'title': 'NIST Special Publication 800-53 Revision 5',
            'id': output_path.stem if output_path.stem != 'tmp' else 'nist_800_53',
            'version': 'Revision 5',
            'source': 'https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final',
        }

        # Add profile metadata if provided
        if profile_info:
            control_data['notes'] = f"Generated from profile: {profile_info.get('title', 'Unknown')}"

        # Add levels
        control_data['levels'] = [
            {'id': 'low'},
            {'id': 'moderate'},
            {'id': 'high'}
        ]

        # Create controls list
        controls = []

        # Add a special control for variables if present
        if variables:
            var_selections = [f"{var_name}={var_value}" for var_name, var_value in sorted(variables.items())]
            controls.append({
                'id': 'VARIABLES',
                'title': 'Profile Variable Assignments',
                'rules': var_selections,
                'status': 'automated'
            })

        # Add NIST controls with rules
        for control_id, rule_ids in sorted(control_to_rules.items()):
            control = {
                'id': control_id,
                'rules': sorted(rule_ids),
                'status': 'automated'
            }
            controls.append(control)

        control_data['controls'] = controls

        # Write to file
        print(f"Writing control file: {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        temp_file = output_path.with_suffix('.yml.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            self.yaml.dump(control_data, f)

        temp_file.replace(output_path)
        print(f"  ✓ Saved {len(controls)} controls with mappings")
        if variables:
            print(f"  ✓ Saved {len(variables)} variable assignments")

    def apply_to_existing_control_file(
        self,
        control_to_rules: Dict[str, Set[str]],
        variables: Dict[str, str],
        control_file: Path,
        merge_strategy: str = 'append',
        verbose: bool = False
    ) -> bool:
        """
        Apply harvested mappings and variables to an existing control file.

        Only updates controls that exist in the file AND have rules in the profile.

        Args:
            control_to_rules: Mapping of control IDs to rule IDs
            variables: Dictionary of variable assignments from profile
            control_file: Path to existing control file
            merge_strategy: 'append' or 'replace'
            verbose: Enable verbose output

        Returns:
            True if changes were made
        """
        if not control_file.exists():
            print(f"Error: Control file not found: {control_file}", file=sys.stderr)
            return False

        print(f"Loading control file: {control_file}")
        with open(control_file, 'r', encoding='utf-8') as f:
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
                    print(f"  Warning: Control {normalized_id} not found in control file")
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
                    control['rules'].extend(sorted(new_rules))
                    mapped_count += 1
                    changes_made = True

                    # Update status if it was 'pending'
                    if control.get('status') == 'pending':
                        control['status'] = 'automated'

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

        print(f"  ✓ Mapped {mapped_count} controls")
        if unmapped_count > 0:
            print(f"  ! {unmapped_count} controls not found in control file")

        # Merge variables into VARIABLES control
        if variables:
            # Find or create VARIABLES control
            variables_control = None
            for ctrl in control_data['controls']:
                if ctrl['id'] == 'VARIABLES':
                    variables_control = ctrl
                    break

            if not variables_control:
                # Create new VARIABLES control
                variables_control = {
                    'id': 'VARIABLES',
                    'title': 'Profile Variable Assignments',
                    'rules': [],
                    'status': 'automated'
                }
                # Insert at the beginning
                control_data['controls'].insert(0, variables_control)

            # Ensure rules field exists
            if 'rules' not in variables_control:
                variables_control['rules'] = []

            # Convert variables dict to list of "var=value" strings
            new_var_selections = [f"{var_name}={var_value}" for var_name, var_value in sorted(variables.items())]

            new_vars_count = 0
            if merge_strategy == 'append':
                # Add new variables that don't exist
                existing_vars = set(variables_control['rules'])
                for var_sel in new_var_selections:
                    if var_sel not in existing_vars:
                        variables_control['rules'].append(var_sel)
                        new_vars_count += 1
                        changes_made = True
            elif merge_strategy == 'replace':
                if set(variables_control['rules']) != set(new_var_selections):
                    variables_control['rules'] = new_var_selections
                    new_vars_count = len(new_var_selections)
                    changes_made = True

            if new_vars_count > 0:
                print(f"  ✓ Merged {new_vars_count} variable assignments")

        if changes_made:
            print("Saving updated control file...")
            temp_file = control_file.with_suffix('.yml.tmp')

            with open(temp_file, 'w', encoding='utf-8') as f:
                self.yaml.dump(control_data, f)

            temp_file.replace(control_file)
            print(f"  ✓ Saved to {control_file}")

        return changes_made


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Harvest NIST 800-53 mappings from a specific built profile',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Harvest from CIS profile and update main control file
  %(prog)s --profile build/rhel8/profiles/cis.profile

  # Create a profile-specific control file
  %(prog)s --profile build/rhel9/profiles/stig.profile \\
           --output controls/nist_rhel9_stig.yml

  # Apply to existing control file with replace strategy
  %(prog)s --profile build/rhel8/profiles/cis.profile \\
           --control-file controls/nist_800_53.yml \\
           --strategy replace
        '''
    )
    parser.add_argument(
        '--profile',
        type=Path,
        required=True,
        help='Path to built profile JSON file (e.g., build/rhel8/profiles/cis.profile)'
    )
    parser.add_argument(
        '--repo-root',
        type=Path,
        default=Path(__file__).parent.parent.parent,
        help='Path to repository root (default: auto-detect)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Create new control file at this path (default: update controls/nist_800_53.yml)'
    )
    parser.add_argument(
        '--control-file',
        type=Path,
        help='Existing control file to update (default: controls/nist_800_53.yml)'
    )
    parser.add_argument(
        '--strategy',
        choices=['append', 'replace'],
        default='append',
        help='Merge strategy: append (add new rules) or replace (overwrite all rules)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without saving'
    )

    args = parser.parse_args()

    harvester = ProfileAwareHarvester(args.repo_root)

    try:
        # Step 1: Harvest mappings from profile
        # Extract product name from profile path (e.g., build/rhel8/profiles/cis.profile -> rhel8)
        product = args.profile.parts[-3] if len(args.profile.parts) >= 3 else "unknown"
        
        mappings, variables = harvester.harvest_from_profile(
            args.profile,
            product=product,
            verbose=args.verbose
        )

        if not mappings:
            print("\nNo NIST references found in profile rules.", file=sys.stderr)
            return 1

        # Dry-run mode
        if args.dry_run:
            print("\nDRY RUN MODE - Showing what would be mapped:")
            for control_id, rules in sorted(mappings.items()):
                print(f"  {control_id}: {len(rules)} rules")
            if variables:
                print(f"\nVariables: {len(variables)} assignments")
            return 0

        # Step 2: Either create new file or update existing
        if args.output:
            # Create new control file
            profile_data = None
            if args.profile.exists():
                with open(args.profile, 'r') as f:
                    profile_data = json.load(f)

            harvester.create_control_file_from_mappings(
                mappings,
                variables,
                args.output,
                profile_info=profile_data
            )
            print(f"\n✓ Created profile-specific control file: {args.output}")
            return 0

        else:
            # Update existing control file
            control_file = args.control_file or (args.repo_root / "controls" / "nist_800_53.yml")

            changed = harvester.apply_to_existing_control_file(
                mappings,
                variables,
                control_file,
                merge_strategy=args.strategy,
                verbose=args.verbose
            )

            if changed:
                print("\n✓ Profile-aware harvest complete! Mappings applied to control file.")
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
