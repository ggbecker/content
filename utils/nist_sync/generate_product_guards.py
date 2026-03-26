#!/usr/bin/env python3
"""
Product-Aware Jinja2 Guard Generator for Control Files

This script analyzes which rules are available in which products and generates
Jinja2-guarded selections in control files to prevent referencing rules that
don't exist for a specific product.

Workflow:
  1. Scan all built profiles for each product
  2. Determine which rules exist in which products
  3. Generate Jinja2 guards in control file selections

Example Output:
    controls:
      - id: AC-2
        rules:
          {{%- if product in ["rhel8", "rhel9"] %}}
          - account_disable_post_pw_expiration
          {{%- endif %}}
          {{%- if product in ["ocp4"] %}}
          - ocp_idp_no_htpasswd
          {{%- endif %}}

This prevents build errors when a product tries to use a rule that doesn't exist.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Set, List, Optional
from collections import defaultdict

try:
    from ruamel.yaml import YAML
except ImportError:
    print("Error: ruamel.yaml is required. Install it with:", file=sys.stderr)
    print("  pip install ruamel.yaml", file=sys.stderr)
    sys.exit(1)


class ProductGuardGenerator:
    """Generates product-aware guards for control file selections."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.build_dir = repo_root / "build"

        # Setup YAML parser
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.default_flow_style = False
        self.yaml.indent(mapping=2, sequence=4, offset=2)
        self.yaml.width = 4096

    def find_built_products(self) -> List[str]:
        """Find all products that have been built."""
        if not self.build_dir.exists():
            print(f"Error: Build directory not found: {self.build_dir}", file=sys.stderr)
            print("Run ./build_product first to generate builds", file=sys.stderr)
            sys.exit(1)

        products = []
        for product_dir in self.build_dir.iterdir():
            if product_dir.is_dir() and (product_dir / "profiles").exists():
                products.append(product_dir.name)

        return sorted(products)

    def scan_product_profiles(self, product: str) -> Set[str]:
        """
        Scan all profiles for a product and collect all selected rules.

        Args:
            product: Product name (e.g., 'rhel8', 'ocp4')

        Returns:
            Set of all rule IDs used across all profiles for this product
        """
        profiles_dir = self.build_dir / product / "profiles"

        if not profiles_dir.exists():
            return set()

        all_rules = set()

        for profile_file in profiles_dir.glob("*.profile"):
            try:
                with open(profile_file, 'r', encoding='utf-8') as f:
                    profile_data = json.load(f)

                selections = profile_data.get('selections', [])

                # Filter out variable assignments and exclusions
                rule_ids = {
                    sel for sel in selections
                    if '=' not in sel and not sel.startswith('!')
                }

                all_rules.update(rule_ids)

            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Failed to read {profile_file}: {e}", file=sys.stderr)

        return all_rules

    def scan_product_variables(self, product: str) -> Dict[str, str]:
        """
        Scan all profiles for a product and collect all variable assignments.

        Args:
            product: Product name (e.g., 'rhel8', 'ocp4')

        Returns:
            Dictionary mapping variable names to their values
        """
        profiles_dir = self.build_dir / product / "profiles"

        if not profiles_dir.exists():
            return {}

        all_variables = {}

        for profile_file in profiles_dir.glob("*.profile"):
            try:
                with open(profile_file, 'r', encoding='utf-8') as f:
                    profile_data = json.load(f)

                selections = profile_data.get('selections', [])

                # Extract variable assignments (contain '=', not exclusions)
                for sel in selections:
                    if '=' in sel and not sel.startswith('!'):
                        var_name, var_value = sel.split('=', 1)
                        # Use the value from first profile that has it
                        # (could be extended to check for conflicts)
                        if var_name not in all_variables:
                            all_variables[var_name] = var_value

            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Failed to read {profile_file}: {e}", file=sys.stderr)

        return all_variables

    def build_rule_to_products_map(
        self,
        products: List[str],
        verbose: bool = False
    ) -> Dict[str, Set[str]]:
        """
        Build a mapping of rule IDs to the products they appear in.

        Args:
            products: List of product names to scan
            verbose: Enable verbose output

        Returns:
            Dictionary mapping rule_id -> set of products
        """
        print("Scanning built profiles for product availability...")

        rule_to_products = defaultdict(set)

        for product in products:
            if verbose:
                print(f"  Scanning {product}...")

            rules = self.scan_product_profiles(product)

            if verbose:
                print(f"    Found {len(rules)} rules")

            for rule_id in rules:
                rule_to_products[rule_id].add(product)

        print(f"  ✓ Scanned {len(products)} products")
        print(f"  ✓ Found {len(rule_to_products)} unique rules")

        return dict(rule_to_products)

    def build_variable_to_products_map(
        self,
        products: List[str],
        verbose: bool = False
    ) -> Dict[str, Dict[str, Set[str]]]:
        """
        Build a mapping of variables to their values and which products have each value.

        Args:
            products: List of product names to scan
            verbose: Enable verbose output

        Returns:
            Dictionary mapping var_name -> {value -> set of products}
        """
        from collections import defaultdict

        print("Scanning variables across products...")

        # var_name -> {value -> set of products}
        var_to_value_products = defaultdict(lambda: defaultdict(set))

        for product in products:
            if verbose:
                print(f"  Scanning {product}...")

            variables = self.scan_product_variables(product)

            if verbose and variables:
                print(f"    Found {len(variables)} variables")

            for var_name, var_value in variables.items():
                var_to_value_products[var_name][var_value].add(product)

        # Convert to regular dict
        result = {}
        for var_name, value_products in var_to_value_products.items():
            result[var_name] = dict(value_products)

        if result:
            print(f"  ✓ Found {len(result)} unique variables")

        return result

    def generate_jinja_guard(self, products: Set[str], all_products: Set[str]) -> str:
        """
        Generate a Jinja2 conditional guard for a rule.

        Args:
            products: Set of products where this rule exists
            all_products: Set of all known products

        Returns:
            Jinja2 conditional string or empty string if applies to all
        """
        # If rule applies to all products, no guard needed
        if products == all_products:
            return ""

        # If rule applies to no products, exclude it entirely
        if not products:
            return "EXCLUDE"

        # Generate Jinja2 conditional with whitespace control
        products_list = sorted(products)

        if len(products_list) == 1:
            return '{{%- if product == "' + products_list[0] + '" %}}'
        else:
            products_str = '", "'.join(products_list)
            return '{{%- if product in ["' + products_str + '"] %}}'

    def apply_guards_to_control_file(
        self,
        control_file: Path,
        rule_to_products: Dict[str, Set[str]],
        var_to_value_products: Dict[str, Dict[str, Set[str]]],
        output_file: Optional[Path] = None,
        verbose: bool = False
    ):
        """
        Apply product guards to a control file.

        Args:
            control_file: Path to control file to process
            rule_to_products: Mapping of rules to products
            var_to_value_products: Mapping of variables to {value -> products}
            output_file: Output path (default: same as input with .jinja extension)
            verbose: Enable verbose output
        """
        if not control_file.exists():
            print(f"Error: Control file not found: {control_file}", file=sys.stderr)
            sys.exit(1)

        print(f"Loading control file: {control_file}")

        with open(control_file, 'r', encoding='utf-8') as f:
            control_data = self.yaml.load(f)

        if not control_data or 'controls' not in control_data:
            print("Error: Invalid control file format", file=sys.stderr)
            sys.exit(1)

        all_products = set()
        for products in rule_to_products.values():
            all_products.update(products)

        print(f"Applying product guards (known products: {', '.join(sorted(all_products))})")

        total_rules = 0
        guarded_rules = 0
        excluded_rules = 0

        for control in control_data['controls']:
            if 'rules' not in control or not control['rules']:
                continue

            # Check if this is the VARIABLES control
            is_variables_control = control['id'] == 'VARIABLES'

            # Process each rule in the control
            new_rules = []

            for item in control['rules']:
                # Check if this is a variable assignment
                if '=' in item:
                    # It's a variable assignment: var_name=value
                    var_name, var_value = item.split('=', 1)

                    # Find which products have this variable=value combination
                    if var_name in var_to_value_products:
                        value_products = var_to_value_products[var_name]
                        products_with_value = value_products.get(var_value, set())
                    else:
                        # Variable not found in scanned products - keep unguarded
                        products_with_value = all_products

                    guard = self.generate_jinja_guard(products_with_value, all_products)

                    if guard == "EXCLUDE":
                        if verbose:
                            print(f"  {control['id']}: Excluding {item} (not in any product)")
                        excluded_rules += 1
                        continue

                    elif guard:
                        if verbose:
                            prods = ', '.join(sorted(products_with_value))
                            print(f"  {control['id']}: Guarding {item} → {prods}")
                        guarded_rules += 1
                        new_rules.append(f"GUARD:{guard}:{item}")

                    else:
                        # Variable applies to all products
                        new_rules.append(item)

                    total_rules += 1

                else:
                    # It's a regular rule
                    total_rules += 1

                    # Get products for this rule
                    products = rule_to_products.get(item, set())

                    # Generate guard
                    guard = self.generate_jinja_guard(products, all_products)

                    if guard == "EXCLUDE":
                        # Rule doesn't exist in any product
                        if verbose:
                            print(f"  {control['id']}: Excluding {item} (not in any product)")
                        excluded_rules += 1
                        continue

                    elif guard:
                        # Rule needs guard
                        if verbose:
                            print(f"  {control['id']}: Guarding {item} → {', '.join(sorted(products))}")
                        guarded_rules += 1
                        # Store as a comment marker that we'll convert during output
                        new_rules.append(f"GUARD:{guard}:{item}")

                    else:
                        # Rule applies to all products
                        new_rules.append(item)

            control['rules'] = new_rules

        print(f"  ✓ Processed {total_rules} rules and variables")
        print(f"  ✓ Added guards to {guarded_rules} items")
        print(f"  ✓ Excluded {excluded_rules} items (not in any product)")

        # Ensure VARIABLES control includes all variable values found in scanned products
        # Find the VARIABLES control
        variables_control = None
        for control in control_data['controls']:
            if control['id'] == 'VARIABLES':
                variables_control = control
                break

        if variables_control and var_to_value_products:
            # Get existing variable assignments
            existing_vars = set(variables_control['rules'])

            # Add any missing variable values from scanned products
            added_vars = 0
            for var_name, value_products in var_to_value_products.items():
                for var_value, products_with_value in value_products.items():
                    var_assignment = f"{var_name}={var_value}"

                    # Check if this variable=value already exists (plain or guarded)
                    already_exists = False
                    for existing in existing_vars:
                        if existing == var_assignment or existing.endswith(f":{var_assignment}"):
                            already_exists = True
                            break

                    if not already_exists:
                        # Generate guard for this new variable
                        guard = self.generate_jinja_guard(products_with_value, all_products)

                        if guard == "EXCLUDE":
                            continue

                        elif guard:
                            variables_control['rules'].append(f"GUARD:{guard}:{var_assignment}")
                            added_vars += 1

                        else:
                            variables_control['rules'].append(var_assignment)
                            added_vars += 1

            if added_vars > 0:
                print(f"  ✓ Added {added_vars} missing variable assignments from scanned products")

        # Determine output path
        if output_file is None:
            output_file = control_file.with_suffix('.profile')

        print(f"Writing guarded control file: {output_file}")

        # Write to file with custom formatting for guards
        self._write_guarded_yaml(control_data, output_file)

        print(f"  ✓ Saved to {output_file}")

    def _write_guarded_yaml(self, data: Dict, output_path: Path):
        """
        Write YAML with Jinja2 guards expanded.

        This is a custom writer that converts our GUARD markers into
        proper Jinja2 conditionals in the YAML output.
        """
        import io

        # First, dump to string
        stream = io.StringIO()
        self.yaml.dump(data, stream)
        yaml_content = stream.getvalue()

        # Now process to convert GUARD markers to Jinja2
        lines = yaml_content.split('\n')
        output_lines = []
        current_guard = None
        indent_level = 0

        for line in lines:
            # Check if line contains a GUARD marker
            if 'GUARD:' in line:
                # Extract guard and the guarded item
                parts = line.split('GUARD:', 1)[1]
                guard_end = parts.index(':', 0)
                guard = parts[:guard_end]
                item_part = parts[guard_end + 1:].strip()

                # Get indentation
                indent = len(line) - len(line.lstrip())

                # Close previous guard if needed
                if current_guard:
                    output_lines.append(' ' * indent_level + '{{%- endif %}}')

                # Open new guard
                output_lines.append(' ' * indent + guard)
                indent_level = indent

                # Determine if this is a rule (list item) or variable (dict entry)
                # Rules appear as "- GUARD:...:{rule_id}"
                # Variables appear as "GUARD:...:{var_name}: value"
                if line.lstrip().startswith('- '):
                    # It's a list item (rule)
                    item_id = item_part.strip("'\"")
                    output_lines.append(' ' * indent + f'- {item_id}')
                else:
                    # It's a dict entry (variable)
                    # The line format is: "  GUARD:{guard}:{var_name}: value"
                    # Extract var_name and find the value part
                    if ': ' in item_part:
                        var_name_with_value = item_part
                        var_name = var_name_with_value.split(': ', 1)[0].strip("'\"")
                        # Need to get the value from the original line
                        value_match = line.split(': ', 1)
                        if len(value_match) > 1:
                            value = value_match[1]
                            output_lines.append(' ' * indent + f'{var_name}: {value}')
                    else:
                        # Fallback: just use the item as-is
                        output_lines.append(' ' * indent + item_part)

                current_guard = guard

            else:
                # Regular line
                stripped = line.lstrip()

                # Check if this is a plain rule (starts with '- ' but no GUARD marker)
                is_plain_rule = stripped.startswith('- ') and 'GUARD:' not in line

                # Close guard if:
                # 1. We're moving to a different section (not a list item), OR
                # 2. We encounter a plain rule (should not be inside a guard)
                if current_guard and line:
                    if not line.startswith(' ' * indent_level + '- ') or is_plain_rule:
                        output_lines.append(' ' * indent_level + '{{%- endif %}}')
                        current_guard = None

                output_lines.append(line)

        # Close final guard if needed
        if current_guard:
            output_lines.append(' ' * indent_level + '{{%- endif %}}')

        # Write output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(output_lines))


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Generate product-aware Jinja2 guards for control files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Scan all built products and add guards to control file
  %(prog)s --control-file controls/nist_800_53.yml

  # Specify output location
  %(prog)s --control-file controls/nist_800_53.yml \\
           --output controls/nist_800_53.profile

  # Verbose mode
  %(prog)s --control-file controls/nist_800_53.yml --verbose

  # Scan specific products only
  %(prog)s --control-file controls/nist_800_53.yml \\
           --products rhel8 rhel9 ocp4
        '''
    )
    parser.add_argument(
        '--control-file',
        type=Path,
        required=True,
        help='Path to control file to process (e.g., controls/nist_800_53.yml)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output file path (default: input with .profile extension)'
    )
    parser.add_argument(
        '--repo-root',
        type=Path,
        default=Path(__file__).parent.parent.parent,
        help='Path to repository root (default: auto-detect)'
    )
    parser.add_argument(
        '--products',
        nargs='+',
        help='Specific products to scan (default: all built products)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    generator = ProductGuardGenerator(args.repo_root)

    try:
        # Find products to scan
        if args.products:
            products = args.products
        else:
            products = generator.find_built_products()

        if not products:
            print("No built products found. Run ./build_product first.", file=sys.stderr)
            return 1

        print(f"Products to scan: {', '.join(products)}")
        print()

        # Build rule→products mapping
        rule_to_products = generator.build_rule_to_products_map(
            products,
            verbose=args.verbose
        )

        print()

        # Build variable→{value→products} mapping
        var_to_value_products = generator.build_variable_to_products_map(
            products,
            verbose=args.verbose
        )

        print()

        # Apply guards to control file
        generator.apply_guards_to_control_file(
            args.control_file,
            rule_to_products,
            var_to_value_products,
            output_file=args.output,
            verbose=args.verbose
        )

        print()
        print("✓ Product guards generated successfully!")
        print()
        print("The guarded control file uses Jinja2 conditionals to ensure")
        print("rules and variables are only selected when they exist for the product.")

        return 0

    except Exception as e:
        print(f"\n✗ Failed to generate guards: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
