#!/usr/bin/env python3

"""
Test Profile Variable Selection

This test validates that profiles properly select variables for the rules they include.
When a rule uses a variable (as indicated in the rule-variable mapping), the profile
should also select that variable. If not, the rule will use the variable's default value,
which may not be the intended behavior.

The test emits warnings when a rule is selected but its variables are not.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Set, List, Tuple


class ProfileVariableChecker:
    """Check that profiles select appropriate variables for their rules."""

    def __init__(self, product: str, build_dir: Path):
        """
        Initialize the checker.

        Args:
            product: Product name (e.g., 'rhel10')
            build_dir: Path to the build directory
        """
        self.product = product
        self.build_dir = build_dir
        self.product_dir = build_dir / product

        # Load the rule-variable mapping
        self.mapping_file = self.product_dir / "rule_variable_mapping.json"
        self.rule_to_variables = self.load_mapping()

    def load_mapping(self) -> Dict[str, List[str]]:
        """
        Load the rule-variable mapping from JSON file.

        Returns:
            Dictionary mapping rule IDs to lists of variable IDs

        Raises:
            FileNotFoundError: If the mapping file doesn't exist
        """
        if not self.mapping_file.exists():
            raise FileNotFoundError(
                f"Rule-variable mapping file not found: {self.mapping_file}\n"
                f"This file should be generated during the build process."
            )

        with open(self.mapping_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_profile(self, profile_name: str) -> Tuple[Set[str], Set[str]]:
        """
        Load a profile and extract selected rules and variables.

        Args:
            profile_name: Profile name (without .profile extension)

        Returns:
            Tuple of (selected_rules, selected_variables)

        Raises:
            FileNotFoundError: If the profile file doesn't exist
        """
        profile_file = self.product_dir / "profiles" / f"{profile_name}.profile"

        if not profile_file.exists():
            raise FileNotFoundError(f"Profile not found: {profile_file}")

        with open(profile_file, 'r', encoding='utf-8') as f:
            profile_data = json.load(f)

        selections = profile_data.get('selections', [])

        selected_rules = set()
        selected_variables = set()

        for selection in selections:
            # Selections can be:
            # 1. Just the name: "rule_name" or "var_name"
            # 2. With value assignment: "var_name=value" or "sysctl_name_value=2"
            # 3. With property assignment: "rule_name.property=value"
            # Extract the base name without the assignment
            base_selection = selection.split('=')[0] if '=' in selection else selection

            # If it contains a dot, it's a rule property (e.g., "rule.role=unscored")
            if '.' in base_selection:
                # Extract the rule name before the dot
                rule_name = base_selection.split('.')[0]
                if rule_name in self.rule_to_variables:
                    selected_rules.add(rule_name)
            # If it starts with 'var_', check if it's a rule or variable
            elif base_selection.startswith('var_'):
                # Could be either a variable or a rule
                if base_selection in self.rule_to_variables:
                    # It's a rule
                    selected_rules.add(base_selection)
                else:
                    # It's a variable
                    selected_variables.add(base_selection)
            else:
                # Doesn't start with 'var_' and has no dot
                # Check if it's a known rule, otherwise assume it's a variable
                if base_selection in self.rule_to_variables:
                    selected_rules.add(base_selection)
                else:
                    # It's a variable (e.g., "sysctl_kernel_something_value=2")
                    selected_variables.add(base_selection)

        return selected_rules, selected_variables

    def check_profile(self, profile_name: str) -> List[Dict]:
        """
        Check a profile for rules with unselected variables.

        Args:
            profile_name: Profile name to check

        Returns:
            List of warning dictionaries containing:
                - profile: Profile name
                - rule: Rule ID
                - variable: Variable ID
                - message: Warning message
        """
        selected_rules, selected_variables = self.load_profile(profile_name)

        warnings = []

        for rule_id in selected_rules:
            if rule_id not in self.rule_to_variables:
                continue

            required_vars = self.rule_to_variables[rule_id]

            for var_id in required_vars:
                if var_id not in selected_variables:
                    warnings.append({
                        'profile': profile_name,
                        'rule': rule_id,
                        'variable': var_id,
                        'message': (
                            f"Rule '{rule_id}' uses variable '{var_id}' but "
                            f"the variable is not selected in profile '{profile_name}'. "
                            f"Default value will be used."
                        )
                    })

        return warnings

    def check_all_profiles(self) -> Dict[str, List[Dict]]:
        """
        Check all profiles in the product.

        Returns:
            Dictionary mapping profile names to lists of warnings
        """
        profiles_dir = self.product_dir / "profiles"

        if not profiles_dir.exists():
            raise FileNotFoundError(f"Profiles directory not found: {profiles_dir}")

        all_warnings = {}

        for profile_file in sorted(profiles_dir.glob("*.profile")):
            profile_name = profile_file.stem
            warnings = self.check_profile(profile_name)
            if warnings:
                all_warnings[profile_name] = warnings

        return all_warnings


def find_built_products(build_dir: Path) -> List[str]:
    """
    Find all products that have been built by looking for rule_variable_mapping.json files.

    Args:
        build_dir: Path to the build directory

    Returns:
        List of product names
    """
    products = []
    for mapping_file in build_dir.glob("*/rule_variable_mapping.json"):
        product = mapping_file.parent.name
        products.append(product)
    return sorted(products)


def main():
    parser = argparse.ArgumentParser(
        description='Test that profiles select appropriate variables for their rules',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--product', help='Product name (e.g., rhel10). If not specified, checks all built products.')
    parser.add_argument('--build-dir', required=True, help='Build directory path')
    parser.add_argument('--profile', help='Specific profile to check (optional, only valid with --product)')

    args = parser.parse_args()

    build_dir = Path(args.build_dir)

    # Determine which products to check
    if args.product:
        products_to_check = [args.product]
    else:
        products_to_check = find_built_products(build_dir)
        if not products_to_check:
            raise RuntimeError("No built products found (no rule_variable_mapping.json files)")

    # If checking a specific profile, we need a specific product
    if args.profile and not args.product:
        raise RuntimeError("--profile requires --product to be specified")

    # Check all products
    total_warnings = 0
    failed_products = []

    for product in products_to_check:
        try:
            checker = ProfileVariableChecker(product, build_dir)
        except FileNotFoundError as e:
            failed_products.append(product)
            print(f"Error for {product}: {e}", file=sys.stderr)
            continue

        if args.profile:
            # Check specific profile for this product
            try:
                warnings = checker.check_profile(args.profile)
            except FileNotFoundError as e:
                raise RuntimeError(f"Profile check failed: {e}")

            if warnings:
                print(f"[{product}] Profile '{args.profile}' has {len(warnings)} warning(s):")
                for warning in warnings:
                    print(f"  {warning['message']}")
            return 0
        else:
            # Check all profiles for this product
            try:
                all_warnings = checker.check_all_profiles()
            except FileNotFoundError as e:
                failed_products.append(product)
                print(f"Error for {product}: {e}", file=sys.stderr)
                continue

            if all_warnings:
                product_warnings = sum(len(w) for w in all_warnings.values())
                total_warnings += product_warnings
                print(f"[{product}] Found {product_warnings} warning(s) across {len(all_warnings)} profile(s):")
                for profile_name, warnings in sorted(all_warnings.items()):
                    print(f"  {profile_name}: {len(warnings)} warning(s)")
                    for warning in warnings:
                        print(f"    {warning['message']}")

    # Summary
    if failed_products:
        raise RuntimeError(f"Failed to check products: {', '.join(failed_products)}")

    if total_warnings > 0:
        print(f"\nTotal: {total_warnings} warning(s) across {len(products_to_check)} product(s)")
    else:
        print("All profiles passed: all rules have their variables selected")

    return 0


if __name__ == '__main__':
    sys.exit(main())
