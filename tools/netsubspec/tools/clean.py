#!/usr/bin/env python3
"""
Clean script to clean up intermediate files (same scope as tools/run.py).

Usage: python tools/clean.py [-a] <work_dir>

- If work_dir contains subdirectories named smt_output_*, runs cleanup (-d) for each
  such subdirectory (same as run.py).
- If work_dir has no smt_output_* subdirectories, runs cleanup on work_dir itself.

  -a             Run cleanup for scripts 1_ through 6_. Default: run only 4_, 5_, 6_.
"""

import sys
import os
import subprocess
from pathlib import Path

def run_command(cmd):
    """Run a command and print its output"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def main():
    args = [a for a in sys.argv[1:] if a != '-a']
    run_all = '-a' in sys.argv[1:]

    if len(args) != 1:
        print("Usage: python tools/clean.py [-a] <work_dir>")
        print("  -a    Clean using scripts 1_..6_; default: scripts 4_..6_ only")
        print("Example: python tools/clean.py smt_outputs_fattrees")
        print("Example: python tools/clean.py -a smt_outputs_fattrees")
        sys.exit(1)

    work_dir = Path(args[0])
    if not work_dir.exists():
        print(f"Error: Directory {work_dir} does not exist")
        sys.exit(1)

    # Project root (parent of tools/)
    project_root = Path(__file__).resolve().parent.parent

    if run_all:
        scripts_to_clean = [
            "1_route_analyzer.py",
            "2_smt_slicer.py",
            "3_assume_guarantee_tester.py",
            "4_subspec_simplifier.py",
            "5_subspec_simplifier_original.py",
            "6_subspec_simplifier_fullsym.py",
        ]
    else:
        scripts_to_clean = [
            "4_subspec_simplifier.py",
            "5_subspec_simplifier_original.py",
            "6_subspec_simplifier_fullsym.py",
        ]
    
    # Verify all scripts exist
    missing_scripts = []
    for script in scripts_to_clean:
        if not (project_root / script).exists():
            missing_scripts.append(script)
    
    if missing_scripts:
        print(f"Error: The following scripts were not found in {project_root}:")
        for s in missing_scripts:
            print(f"  - {s}")
        sys.exit(1)
        
    # Get subdirectories
    excluded_dirs = {'__pycache__', '.git', '.svn', '.hg'}
    subdirs = sorted([d for d in work_dir.iterdir() 
                     if d.is_dir() and d.name not in excluded_dirs and not d.name.startswith('.')])
    
    if not subdirs:
        print(f"No subdirectories found in {work_dir}")
        sys.exit(0)
        
    print(f"Found {len(subdirs)} subdirectories in {work_dir}")
    print(f"Cleaning scripts: {', '.join(scripts_to_clean)}")
    print("=" * 80)
    
    for idx, subdir in enumerate(subdirs, 1):
        print(f"[{idx}/{len(subdirs)}] Cleaning {subdir.name}...")
        
        for script in scripts_to_clean:
            script_path = project_root / script
            # Construct command: python3 script.py -d absolute_subdir_path
            cmd = f"{sys.executable} {script_path} -d {subdir.absolute()}"
            
            # Print a compact status line
            # print(f"  Running: {script} -d ... ", end="", flush=True)
            
            success, output = run_command(cmd)
            
            if success:
                # print("OK")
                pass
            else:
                print(f"  Failed: {script} -d")
                print(f"  Error: {output.strip()}")
        
        print("  Done.")

    print("=" * 80)
    print("Cleanup complete.")

if __name__ == "__main__":
    main()

