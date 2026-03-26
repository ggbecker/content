#!/usr/bin/env python3
"""
Migrate nist_800_53.yml to source file format.

This script creates nist_800_53.yml.source from nist_800_53.yml by:
1. Using Jinja2 to expand the template with a "union" context
2. Saving the expanded version as .source
3. Backing up the original guarded version

Usage:
    python3 migrate_to_source_format.py
"""

import sys
from pathlib import Path
from jinja2 import Template, Environment, StrictUndefined
import re

def create_union_context():
    """Create a context where all products are enabled."""
    # List all products we care about
    products = [
        'rhel7', 'rhel8', 'rhel9', 'rhel10',
        'ol7', 'ol8', 'ol9',
        'almalinux8', 'almalinux9', 'almalinux10',
        'ubuntu2004', 'ubuntu2204', 'ubuntu2404',
        'fedora', 'debian10', 'debian11', 'debian12',
        'ocp4', 'eks', 'rhcos4', 'sle12', 'sle15'
    ]

    # Context that makes all product checks pass
    context = {
        'product': 'rhel9',  # Default product for product == checks
    }

    return context, products

def expand_guards_to_union(content: str) -> str:
    """
    Expand Jinja2 guards to include all conditional content.

    Strategy: For each if/else/endif block, keep all unique content
    from both branches.
    """
    # Parse the content line by line and handle guards manually
    lines = content.split('\n')
    result_lines = []
    in_if = False
    in_else = False
    if_content = []
    else_content = []
    indent_level = 0

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check for Jinja2 guards
        if_match = re.search(r'{%\s*if\s+', line)
        else_match = re.search(r'{%\s*else\s*%}', line)
        endif_match = re.search(r'{%\s*endif\s*%}', line)

        if if_match:
            # Start of conditional block
            in_if = True
            in_else = False
            if_content = []
            else_content = []
            indent_level = len(line) - len(line.lstrip())
            # Don't add the guard line
        elif else_match:
            # Switch to else branch
            in_if = False
            in_else = True
            # Don't add the guard line
        elif endif_match:
            # End of conditional block - merge content
            # For rules list, merge and deduplicate
            # For other content, prefer if branch
            merged = merge_conditional_content(if_content, else_content, indent_level)
            result_lines.extend(merged)

            in_if = False
            in_else = False
            if_content = []
            else_content = []
        elif in_if:
            if_content.append(line)
        elif in_else:
            else_content.append(line)
        else:
            # Regular line, not in conditional
            result_lines.append(line)

        i += 1

    return '\n'.join(result_lines)

def merge_conditional_content(if_lines, else_lines, indent):
    """Merge content from if and else branches."""
    # Check if this is a list item block
    if_has_rules = any('-' in line for line in if_lines)
    else_has_rules = any('-' in line for line in else_lines)

    if if_has_rules and else_has_rules:
        # Both branches have list items - merge and deduplicate
        all_items = []
        seen = set()

        for line in if_lines + else_lines:
            stripped = line.strip()
            if stripped and stripped not in seen:
                all_items.append(line)
                seen.add(stripped)

        return all_items
    elif if_has_rules:
        # Only if branch has content
        return if_lines
    elif else_has_rules:
        # Only else branch has content
        return else_lines
    elif '[]' in ''.join(else_lines):
        # Else branch is just empty list marker
        return if_lines
    else:
        # Prefer if branch for other content
        return if_lines

def main():
    repo_root = Path(__file__).parent.parent.parent
    control_file = repo_root / "controls" / "nist_800_53.yml"
    source_file = repo_root / "controls" / "nist_800_53.yml.source"
    backup_file = repo_root / "controls" / "nist_800_53.yml.guarded.backup"

    if not control_file.exists():
        print(f"Error: {control_file} does not exist")
        return 1

    if source_file.exists():
        print(f"Warning: {source_file} already exists")
        response = input("Overwrite? [y/N]: ")
        if response.lower() != 'y':
            print("Aborted")
            return 0

    print("=" * 70)
    print("Migrating to source file format")
    print("=" * 70)
    print()
    print(f"Input:  {control_file}")
    print(f"Output: {source_file}")
    print(f"Backup: {backup_file}")
    print()

    # Read original file
    print("Reading original file...")
    with open(control_file, 'r', encoding='utf-8') as f:
        original_content = f.read()

    # Check if it has guards
    if '{%' not in original_content:
        print("File does not contain Jinja2 guards - copying as-is")
        with open(source_file, 'w', encoding='utf-8') as f:
            f.write(original_content)
        print(f"✓ Created {source_file}")
        return 0

    # Expand guards to union of all branches
    print("Expanding Jinja2 guards to create source file...")
    expanded_content = expand_guards_to_union(original_content)

    # Save source file
    print(f"Writing source file: {source_file}")
    with open(source_file, 'w', encoding='utf-8') as f:
        f.write(expanded_content)

    # Backup original
    print(f"Backing up original guarded file: {backup_file}")
    with open(backup_file, 'w', encoding='utf-8') as f:
        f.write(original_content)

    print()
    print("=" * 70)
    print("✓ Migration complete!")
    print("=" * 70)
    print()
    print("Next steps:")
    print("1. Review the source file to ensure it looks correct")
    print("2. Run sync_nist.py to synchronize with OSCAL")
    print("3. Run generate_product_family_guards.py to regenerate guards")
    print()
    print("Commands:")
    print("  cd utils/nist_sync")
    print("  python3 sync_nist.py --verbose")
    print("  python3 generate_product_family_guards.py --target rhel")
    print()

    return 0

if __name__ == '__main__':
    sys.exit(main())
