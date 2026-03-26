# NIST 800-53 Control Files

This directory contains the NIST 800-53 control file and its CIS mapping reference.

## File Structure

### `nist_800_53.yml` (Real Control File - Source of Truth)
- **Purpose**: Production control file used for building profiles
- **Maintained By**: 👤 **Humans (YOU)**
- **Format**: YAML with Jinja2 guards
- **Edits**: Make all edits directly to this file
- **Automation**: **NEVER** touched by automation
- **Contains**:
  - Human-curated rule mappings
  - Custom Jinja2 guards
  - Manual notes and metadata
  - Rules not from CIS (human additions)

### `shared/references/controls/nist_800_53_cis_reference.yml` (CIS Reference - With Guards)
- **Purpose**: Shows what CIS benchmark mappings say NIST controls should have
- **Maintained By**: 🤖 **Automation**
- **Format**: YAML with Jinja2 guards (auto-generated)
- **Edits**: **DO NOT** edit this file manually
- **Automation**: Regenerated weekly from CIS→NIST mappings + guards
- **Used For**: Building CIS-NIST profiles (profiles inherit from this)
- **Contains**:
  - Auto-generated CIS→NIST rule mappings
  - OSCAL catalog metadata
  - Baseline level assignments
  - Product-specific Jinja2 guards

## Workflow

### Weekly Automation

Every Sunday afternoon, automation:

1. ✅ Downloads latest NIST OSCAL catalog
2. ✅ Regenerates `nist_800_53_cis_reference.yml` from CIS mappings
3. ✅ Creates PR if reference file changed
4. ⚠️  **PR requires manual action** - see below

### Manual Review Process

When you receive an automated PR:

1. **Review the diff** in `shared/references/controls/nist_800_53_cis_reference.yml`
   - What rules were added?
   - What rules were removed?
   - What controls changed?
   - Note: This file has Jinja2 guards for product-specific rules

2. **Manually update** `nist_800_53.yml` based on the diff
   - Add new rules that make sense
   - Remove obsolete rules (check if they're used elsewhere first!)
   - Update metadata if needed
   - **Preserve your human edits and guards**

3. **Commit your changes** to the PR
   ```bash
   gh pr checkout <PR-NUMBER>
   vim controls/nist_800_53.yml
   git add controls/nist_800_53.yml
   git commit -m "Apply CIS mapping updates to nist_800_53.yml"
   git push
   ```

4. **Merge the PR** once both files are updated

### Making Manual Edits

To add rules, notes, or guards to the real control file:

```bash
# Edit the real file directly
vim controls/nist_800_53.yml

# Example: Add a rule to a control
  - id: ac-2
    title: Account Management
    rules:
      - existing_rule_1
      - my_new_human_added_rule  # Your addition
    notes: "Added custom rule for XYZ requirement"

# Commit your changes
git add controls/nist_800_53.yml
git commit -m "Add custom rule to AC-2"
```

## Why Two Files?

### The Problem
- CIS benchmarks change over time (new rules added/removed)
- We need to track what CIS *thinks* NIST controls should have
- But we also have human-curated content that shouldn't be overwritten
- Automation can't distinguish "human addition" from "old CIS mapping"

### The Solution
- **Reference file** = What CIS currently says
- **Real file** = What we actually use (CIS + human edits)
- **Diff** = What changed in CIS that we might want to apply

### Benefits
- ✅ Human edits are never overwritten by automation
- ✅ CIS changes are tracked and reviewable
- ✅ Clear separation between automated and manual content
- ✅ Both files committed for full transparency

## Example Scenario

### Initial State
`controls/nist_800_53.yml` (real file):
```yaml
  - id: ac-2
    title: Account Management
    rules:
      - rule_from_cis_v1
      - my_custom_rule  # Human added
    notes: "Custom note about this control"
```

`shared/references/controls/nist_800_53_cis_reference.yml`:
```yaml
  - id: ac-2
    title: Account Management
    rules:
      - rule_from_cis_v1
```

### CIS Benchmark Updates

New CIS version adds `rule_from_cis_v2`, removes `rule_from_cis_v1`.

Automation regenerates reference:
```yaml
  - id: ac-2
    title: Account Management
    rules:
      - rule_from_cis_v2  # NEW
```

### You Review the PR

You see:
- ❌ `rule_from_cis_v1` removed (was in old reference)
- ✅ `rule_from_cis_v2` added (new in reference)

### You Manually Update Real File

```yaml
  - id: ac-2
    title: Account Management
    rules:
      - rule_from_cis_v2      # Added based on CIS update
      - my_custom_rule        # PRESERVED (your addition)
    notes: "Custom note about this control"  # PRESERVED
```

### Result
- ✅ CIS updates applied
- ✅ Human edits preserved
- ✅ Full control over what goes in the real file

## File Locations

```
controls/
├── nist_800_53.yml                # 👤 REAL FILE (edit this)
└── README_nist_800_53.md          # This file

shared/references/controls/
└── nist_800_53_cis_reference.yml  # 🤖 REFERENCE (auto-generated with guards)

utils/nist_sync/
├── sync_nist.py                   # Generates CIS reference (clean YAML)
├── generate_product_family_guards.py  # Adds Jinja2 guards
└── generate_cis_nist_workflow.sh  # Complete workflow
```

## Integration with CI/CD

See `.github/workflows/cis-nist-sync.yml`

The workflow:
- Runs weekly (Sundays at 2 PM UTC)
- Can be triggered manually
- Creates PRs labeled `manual-review-required`
- PR description explains exactly what to do

## Troubleshooting

**Q: I edited `shared/references/controls/nist_800_53_cis_reference.yml` directly, what do I do?**

A: Don't do that! The reference file is auto-generated. Instead:
1. Revert your changes to the reference file
2. Make the same changes in `controls/nist_800_53.yml` (the real file)

**Q: The automation PR removes rules I added manually, what happened?**

A: The automation only updates the *reference* file. Your manually-added rules in `nist_800_53.yml` are safe! The PR is showing you what CIS currently says, but you decide what to keep.

**Q: Should I keep rules that CIS removed?**

A: Maybe! Consider:
- Is the rule still security-relevant?
- Is it used in other profiles?
- Do you have a reason to keep it?

You decide what goes in the real file.

**Q: Can I add Jinja2 guards to the real file?**

A: Yes! The real file (`nist_800_53.yml`) can have any guards you want. The automation never touches it.

**Q: How do I regenerate the CIS reference manually?**

A:
```bash
cd utils/nist_sync
./generate_cis_nist_workflow.sh --products "rhel8 rhel9 rhel10"
```

This regenerates the reference file. Then review the diff and manually update the real file.
