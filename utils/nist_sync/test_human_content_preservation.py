#!/usr/bin/env python3
"""
Integration test for NIST 800-53 control file synchronization.

Test Scenario:
1. Generate initial nist_800_53.yml from CIS mappings
2. Human manually adds rules to a NIST control
3. CIS benchmark mapping is updated (new rules added)
4. Regenerate nist_800_53.yml
5. Verify both human additions and new CIS mappings are present

This validates that sync_nist.py preserves manual edits while incorporating
upstream changes from the OSCAL catalog and CIS mappings.
"""

import json
import tempfile
import shutil
from pathlib import Path
from ruamel.yaml import YAML
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from sync_nist import NISTControlSync


class TestHumanContentPreservation:
    """Test suite for human content preservation during sync."""

    def __init__(self):
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.default_flow_style = False
        self.yaml.indent(mapping=2, sequence=4, offset=2)
        self.yaml.width = 4096

    def create_test_environment(self) -> Path:
        """Create a temporary test repository structure."""
        temp_dir = Path(tempfile.mkdtemp(prefix='nist_sync_test_'))

        # Create directory structure
        (temp_dir / "controls").mkdir()
        (temp_dir / "build").mkdir()
        (temp_dir / "products" / "rhel9" / "profiles").mkdir(parents=True)

        data_dir = temp_dir / "utils" / "nist_sync" / "data"
        data_dir.mkdir(parents=True)

        return temp_dir

    def create_oscal_catalog(self, data_dir: Path):
        """Create a minimal OSCAL catalog for testing."""
        catalog = {
            "catalog": {
                "uuid": "test-uuid",
                "metadata": {
                    "title": "NIST SP 800-53 Rev 5 Test Catalog",
                    "version": "5.1.1"
                },
                "groups": [
                    {
                        "id": "ac",
                        "title": "Access Control",
                        "controls": [
                            {
                                "id": "ac-2",
                                "title": "Account Management",
                                "parts": [
                                    {
                                        "id": "ac-2_smt",
                                        "name": "statement",
                                        "prose": "Manage system accounts..."
                                    }
                                ]
                            },
                            {
                                "id": "ac-3",
                                "title": "Access Enforcement",
                                "parts": [
                                    {
                                        "id": "ac-3_smt",
                                        "name": "statement",
                                        "prose": "Enforce approved authorizations..."
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "id": "au",
                        "title": "Audit and Accountability",
                        "controls": [
                            {
                                "id": "au-2",
                                "title": "Event Logging",
                                "parts": [
                                    {
                                        "id": "au-2_smt",
                                        "name": "statement",
                                        "prose": "Identify the types of events..."
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        }

        # Write catalog
        catalog_file = data_dir / "nist_800_53_rev5_catalog.json"
        with open(catalog_file, 'w') as f:
            json.dump(catalog, f, indent=2)

    def create_initial_cis_mappings(self, data_dir: Path):
        """Create initial CIS→NIST mappings (simulating Phase 1)."""
        mappings = {
            "rules": {
                "account_disable_post_pw_expiration": ["ac-2"],
                "accounts_password_minlen_login_defs": ["ac-2"],
                "audit_rules_login_events": ["au-2"],
            },
            "variables": {
                "var_password_pam_minlen": ["ac-2"]
            }
        }

        mapping_file = data_dir / "cis_nist_mappings.json"
        with open(mapping_file, 'w') as f:
            json.dump(mappings, f, indent=2)

    def create_updated_cis_mappings(self, data_dir: Path):
        """Create updated CIS→NIST mappings (simulating new CIS benchmark)."""
        # Add new rules to existing controls
        mappings = {
            "rules": {
                # Original mappings
                "account_disable_post_pw_expiration": ["ac-2"],
                "accounts_password_minlen_login_defs": ["ac-2"],
                "audit_rules_login_events": ["au-2"],
                # NEW rules from updated CIS benchmark
                "accounts_maximum_age_login_defs": ["ac-2"],
                "accounts_password_pam_retry": ["ac-2"],
                "audit_rules_privileged_commands": ["au-2"],
                "file_permissions_var_log_audit": ["au-2"],
            },
            "variables": {
                "var_password_pam_minlen": ["ac-2"],
                # NEW variable
                "var_accounts_maximum_age_login_defs": ["ac-2"]
            }
        }

        mapping_file = data_dir / "cis_nist_mappings.json"
        with open(mapping_file, 'w') as f:
            json.dump(mappings, f, indent=2)

    def create_cis_profiles(self, repo_root: Path):
        """Create minimal CIS profiles for testing."""
        # Create RHEL 9 CIS profile
        cis_profile = {
            "documentation_complete": True,
            "title": "CIS Red Hat Enterprise Linux 9 Benchmark",
            "platform": "rhel9",
            "selections": [
                "account_disable_post_pw_expiration",
                "accounts_password_minlen_login_defs",
                "audit_rules_login_events",
                "var_password_pam_minlen=14"
            ]
        }

        profile_path = repo_root / "products" / "rhel9" / "profiles" / "cis.profile"
        with open(profile_path, 'w') as f:
            self.yaml.dump(cis_profile, f)

    def add_human_edits(self, source_file: Path):
        """Simulate human adding rules to NIST controls."""
        print("  → Simulating human edits to control source file...")

        with open(source_file, 'r') as f:
            data = self.yaml.load(f)

        # Find ac-2 control and add human-curated rules
        for control in data.get('controls', []):
            if control.get('id') == 'ac-2':
                if 'rules' not in control:
                    control['rules'] = []

                # Human manually adds these rules (not from CIS)
                human_added_rules = [
                    "accounts_password_pam_unix_remember",  # Human addition 1
                    "accounts_logon_fail_delay",             # Human addition 2
                ]

                # Add at the beginning to test ordering preservation
                for rule in reversed(human_added_rules):
                    if rule not in control['rules']:
                        control['rules'].insert(0, rule)

                # Add a note from human
                control['notes'] = "Human note: Additional password policy rules added for enhanced security"

                print(f"     Added human rules to ac-2: {human_added_rules}")
                break

        # Also add a completely new control that's not in OSCAL (human-created)
        data['controls'].append({
            'id': 'CUSTOM-1',
            'title': 'Custom Security Control',
            'notes': 'This is a human-added custom control not in NIST catalog',
            'rules': [
                'custom_security_rule_1',
                'custom_security_rule_2'
            ],
            'status': 'manual'
        })

        print("     Added custom control: CUSTOM-1")

        # Save with human edits
        with open(source_file, 'w') as f:
            self.yaml.dump(data, f)

    def verify_results(self, control_file: Path) -> bool:
        """Verify that both human additions and new CIS mappings are present."""
        print("\n  → Verifying synchronized control file...")

        with open(control_file, 'r') as f:
            data = self.yaml.load(f)

        results = {
            'ac-2_has_human_rules': False,
            'ac-2_has_original_cis_rules': False,
            'ac-2_has_new_cis_rules': False,
            'ac-2_has_human_note': False,
            'custom_control_preserved': False,
            'au-2_has_new_rules': False
        }

        # Check ac-2 control
        for control in data.get('controls', []):
            if control.get('id') == 'ac-2':
                rules = control.get('rules', [])

                # Check human-added rules are preserved
                human_rules = [
                    'accounts_password_pam_unix_remember',
                    'accounts_logon_fail_delay'
                ]
                if all(rule in rules for rule in human_rules):
                    results['ac-2_has_human_rules'] = True
                    print(f"     ✓ Human-added rules preserved in AC-2")

                # Check original CIS rules are still there
                original_cis_rules = [
                    'account_disable_post_pw_expiration',
                    'accounts_password_minlen_login_defs'
                ]
                if all(rule in rules for rule in original_cis_rules):
                    results['ac-2_has_original_cis_rules'] = True
                    print(f"     ✓ Original CIS rules preserved in AC-2")

                # Check new CIS rules were added
                new_cis_rules = [
                    'accounts_maximum_age_login_defs',
                    'accounts_password_pam_retry'
                ]
                if all(rule in rules for rule in new_cis_rules):
                    results['ac-2_has_new_cis_rules'] = True
                    print(f"     ✓ New CIS rules added to AC-2")

                # Check human note is preserved
                if 'notes' in control and 'Human note' in control['notes']:
                    results['ac-2_has_human_note'] = True
                    print(f"     ✓ Human note preserved in AC-2")

                print(f"     AC-2 total rules: {len(rules)}")

            elif control.get('id') == 'au-2':
                rules = control.get('rules', [])

                # Check new au-2 rules were added
                new_au2_rules = [
                    'audit_rules_privileged_commands',
                    'file_permissions_var_log_audit'
                ]
                if all(rule in rules for rule in new_au2_rules):
                    results['au-2_has_new_rules'] = True
                    print(f"     ✓ New CIS rules added to au-2")

                print(f"     au-2 total rules: {len(rules)}")

            elif control.get('id') == 'CUSTOM-1':
                results['custom_control_preserved'] = True
                print(f"     ✓ Human-created custom control preserved")

        # Print summary
        print(f"\n  Results Summary:")
        all_passed = all(results.values())

        for check, passed in results.items():
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"    {status}: {check}")

        return all_passed

    def run_test(self):
        """Run the complete integration test."""
        print("=" * 70)
        print("Integration Test: Human Content Preservation During Sync")
        print("=" * 70)

        temp_repo = None
        try:
            # Phase 1: Setup test environment
            print("\n[Phase 1] Creating test environment...")
            temp_repo = self.create_test_environment()
            data_dir = temp_repo / "utils" / "nist_sync" / "data"

            # Copy sync_nist.py to temp repo
            shutil.copy(Path(__file__).parent / "sync_nist.py",
                       temp_repo / "utils" / "nist_sync" / "sync_nist.py")

            print(f"  Test repository: {temp_repo}")

            # Phase 2: Create initial data
            print("\n[Phase 2] Creating initial OSCAL catalog and CIS mappings...")
            self.create_oscal_catalog(data_dir)
            self.create_initial_cis_mappings(data_dir)
            self.create_cis_profiles(temp_repo)
            print("  ✓ Initial data created")

            # Phase 3: Generate initial control source file
            print("\n[Phase 3] Generating initial nist_800_53.yml.source...")
            syncer = NISTControlSync(temp_repo)
            syncer.sync_controls(verbose=False)
            source_file = temp_repo / "controls" / "nist_800_53.yml.source"
            print(f"  ✓ Initial control source file generated: {source_file}")

            # Phase 4: Human edits
            print("\n[Phase 4] Simulating human edits to control source file...")
            self.add_human_edits(source_file)
            print("  ✓ Human edits applied")

            # Phase 5: Update CIS mappings (new benchmark version)
            print("\n[Phase 5] Updating CIS mappings (simulating new benchmark)...")
            self.create_updated_cis_mappings(data_dir)
            print("  ✓ CIS mappings updated with new rules")

            # Phase 6: Re-synchronize
            print("\n[Phase 6] Re-synchronizing control file...")
            syncer = NISTControlSync(temp_repo)
            syncer.sync_controls(verbose=False)
            print("  ✓ Control file re-synchronized")

            # Phase 7: Verify results
            print("\n[Phase 7] Verifying results...")
            all_passed = self.verify_results(source_file)

            if all_passed:
                print("\n" + "=" * 70)
                print("TEST PASSED: All checks successful! ✓")
                print("=" * 70)
                return 0
            else:
                print("\n" + "=" * 70)
                print("TEST FAILED: Some checks did not pass ✗")
                print("=" * 70)
                return 1

        except Exception as e:
            print(f"\n✗ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return 1

        finally:
            # Cleanup
            if temp_repo and temp_repo.exists():
                print(f"\n[Cleanup] Removing test repository: {temp_repo}")
                shutil.rmtree(temp_repo)


def main():
    """Main entry point."""
    test = TestHumanContentPreservation()
    return test.run_test()


if __name__ == '__main__':
    sys.exit(main())
