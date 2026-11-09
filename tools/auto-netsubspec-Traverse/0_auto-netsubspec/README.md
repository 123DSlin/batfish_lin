# Auto-NetSubspec

Automatic network verification subspec generation toolkit.

## Usage

Execute the following scripts in order, using example directory: `smt_outputs/smt_output_0001`

### 1. SMT Slicing

```bash
python3 1_smt_slicer.py smt_outputs/smt_output_0001
```

**Output:**
- `1_sliced_device_smt_encoding/` - Device-level sliced files
  - `sliced_smt_encoding.smt2` - Global sliced file
  - `sliced_{device}_smt_encoding.smt2` - Per-device sliced files

### 2. Route Analysis

```bash
python3 2_route_analyzer.py smt_outputs/smt_output_0001
```

**Output:**
- `2_dataplane_original/` - Device constraint files
  - `{device}_overall_best_routes.txt` - Best route constraints
  - `{device}_stable_states.txt` - Stable state constraints
  - `{device}_stable_states_negated.txt` - Negated stable state constraints
  - `{device}_route_attributes_negated.txt` - Negated route attribute constraints

### 3. Assume-Guarantee Testing

```bash
python3 3_assume_guarantee_tester.py smt_outputs/smt_output_0001
```

**Important: All tests must pass before proceeding to step 4!**

**Output:**
- `3_assume_guarantee_test/` - Test results
  - `complete_forward_{device}.smt2` - Forward verification files
  - `complete_reverse_{device}.smt2` - Reverse verification files
  - `test_summary.txt` - Test summary

### 4. Subspec Simplification

```bash
python3 4_subspec_simplifier.py smt_outputs/smt_output_0001
```

**Output:**
- `4_baseline_files/` - Baseline files
  - `verification_{device}.smt2` - Verification files
  - `route_attributes_verification_{device}.smt2` - Route attributes verification files
  - `synthesis_{device}.smt2` - Synthesis files
- `4_field_level_intermediate_files/` - Field-level intermediate files
- `4_line_level_intermediate_files/` - Line-level intermediate files
- `field_level_subspecs.txt` - Field-level subspecs
- `line_level_subspecs.txt` - Line-level subspecs
- `field_level_pair_subspecs.txt` - Field-level pair subspecs

## Delete Intermediate Files

Use the `-d` option to delete intermediate output files (without executing subsequent operations):

```bash
python3 1_smt_slicer.py -d smt_outputs/smt_output_0001
python3 2_route_analyzer.py -d smt_outputs/smt_output_0001
python3 3_assume_guarantee_tester.py -d smt_outputs/smt_output_0001
python3 4_subspec_simplifier.py -d smt_outputs/smt_output_0001
```
