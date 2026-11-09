#!/usr/bin/env python3
"""
Parallel execution script for subspec computation

This script runs the pipeline for each subdirectory in work_dir:

1.1. python3 1_route_analyzer.py <sub_work_dir> (serial)
1.2. python3 2_smt_slicer.py <sub_work_dir> (serial)
1.3. python3 3_assume_guarantee_tester.py --device xxx <sub_work_dir> (parallel per device)
1.4. python3 3_internet2_refiner.py --device xxx <sub_work_dir> (parallel per device; only with --internet2)

--------------------------------------------------------------------------------

2.1. python3 4_subspec_simplifier.py -o -l --device xxx <sub_work_dir> (parallel per device)
2.2. python3 4_subspec_simplifier.py -o -f --device xxx <sub_work_dir> (parallel per device)

--------------------------------------------------------------------------------

3.1. python3 5_subspec_simplifier_original.py -l --device xxx <sub_work_dir> (parallel per device)
3.2. python3 5_subspec_simplifier_original.py -f --device xxx <sub_work_dir> (parallel per device)

--------------------------------------------------------------------------------

4.1. python3 6_subspec_simplifier_fullsym.py -l --device xxx <sub_work_dir> (parallel per device)
4.2. python3 6_subspec_simplifier_fullsym.py -f --device xxx <sub_work_dir> (parallel per device)

Flags: -i step 1 | -s step 2 | -sn step 3 | -sf step 4 (combinable; default: all steps)
       --internet2  After step 1.3, also run 3_internet2_refiner.py as step 1.4

Records timing for each step (start to end time difference) and writes results to times_NNNN.txt (e.g. times_0001.txt; if that exists, writes to times_0002.txt, etc.)
"""

import os
import sys
import subprocess
import time
import multiprocessing
from pathlib import Path
from queue import Empty as QueueEmpty
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Tuple, Dict

# Timeout for steps 2.1 / 2.2 / 3.1 / 3.2 / 4.1 / 4.2: 4 hours per step
# No timeout for steps 1.1 / 1.2 / 1.3
STEP_GROUP_TIMEOUT = 4 * 3600  # 14400 seconds

# Sleep (seconds) before each of steps 2.1 / 2.2 / 3.1 / 3.2 / 4.1 / 4.2
STEP_SLEEP_BEFORE_SECONDS = 100

def run_command(cmd, work_dir=None, timeout=None):
    """Run a command and return (success, elapsed_time, output, timed_out)"""
    start_time = time.time()
    timed_out = False
    try:
        if work_dir:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=timeout
            )
        else:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
        elapsed_time = time.time() - start_time
        success = result.returncode == 0
        return success, elapsed_time, result.stdout + result.stderr, timed_out
    except subprocess.TimeoutExpired:
        elapsed_time = time.time() - start_time
        timed_out = True
        return False, elapsed_time, "Timeout expired", timed_out
    except Exception as e:
        elapsed_time = time.time() - start_time
        return False, elapsed_time, f"Error: {str(e)}", timed_out

def format_time(seconds):
    """Format time in seconds to human-readable format"""
    if seconds < 60:
        return f"{seconds:.2f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.2f}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}h {minutes}m {secs:.2f}s"

def load_devices(hostnames_file: Path) -> List[str]:
    """Load device names from 0_hostnames.txt"""
    devices = []
    if hostnames_file.exists():
        with open(hostnames_file, 'r') as f:
            devices = [line.strip() for line in f if line.strip()]
    return devices


def get_next_times_file(base_dir: Path) -> Path:
    """Find next times file: scan times_0001.txt .. times_9999.txt; if e.g. times_0001.txt exists, return times_0002.txt. If none exist, return times_0001.txt."""
    max_found = 0
    for n in range(1, 10000):
        path = base_dir / f"times_{n:04d}.txt"
        if path.exists():
            max_found = n
    return base_dir / f"times_{max_found + 1:04d}.txt"


def init_subdir(subdir: Path, times_file: Path) -> Tuple[List[str], float]:
    """Per-subdir init: write directory to times file, load devices. Returns (devices, dir_start_time)."""
    with open(times_file, 'a') as f:
        f.write(f"\n[DIRECTORY]\n")
        f.write(f"name={subdir.name}\n")
    dir_start_time = time.time()
    devices = load_devices(subdir / "0_hostnames.txt")
    return devices, dir_start_time


def run_device_task(args: Tuple) -> Tuple[str, str, bool, float, str]:
    """Run a task for a specific device. Returns (device, step_name, success, elapsed, output)"""
    device, step_name, cmd, work_dir, timeout = args
    success, elapsed, output, timed_out = run_command(cmd, work_dir=work_dir, timeout=timeout)
    return (device, step_name, success, elapsed, output)

def run_parallel_steps(devices: List[str], step_name: str, cmd_template: str, 
                       work_dir: Path, script_dir: Path, max_parallel: int = None, 
                       timeout: float = None) -> Dict[str, float]:
    """Run a step in parallel for all network devices
    
    Args:
        devices: List of network device names (from 0_hostnames.txt, e.g., r1, r2, r3)
        step_name: Name of the step (for logging)
        cmd_template: Command template with {device}, {script_dir}, {work_dir} placeholders
        work_dir: Working directory
        script_dir: Directory containing scripts
        max_parallel: Maximum number of network devices to process simultaneously
                      (e.g., --core 4 means process 4 devices at the same time)
        timeout: Optional timeout in seconds
    
    Returns:
        Dictionary mapping device name to elapsed time (or -1 for failures)
    """
    if not devices:
        return {}
    
    # Prepare tasks
    tasks = []
    for device in devices:
        # Convert Path objects to strings for command template
        cmd = cmd_template.format(
            device=device, 
            script_dir=str(script_dir.absolute()), 
            work_dir=str(work_dir.absolute())
        )
        tasks.append((device, step_name, cmd, str(work_dir.absolute()), timeout))
    
    results = {}
    
    # If max_parallel is None or 1, run serially (like run.py)
    # --core 1 is treated as serial execution to avoid ProcessPoolExecutor overhead
    if max_parallel is None or max_parallel == 1:
        print(f"  Running {step_name} serially for {len(devices)} network devices...")
        for idx, task in enumerate(tasks, 1):
            device, step_name, success, elapsed, output = run_device_task(task)
            if success:
                print(f"    [{idx}/{len(devices)}] Device {device}: ✓ Completed in {format_time(elapsed)}")
                results[device] = elapsed
            else:
                print(f"    [{idx}/{len(devices)}] Device {device}: ✗ Failed after {format_time(elapsed)}")
                # Print error details (last few lines of output)
                if output:
                    error_lines = output.strip().split('\n')
                    if error_lines:
                        # Print last 3 lines of error output
                        error_snippet = '\n'.join(error_lines[-3:])
                        print(f"      Error: {error_snippet}")
                results[device] = -1  # Use -1 to indicate failure
    else:
        # Parallel execution: run multiple network devices simultaneously
        # Note: max_parallel must be >= 2 at this point (1 is handled above as serial)
        print(f"  Running {step_name} in parallel for {len(devices)} network devices ({max_parallel} devices simultaneously)...")
        
        # max_workers directly equals max_parallel (number of network devices to process in parallel)
        # Example: --core 4 -> max_workers = 4 (process 4 network devices at the same time)
        #          --core 8 -> max_workers = 8 (process 8 network devices at the same time)
        max_workers = min(len(devices), max_parallel)
        print(f"    Processing {max_workers} network devices in parallel (out of {len(devices)} total devices)")
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(run_device_task, task): task[0] for task in tasks}
            
            completed = 0
            for future in as_completed(futures):
                device, step_name, success, elapsed, output = future.result()
                completed += 1
                if success:
                    print(f"    [{completed}/{len(devices)}] Device {device}: ✓ Completed in {format_time(elapsed)}")
                    results[device] = elapsed
                else:
                    print(f"    [{completed}/{len(devices)}] Device {device}: ✗ Failed after {format_time(elapsed)}")
                    # Print error details (last few lines of output)
                    if output:
                        error_lines = output.strip().split('\n')
                        if error_lines:
                            # Print last 3 lines of error output
                            error_snippet = '\n'.join(error_lines[-3:])
                            print(f"      Error: {error_snippet}")
                    results[device] = -1  # Use -1 to indicate failure
    
    return results


def _run_step_in_process(
    result_queue: multiprocessing.Queue,
    devices: List[str],
    step_name: str,
    cmd_template: str,
    work_dir: Path,
    script_dir: Path,
    max_parallel: int,
) -> None:
    """Run run_parallel_steps with no per-device timeout and put result dict into queue. Used for step-level 4h timeout."""
    results = run_parallel_steps(
        devices, step_name, cmd_template, work_dir, script_dir, max_parallel, timeout=None
    )
    result_queue.put(results)


def main():
    # Parse command line arguments
    max_parallel = 20  # Default: 20 devices in parallel
    work_dir = None
    run_step1 = False  # -i: step 1 (1.1–1.3)
    run_step2 = False  # -s: step 2 (2.1–2.2, 4_subspec_simplifier)
    run_step3 = False  # -sn: step 3 (3.1–3.2, 5_subspec_simplifier_original)
    run_step4 = False  # -sf: step 4 (4.1–4.2, 6_subspec_simplifier_fullsym)
    run_internet2 = False  # --internet2: step 1.4 (3_internet2_refiner.py after 1.3)
    
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--core':
            if i + 1 >= len(sys.argv):
                print("Error: --core requires a positive integer value")
                sys.exit(1)
            try:
                max_parallel = int(sys.argv[i + 1])
                if max_parallel <= 0:
                    print(f"Error: --core must be a positive integer, got {max_parallel}")
                    sys.exit(1)
            except ValueError:
                print(f"Error: Invalid parallel count '{sys.argv[i + 1]}'. Must be an integer")
                sys.exit(1)
            i += 1
        elif arg == '-i':
            run_step1 = True
        elif arg == '-sn':
            run_step3 = True
        elif arg == '-sf':
            run_step4 = True
        elif arg == '-s':
            run_step2 = True
        elif arg == '--internet2':
            run_internet2 = True
        elif arg in ['-h', '--help']:
            print("Usage: python tools/run.py [-i] [-s] [-sn] [-sf] [--internet2] [--core N] <work_dir>")
            print("Options:")
            print("  -i             Run step 1 only (1.1–1.3, plus 1.4 if --internet2)")
            print("  -s             Run step 2 only (2.1–2.2, 4_subspec_simplifier -l then -f)")
            print("  -sn            Run step 3 only (3.1–3.2, 5_subspec_simplifier_original -l then -f)")
            print("  -sf            Run step 4 only (4.1–4.2, 6_subspec_simplifier_fullsym -l then -f)")
            print("  --internet2    After step 1.3, run 3_internet2_refiner.py as step 1.4 (parallel per device)")
            print("  --core N       Number of network devices to process simultaneously (default: 20)")
            print("                 Applies to steps that run per device (1.3, 1.4, 2.1, 2.2, 3.1, 3.2, 4.1, 4.2)")
            print("  <work_dir>     Directory containing subdirectories (e.g. smt_output_0012) to process")
            print("")
            print("Flags are combinable (e.g. -s -sn -sf). If none of -i/-s/-sn/-sf is specified, all steps run.")
            sys.exit(0)
        elif arg.startswith('-'):
            print(f"Error: Unknown option: {arg}")
            print("Usage: python tools/run.py [-i] [-s] [-sn] [-sf] [--internet2] [--core N] <work_dir>")
            sys.exit(1)
        else:
            if work_dir is None:
                work_dir = arg
            else:
                print(f"Error: Multiple working directories specified: {work_dir} and {arg}")
                sys.exit(1)
        i += 1
    
    if work_dir is None:
        print("Error: Working directory not specified")
        print("Usage: python tools/run.py [-i] [-s] [-sn] [-sf] [--internet2] [--core N] <work_dir>")
        sys.exit(1)
    
    # If no step flag is specified, run all steps
    if not run_step1 and not run_step2 and not run_step3 and not run_step4:
        run_step1 = run_step2 = run_step3 = run_step4 = True
    
    # Base directory
    base_dir = Path(work_dir)
    if not base_dir.exists():
        print(f"Error: Directory {base_dir} does not exist")
        sys.exit(1)
    
    # Verify required scripts exist
    script_dir = Path(__file__).resolve().parent.parent
    required_scripts = [
        "1_route_analyzer.py",
        "2_smt_slicer.py",
        "3_assume_guarantee_tester.py",
        "4_subspec_simplifier.py",
        "5_subspec_simplifier_original.py",
        "6_subspec_simplifier_fullsym.py"
    ]
    
    missing_scripts = []
    for script in required_scripts:
        script_path = script_dir / script
        if not script_path.exists():
            missing_scripts.append(script)
    
    if run_internet2:
        refiner_path = script_dir / "3_internet2_refiner.py"
        if not refiner_path.exists():
            missing_scripts.append("3_internet2_refiner.py")

    if missing_scripts:
        print(f"Error: Required scripts not found:")
        for script in missing_scripts:
            print(f"  - {script}")
        print(f"\nPlease ensure all scripts are in: {script_dir}")
        sys.exit(1)
    
    # Get all subdirectories starting with smt_output_
    subdirs = sorted([d for d in base_dir.iterdir() 
                     if d.is_dir() and d.name.startswith('smt_output_')])
    
    if not subdirs:
        print(f"No subdirectories found in {base_dir}")
        sys.exit(1)
    
    print(f"Found {len(subdirs)} subdirectories to process")
    
    # Choose next times file: times_0001.txt .. times_9999.txt (if times_0001 exists, write to times_0002, etc.)
    times_file = get_next_times_file(base_dir)
    print(f"Results will be written to: {times_file}")
    
    # Display hardware information
    available_cores = os.cpu_count() or 1
    print(f"Detected CPU cores: {available_cores}")
    
    print(f"Parallel execution: {max_parallel} network devices simultaneously")
    
    # Display which steps will be run
    steps_to_run = []
    if run_step1:
        if run_internet2:
            steps_to_run.append("1.1–1.4 (1_, --internet2)")
        else:
            steps_to_run.append("1.1–1.3 (1_)")
    if run_step2:
        steps_to_run.append("2.1–2.2 (4_)")
    if run_step3:
        steps_to_run.append("3.1–3.2 (5_)")
    if run_step4:
        steps_to_run.append("4.1–4.2 (6_)")
    print(f"Steps to run: {', '.join(steps_to_run)}")
    print()
    
    # Open output file for writing
    with open(times_file, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write(f"Timing Benchmark Results\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
    
    total_start_time = time.time()
    
    for idx, subdir in enumerate(subdirs, 1):
        dir_name = subdir.name
        print(f"[{idx}/{len(subdirs)}] Processing: {dir_name}")
        
        # Per-subdir init: write directory to times file, load devices (used by steps 1.3, 2.x, 3.x, 4.x)
        devices, dir_start_time = init_subdir(subdir, times_file)
        if not devices:
            print(f"  ⚠ No devices found in {subdir / '0_hostnames.txt'}, skipping parallel steps")
        else:
            print(f"  Found {len(devices)} devices: {', '.join(devices)}")
        
        # Step 1: Base steps (1.1, 1.2, 1.3)
        if run_step1:
            # Step 1.1: 1_route_analyzer.py (serial)
            print(f"  Running step1.1: 1_route_analyzer.py...")
            cmd = f"python3 {script_dir / '1_route_analyzer.py'} {subdir.absolute()}"
            success, elapsed, output, timed_out = run_command(cmd)
            with open(times_file, 'a') as f:
                if success:
                    print(f"    ✓ Completed in {format_time(elapsed)}")
                    f.write(f"step1.1: {format_time(elapsed)}\n")
                else:
                    print(f"    ✗ Failed after {format_time(elapsed)}")
                    f.write(f"step1.1: ERROR\n")
            
            # Step 1.2: 2_smt_slicer.py (serial)
            print(f"  Running step1.2: 2_smt_slicer.py...")
            cmd = f"python3 {script_dir / '2_smt_slicer.py'} {subdir.absolute()}"
            success, elapsed, output, timed_out = run_command(cmd)
            with open(times_file, 'a') as f:
                if success:
                    print(f"    ✓ Completed in {format_time(elapsed)}")
                    f.write(f"step1.2: {format_time(elapsed)}\n")
                else:
                    print(f"    ✗ Failed after {format_time(elapsed)}")
                    f.write(f"step1.2: ERROR\n")
            
            # Step 1.3: 3_assume_guarantee_tester.py --device xxx (parallel)
            if devices:
                print(f"  Running step1.3: 3_assume_guarantee_tester.py (parallel for {len(devices)} devices)...")
                step_start = time.time()
                results = run_parallel_steps(
                    devices, "step1.3",
                    f"python3 {{script_dir}}/3_assume_guarantee_tester.py --device {{device}} {{work_dir}}",
                    subdir, script_dir, max_parallel
                )
                step_elapsed = time.time() - step_start
                with open(times_file, 'a') as f:
                    if all(elapsed >= 0 for elapsed in results.values()):
                        print(f"    ✓ Completed in {format_time(step_elapsed)}")
                        f.write(f"step1.3: {format_time(step_elapsed)}\n")
                    else:
                        print(f"    ✗ Some devices failed after {format_time(step_elapsed)}")
                        f.write(f"step1.3: ERROR\n")

            # Step 1.4: 3_internet2_refiner.py --device xxx (parallel; only with --internet2)
            if run_internet2 and devices:
                print(f"  Running step1.4: 3_internet2_refiner.py (parallel for {len(devices)} devices)...")
                step_start = time.time()
                results = run_parallel_steps(
                    devices, "step1.4",
                    f"python3 {{script_dir}}/3_internet2_refiner.py --device {{device}} {{work_dir}}",
                    subdir, script_dir, max_parallel
                )
                step_elapsed = time.time() - step_start
                with open(times_file, 'a') as f:
                    if all(elapsed >= 0 for elapsed in results.values()):
                        print(f"    ✓ Completed in {format_time(step_elapsed)}")
                        f.write(f"step1.4: {format_time(step_elapsed)}\n")
                    else:
                        print(f"    ✗ Some devices failed after {format_time(step_elapsed)}")
                        f.write(f"step1.4: ERROR\n")

        # Step 2: 4_subspec_simplifier.py — 4h timeout per step
        if run_step2:
            if devices:
                time.sleep(STEP_SLEEP_BEFORE_SECONDS)
                print(f"  Running step2.1: 4_subspec_simplifier.py -o -l (parallel for {len(devices)} devices, timeout 4h per step)...")
                step_start = time.time()
                result_queue = multiprocessing.Queue()
                step_proc = multiprocessing.Process(
                    target=_run_step_in_process,
                    args=(
                        result_queue, devices, "step2.1",
                        f"python3 {{script_dir}}/4_subspec_simplifier.py -o -l --device {{device}} {{work_dir}}",
                        subdir, script_dir, max_parallel,
                    ),
                )
                step_proc.start()
                step_timed_out = False
                try:
                    results = result_queue.get(timeout=STEP_GROUP_TIMEOUT)
                except QueueEmpty:
                    step_timed_out = True
                    print(f"    Step 2.1 timed out (4h), stopping all and proceeding to next step")
                    step_proc.terminate()
                    step_proc.join(timeout=10)
                    if step_proc.is_alive():
                        step_proc.kill()
                        step_proc.join()
                    results = {d: -1 for d in devices}
                step_elapsed = time.time() - step_start
                with open(times_file, 'a') as f:
                    if step_timed_out:
                        f.write(f"step2.1: 4h +\n")
                    elif all(elapsed >= 0 for elapsed in results.values()):
                        print(f"    ✓ Completed in {format_time(step_elapsed)}")
                        f.write(f"step2.1: {format_time(step_elapsed)}\n")
                    else:
                        print(f"    ✗ Some devices failed after {format_time(step_elapsed)}")
                        f.write(f"step2.1: ERROR\n")

            if devices:
                time.sleep(STEP_SLEEP_BEFORE_SECONDS)
                print(f"  Running step2.2: 4_subspec_simplifier.py -o -f (parallel for {len(devices)} devices, timeout 4h per step)...")
                step_start = time.time()
                result_queue = multiprocessing.Queue()
                step_proc = multiprocessing.Process(
                    target=_run_step_in_process,
                    args=(
                        result_queue, devices, "step2.2",
                        f"python3 {{script_dir}}/4_subspec_simplifier.py -o -f --device {{device}} {{work_dir}}",
                        subdir, script_dir, max_parallel,
                    ),
                )
                step_proc.start()
                step_timed_out = False
                try:
                    results = result_queue.get(timeout=STEP_GROUP_TIMEOUT)
                except QueueEmpty:
                    step_timed_out = True
                    print(f"    Step 2.2 timed out (4h), stopping all and proceeding to next step")
                    step_proc.terminate()
                    step_proc.join(timeout=10)
                    if step_proc.is_alive():
                        step_proc.kill()
                        step_proc.join()
                    results = {d: -1 for d in devices}
                step_elapsed = time.time() - step_start
                with open(times_file, 'a') as f:
                    if step_timed_out:
                        f.write(f"step2.2: 4h +\n")
                    elif all(elapsed >= 0 for elapsed in results.values()):
                        print(f"    ✓ Completed in {format_time(step_elapsed)}")
                        f.write(f"step2.2: {format_time(step_elapsed)}\n")
                    else:
                        print(f"    ✗ Some devices failed after {format_time(step_elapsed)}")
                        f.write(f"step2.2: ERROR\n")

        # Step 3: 5_subspec_simplifier_original.py — 4h timeout per step
        if run_step3:
            if devices:
                time.sleep(STEP_SLEEP_BEFORE_SECONDS)
                print(f"  Running step3.1: 5_subspec_simplifier_original.py -l (parallel for {len(devices)} devices, timeout 4h per step)...")
                step_start = time.time()
                result_queue = multiprocessing.Queue()
                step_proc = multiprocessing.Process(
                    target=_run_step_in_process,
                    args=(
                        result_queue, devices, "step3.1",
                        f"python3 {{script_dir}}/5_subspec_simplifier_original.py -l --device {{device}} {{work_dir}}",
                        subdir, script_dir, max_parallel,
                    ),
                )
                step_proc.start()
                step_timed_out = False
                try:
                    results = result_queue.get(timeout=STEP_GROUP_TIMEOUT)
                except QueueEmpty:
                    step_timed_out = True
                    print(f"    Step 3.1 timed out (4h), stopping all and proceeding to next step")
                    step_proc.terminate()
                    step_proc.join(timeout=10)
                    if step_proc.is_alive():
                        step_proc.kill()
                        step_proc.join()
                    results = {d: -1 for d in devices}
                step_elapsed = time.time() - step_start
                with open(times_file, 'a') as f:
                    if step_timed_out:
                        f.write(f"step3.1: 4h +\n")
                    elif all(elapsed >= 0 for elapsed in results.values()):
                        print(f"    ✓ Completed in {format_time(step_elapsed)}")
                        f.write(f"step3.1: {format_time(step_elapsed)}\n")
                    else:
                        print(f"    ✗ Some devices failed after {format_time(step_elapsed)}")
                        f.write(f"step3.1: ERROR\n")

            if devices:
                time.sleep(STEP_SLEEP_BEFORE_SECONDS)
                print(f"  Running step3.2: 5_subspec_simplifier_original.py -f (parallel for {len(devices)} devices, timeout 4h per step)...")
                step_start = time.time()
                result_queue = multiprocessing.Queue()
                step_proc = multiprocessing.Process(
                    target=_run_step_in_process,
                    args=(
                        result_queue, devices, "step3.2",
                        f"python3 {{script_dir}}/5_subspec_simplifier_original.py -f --device {{device}} {{work_dir}}",
                        subdir, script_dir, max_parallel,
                    ),
                )
                step_proc.start()
                step_timed_out = False
                try:
                    results = result_queue.get(timeout=STEP_GROUP_TIMEOUT)
                except QueueEmpty:
                    step_timed_out = True
                    print(f"    Step 3.2 timed out (4h), stopping all and proceeding to next step")
                    step_proc.terminate()
                    step_proc.join(timeout=10)
                    if step_proc.is_alive():
                        step_proc.kill()
                        step_proc.join()
                    results = {d: -1 for d in devices}
                step_elapsed = time.time() - step_start
                with open(times_file, 'a') as f:
                    if step_timed_out:
                        f.write(f"step3.2: 4h +\n")
                    elif all(elapsed >= 0 for elapsed in results.values()):
                        print(f"    ✓ Completed in {format_time(step_elapsed)}")
                        f.write(f"step3.2: {format_time(step_elapsed)}\n")
                    else:
                        print(f"    ✗ Some devices failed after {format_time(step_elapsed)}")
                        f.write(f"step3.2: ERROR\n")

        # Step 4: 6_subspec_simplifier_fullsym.py — 4h timeout per step
        if run_step4:
            if devices:
                time.sleep(STEP_SLEEP_BEFORE_SECONDS)
                print(f"  Running step4.1: 6_subspec_simplifier_fullsym.py -l (parallel for {len(devices)} devices, timeout 4h per step)...")
                step_start = time.time()
                result_queue = multiprocessing.Queue()
                step_proc = multiprocessing.Process(
                    target=_run_step_in_process,
                    args=(
                        result_queue, devices, "step4.1",
                        f"python3 {{script_dir}}/6_subspec_simplifier_fullsym.py -l --device {{device}} {{work_dir}}",
                        subdir, script_dir, max_parallel,
                    ),
                )
                step_proc.start()
                step_timed_out = False
                try:
                    results = result_queue.get(timeout=STEP_GROUP_TIMEOUT)
                except QueueEmpty:
                    step_timed_out = True
                    print(f"    Step 4.1 timed out (4h), stopping all and proceeding to next step")
                    step_proc.terminate()
                    step_proc.join(timeout=10)
                    if step_proc.is_alive():
                        step_proc.kill()
                        step_proc.join()
                    results = {d: -1 for d in devices}
                step_elapsed = time.time() - step_start
                with open(times_file, 'a') as f:
                    if step_timed_out:
                        f.write(f"step4.1: 4h +\n")
                    elif all(elapsed >= 0 for elapsed in results.values()):
                        print(f"    ✓ Completed in {format_time(step_elapsed)}")
                        f.write(f"step4.1: {format_time(step_elapsed)}\n")
                    else:
                        print(f"    ✗ Some devices failed after {format_time(step_elapsed)}")
                        f.write(f"step4.1: ERROR\n")

            if devices:
                time.sleep(STEP_SLEEP_BEFORE_SECONDS)
                print(f"  Running step4.2: 6_subspec_simplifier_fullsym.py -f (parallel for {len(devices)} devices, timeout 4h per step)...")
                step_start = time.time()
                result_queue = multiprocessing.Queue()
                step_proc = multiprocessing.Process(
                    target=_run_step_in_process,
                    args=(
                        result_queue, devices, "step4.2",
                        f"python3 {{script_dir}}/6_subspec_simplifier_fullsym.py -f --device {{device}} {{work_dir}}",
                        subdir, script_dir, max_parallel,
                    ),
                )
                step_proc.start()
                step_timed_out = False
                try:
                    results = result_queue.get(timeout=STEP_GROUP_TIMEOUT)
                except QueueEmpty:
                    step_timed_out = True
                    print(f"    Step 4.2 timed out (4h), stopping all and proceeding to next step")
                    step_proc.terminate()
                    step_proc.join(timeout=10)
                    if step_proc.is_alive():
                        step_proc.kill()
                        step_proc.join()
                    results = {d: -1 for d in devices}
                step_elapsed = time.time() - step_start
                with open(times_file, 'a') as f:
                    if step_timed_out:
                        f.write(f"step4.2: 4h +\n")
                    elif all(elapsed >= 0 for elapsed in results.values()):
                        print(f"    ✓ Completed in {format_time(step_elapsed)}")
                        f.write(f"step4.2: {format_time(step_elapsed)}\n")
                    else:
                        print(f"    ✗ Some devices failed after {format_time(step_elapsed)}")
                        f.write(f"step4.2: ERROR\n")
        
        dir_elapsed = time.time() - dir_start_time
        print(f"  Completed {dir_name} in {format_time(dir_elapsed)}")
        print()
    
    total_elapsed = time.time() - total_start_time
    print(f"Total time: {format_time(total_elapsed)}")

if __name__ == "__main__":
    main()

