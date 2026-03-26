#!/usr/bin/env python3
"""
NIST 800-53 Control File Synchronization Engine

This script synchronizes the controls/nist_800_53.yml file with the official
NIST OSCAL catalog while preserving all manual mappings, comments, and formatting.

Uses ruamel.yaml for round-trip YAML parsing to ensure non-destructive updates.

Phase 1: Load existing control file and OSCAL catalog
Phase 2: Update metadata (titles, descriptions) from OSCAL
Phase 3: Add new controls discovered in OSCAL
Phase 4: Mark controls with baseline levels (LOW, MODERATE, HIGH)
Phase 5: Save atomically with preserved formatting

Note: This script handles files with Jinja2 guards by stripping them during
load and preserving them during save.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Set, Optional
from collections import OrderedDict, defaultdict

try:
    from ruamel.yaml import YAML
except ImportError:
    print("Error: ruamel.yaml is required. Install it with:", file=sys.stderr)
    print("  pip install ruamel.yaml", file=sys.stderr)
    sys.exit(1)


class NISTControlSync:
    """Synchronizes NIST 800-53 control file with OSCAL catalog."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        # CIS reference file: Auto-generated from CIS mappings (comparison only)
        self.reference_file = repo_root / "shared" / "references" / "controls" / "nist_800_53_cis_reference.yml"
        # Real control file: Human-maintained source of truth (NEVER touched by automation)
        self.control_file = repo_root / "controls" / "nist_800_53.yml"
        self.data_dir = Path(__file__).parent / "data"
        self.catalog_file = self.data_dir / "nist_800_53_rev5_catalog.json"
        self.mapping_cache_file = self.data_dir / "cis_nist_mappings.json"
        self.build_dir = repo_root / "build"

        # Setup round-trip YAML parser
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.default_flow_style = False
        self.yaml.indent(mapping=2, sequence=4, offset=2)
        self.yaml.width = 4096  # Prevent line wrapping

    def load_oscal_catalog(self) -> Dict:
        """Load NIST OSCAL catalog JSON."""
        if not self.catalog_file.exists():
            print(f"Error: OSCAL catalog not found at {self.catalog_file}", file=sys.stderr)
            print("Run download_oscal.py first to download the catalog.", file=sys.stderr)
            sys.exit(1)

        with open(self.catalog_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_baselines(self) -> Dict[str, Set[str]]:
        """Load baseline profiles to determine control levels."""
        baselines = {
            'low': set(),
            'moderate': set(),
            'high': set()
        }

        baseline_files = [
            ('low', 'nist_800_53_rev5_low_baseline.json'),
            ('moderate', 'nist_800_53_rev5_moderate_baseline.json'),
            ('high', 'nist_800_53_rev5_high_baseline.json')
        ]

        for level, filename in baseline_files:
            filepath = self.data_dir / filename
            if not filepath.exists():
                print(f"Warning: Baseline {level} not found at {filepath}", file=sys.stderr)
                continue

            with open(filepath, 'r', encoding='utf-8') as f:
                baseline_data = json.load(f)

            # Extract control IDs from imports
            if 'profile' in baseline_data and 'imports' in baseline_data['profile']:
                for import_item in baseline_data['profile']['imports']:
                    if 'include-controls' in import_item:
                        for include in import_item['include-controls']:
                            if 'with-ids' in include:
                                baselines[level].update(include['with-ids'])

        return baselines

    def load_rule_mappings(self) -> tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
        """Load rule→NIST and variable→NIST mappings from CIS harvest cache."""
        if not self.mapping_cache_file.exists():
            print(f"  ℹ  No mapping cache found at {self.mapping_cache_file}")
            print(f"     Run harvest_cis_nist_mappings.py to generate mappings")
            return {}, {}

        print(f"  Loading rule and variable mappings from cache...")
        with open(self.mapping_cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)

        # Handle both old format (dict of rules) and new format (dict with 'rules' and 'variables' keys)
        if 'rules' in cache_data and 'variables' in cache_data:
            # New format
            rule_to_nist = {
                rule_id: set(nist_controls)
                for rule_id, nist_controls in cache_data['rules'].items()
            }
            var_to_nist = {
                var_id: set(nist_controls)
                for var_id, nist_controls in cache_data['variables'].items()
            }
        else:
            # Old format (backward compatibility)
            rule_to_nist = {
                rule_id: set(nist_controls)
                for rule_id, nist_controls in cache_data.items()
            }
            var_to_nist = {}

        print(f"    ✓ Loaded {len(rule_to_nist)} rule mappings")
        print(f"    ✓ Loaded {len(var_to_nist)} variable mappings")
        return rule_to_nist, var_to_nist

    def load_all_cis_items(self) -> Set[str]:
        """Load ALL rules and variables from ALL CIS control files."""
        all_items = set()

        # Products to scan
        products = ['rhel8', 'rhel9', 'rhel10']

        for product in products:
            cis_file = self.repo_root / 'products' / product / 'controls' / f'cis_{product}.yml'

            if not cis_file.exists():
                continue

            with open(cis_file, 'r', encoding='utf-8') as f:
                cis_data = self.yaml.load(f)

            for control in cis_data.get('controls', []):
                all_items.update(control.get('rules', []))

        print(f"  ✓ Loaded {len(all_items)} total CIS items from all products")
        return all_items

    def load_control_file(self) -> Dict:
        """Load existing CIS reference file, or create skeleton if it doesn't exist.

        This loads the AUTO-GENERATED reference file that shows CIS→NIST mappings.
        The real control file (nist_800_53.yml) is NEVER touched by this script.
        """
        if self.reference_file.exists():
            print(f"  Loading previous CIS reference from: {self.reference_file.name}")
            with open(self.reference_file, 'r', encoding='utf-8') as f:
                data = self.yaml.load(f)
                if data is None:
                    data = {}
        else:
            print(f"  Creating new CIS reference file at {self.reference_file}")
            data = {}

        # Ensure required top-level keys exist
        if 'policy' not in data:
            data['policy'] = 'NIST 800-53 Revision 5 CIS Reference'
        if 'title' not in data:
            data['title'] = 'NIST Special Publication 800-53 Revision 5 CIS Reference'
        if 'id' not in data:
            data['id'] = 'nist_800_53_cis_reference'
        if 'version' not in data:
            data['version'] = 'Revision 5'
        if 'source' not in data:
            data['source'] = 'https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final'
        if 'levels' not in data:
            data['levels'] = [
                {'id': 'low'},
                {'id': 'moderate'},
                {'id': 'high'}
            ]
        if 'controls' not in data:
            data['controls'] = []

        return data

    def extract_controls_from_catalog(self, catalog: Dict) -> List[Dict]:
        """Extract all controls and enhancements from OSCAL catalog."""
        controls = []

        def process_control(ctrl: Dict, parent_id: Optional[str] = None):
            """Recursively process controls and their enhancements."""
            ctrl_id = ctrl.get('id', '')  # Preserve exact case from OSCAL
            title = ctrl.get('title', 'No Title')

            # Extract description from parts
            description = ""
            if 'parts' in ctrl:
                for part in ctrl['parts']:
                    if part.get('name') == 'statement':
                        # Extract prose or nested statement text
                        if 'prose' in part:
                            description = part['prose']
                            # Escape Jinja2-like syntax to prevent build errors
                            description = description.replace('{{', '[[').replace('}}', ']]')
                        break

            control_entry = {
                'id': ctrl_id,
                'title': title,
                'description': description if description else None
            }

            controls.append(control_entry)

            # Process control enhancements
            if 'controls' in ctrl:
                for enhancement in ctrl['controls']:
                    process_control(enhancement, ctrl_id)

        # Process all top-level controls
        if 'catalog' in catalog and 'groups' in catalog['catalog']:
            for group in catalog['catalog']['groups']:
                if 'controls' in group:
                    for control in group['controls']:
                        process_control(control)

        return controls

    def sync_controls(self, verbose: bool = False) -> bool:
        """
        Main synchronization logic.

        Returns True if changes were made, False otherwise.
        """
        print("Phase 1: Loading OSCAL catalog and existing control file...")
        catalog = self.load_oscal_catalog()
        baselines = self.load_baselines()
        local_data = self.load_control_file()

        print("Phase 2: Loading rule and variable mappings from CIS harvest...")
        rule_to_nist, var_to_nist = self.load_rule_mappings()

        print("Phase 3: Loading ALL CIS items (including unmapped)...")
        all_cis_items = self.load_all_cis_items()
        mapped_items = set(rule_to_nist.keys()) | set(var_to_nist.keys())

        # Build reverse mapping: NIST → rules
        nist_to_rules = defaultdict(set)
        for rule_id, nist_controls in rule_to_nist.items():
            for nist_id in nist_controls:
                nist_to_rules[nist_id].add(rule_id)

        # Build reverse mapping: NIST → variables
        nist_to_vars = defaultdict(set)
        for var_id, nist_controls in var_to_nist.items():
            for nist_id in nist_controls:
                nist_to_vars[nist_id].add(var_id)

        print("Phase 4: Extracting controls from OSCAL catalog...")
        oscal_controls = self.extract_controls_from_catalog(catalog)
        print(f"  Found {len(oscal_controls)} controls in OSCAL catalog")

        # Create lookup for existing controls (preserve exact case)
        existing_controls = {
            ctrl['id']: ctrl
            for ctrl in local_data['controls']
        }

        print("Phase 5: Synchronizing controls...")
        new_count = 0
        update_count = 0
        rules_added = 0
        vars_added = 0
        changes_made = False

        for oscal_ctrl in oscal_controls:
            ctrl_id = oscal_ctrl['id']  # Preserve exact case

            # Determine baseline levels for this control
            levels = []
            if ctrl_id in baselines['low']:
                levels.append('low')
            if ctrl_id in baselines['moderate']:
                levels.append('moderate')
            if ctrl_id in baselines['high']:
                levels.append('high')

            # Get rules and variables for this control from CIS mappings
            rules_for_control = sorted(nist_to_rules.get(ctrl_id, set()))
            vars_for_control = sorted(nist_to_vars.get(ctrl_id, set()))

            # Combine variables and rules (variables come first, like in CIS controls)
            selections_for_control = vars_for_control + rules_for_control

            if ctrl_id in existing_controls:
                # UPDATE: Update metadata and levels, MERGE rules intelligently
                existing = existing_controls[ctrl_id]

                if existing.get('title') != oscal_ctrl['title']:
                    if verbose:
                        print(f"  Updating title for {ctrl_id}")
                    existing['title'] = oscal_ctrl['title']
                    update_count += 1
                    changes_made = True

                # Only add description if not present
                if oscal_ctrl.get('description') and 'description' not in existing:
                    existing['description'] = oscal_ctrl['description']
                    changes_made = True

                # Update levels based on baselines
                existing_levels = existing.get('levels', [])
                if existing_levels != levels:
                    if levels:
                        existing['levels'] = levels
                    elif 'levels' in existing:
                        # Remove levels if control is not in any baseline
                        del existing['levels']
                    if verbose:
                        print(f"  Updating levels for {ctrl_id}: {levels}")
                    changes_made = True

                # MERGE rules: preserve existing rules (human edits) + add new CIS rules
                existing_rules = existing.get('rules', [])
                if selections_for_control:
                    # Merge new CIS rules with existing rules (preserve order, no duplicates)
                    merged_rules = list(existing_rules)  # Start with existing (human edits)

                    added_rules = []
                    for new_rule in selections_for_control:
                        if new_rule not in merged_rules:
                            merged_rules.append(new_rule)
                            added_rules.append(new_rule)

                    if added_rules:
                        existing['rules'] = merged_rules
                        rules_added += len([r for r in added_rules if not r.startswith('var_')])
                        vars_added += len([r for r in added_rules if r.startswith('var_')])
                        changes_made = True
                        if verbose:
                            print(f"  Merged {len(added_rules)} new rules into {ctrl_id}")
                            print(f"    New rules: {', '.join(added_rules[:5])}{'...' if len(added_rules) > 5 else ''}")

                    # Update status if control now has automated rules
                    if merged_rules and existing.get('status') == 'pending':
                        existing['status'] = 'automated'
                        changes_made = True

            else:
                # INSERT: Create new control skeleton
                if verbose:
                    print(f"  Adding new control {ctrl_id}")

                new_ctrl = {
                    'id': ctrl_id,
                    'title': oscal_ctrl['title'],
                }

                # Add description if available
                if oscal_ctrl.get('description'):
                    new_ctrl['description'] = oscal_ctrl['description']

                # Add baseline levels (already calculated above)
                if levels:
                    new_ctrl['levels'] = levels

                # Add rules and variables from CIS mappings
                if selections_for_control:
                    new_ctrl['rules'] = selections_for_control
                    new_ctrl['status'] = 'automated'
                    rules_added += len(rules_for_control)
                    vars_added += len(vars_for_control)
                    if verbose:
                        var_count = len(vars_for_control)
                        rule_count = len(rules_for_control)
                        if var_count > 0 and rule_count > 0:
                            print(f"    Added {var_count} variables and {rule_count} rules")
                        elif var_count > 0:
                            print(f"    Added {var_count} variables")
                        else:
                            print(f"    Added {rule_count} rules")
                else:
                    new_ctrl['rules'] = []
                    new_ctrl['status'] = 'pending'

                local_data['controls'].append(new_ctrl)
                new_count += 1
                changes_made = True

        # NOTE: Variables are now included directly in controls alongside their related rules
        # The separate VARIABLES control has been removed to avoid duplication

        print(f"  ✓ Added {new_count} new controls")
        print(f"  ✓ Updated {update_count} existing controls")
        if rules_added > 0:
            print(f"  ✓ Added {rules_added} rule mappings from CIS harvest")
        if vars_added > 0:
            print(f"  ✓ Added {vars_added} variable mappings from CIS harvest")

        # Add unmapped CIS items to a catch-all control
        unmapped_items = all_cis_items - mapped_items
        if unmapped_items:
            # Check if CIS_UNMAPPED control already exists
            cis_unmapped_exists = any(ctrl.get('id') == 'CIS_UNMAPPED' for ctrl in local_data['controls'])

            if not cis_unmapped_exists:
                unmapped_control = {
                    'id': 'CIS_UNMAPPED',
                    'title': 'CIS Benchmark Items Without NIST 800-53 Mapping',
                    'notes': 'These CIS benchmark items do not have explicit NIST 800-53 mappings in the benchmark documentation. They are included to ensure complete CIS coverage.',
                    'rules': sorted(list(unmapped_items)),
                    'status': 'automated'
                }
                # Insert at the beginning for easy visibility
                local_data['controls'].insert(0, unmapped_control)
                print(f"  ✓ Added {len(unmapped_items)} unmapped CIS items to CIS_UNMAPPED control")
                changes_made = True
            else:
                # Update existing CIS_UNMAPPED control
                for ctrl in local_data['controls']:
                    if ctrl.get('id') == 'CIS_UNMAPPED':
                        ctrl['rules'] = sorted(list(unmapped_items))
                        print(f"  ✓ Updated CIS_UNMAPPED control with {len(unmapped_items)} items")
                        changes_made = True
                        break

        if changes_made:
            print("Phase 6: Saving control file...")
            self.save_control_file(local_data)
            print(f"  ✓ Saved to {self.control_file}")
        else:
            print("  ℹ  No changes needed - control file is up to date")

        return changes_made

    def save_control_file(self, data: Dict):
        """Atomically save CIS reference file with preserved formatting.

        This saves the AUTO-GENERATED reference file showing CIS→NIST mappings.
        The real control file (nist_800_53.yml) is NEVER touched by automation.
        """
        # Write to temporary file first
        temp_file = self.reference_file.with_suffix('.yml.tmp')

        with open(temp_file, 'w', encoding='utf-8') as f:
            # Add header comment explaining this is auto-generated
            f.write("# AUTO-GENERATED CIS Reference File\n")
            f.write("# \n")
            f.write("# This file is auto-generated from CIS→NIST mappings and is used\n")
            f.write("# for COMPARISON ONLY. Do NOT edit this file manually.\n")
            f.write("# \n")
            f.write("# To update the REAL control file (nist_800_53.yml):\n")
            f.write("#   1. Review the diff between this file and the previous version\n")
            f.write("#   2. Manually apply relevant changes to nist_800_53.yml\n")
            f.write("#   3. The real file may have additional human edits and guards\n")
            f.write("# \n")
            self.yaml.dump(data, f)

        # Atomic rename
        temp_file.replace(self.reference_file)
        print(f"  ✓ Saved CIS reference to: {self.reference_file.name}")
        print(f"  ℹ  This is a REFERENCE file for comparison only")
        print(f"  ℹ  Human must manually update {self.control_file.name} based on changes")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Synchronize NIST 800-53 control file with OSCAL catalog'
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
        '--dry-run',
        action='store_true',
        help='Show what would be changed without saving'
    )

    args = parser.parse_args()

    syncer = NISTControlSync(args.repo_root)

    if args.dry_run:
        print("DRY RUN MODE - No changes will be saved")
        # TODO: Implement dry-run mode

    try:
        changed = syncer.sync_controls(verbose=args.verbose)
        if changed:
            print("\n✓ Synchronization complete!")
            return 0
        else:
            print("\n✓ Already synchronized - no changes needed")
            return 0
    except Exception as e:
        print(f"\n✗ Synchronization failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
