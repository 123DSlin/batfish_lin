#!/usr/bin/env python3
"""
Plot timing benchmark results from times.txt

Creates a single line plot with four lines:
1. Minesweeper (step1: z3 smt_encoding.smt2)
2. Subspecs (step2.1 + step2.2 + step2.3 + step2.4 + step2.5)
3. Subspecs Stable States (step3.4 + step3.5)
4. Subspecs Global Specification (step4.4 + step4.5)
"""

import re
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

def parse_time(time_str):
    """Parse time string like '1.50s', '3m 7.83s', '1h 22m 50.62s' to seconds"""
    time_str = time_str.strip()
    
    # Remove 's' suffix if present
    if time_str.endswith('s'):
        time_str = time_str[:-1]
    
    total_seconds = 0.0
    
    # Parse hours
    hour_match = re.search(r'(\d+)h', time_str)
    if hour_match:
        total_seconds += int(hour_match.group(1)) * 3600
        time_str = re.sub(r'\d+h\s*', '', time_str)
    
    # Parse minutes
    min_match = re.search(r'(\d+)m', time_str)
    if min_match:
        total_seconds += int(min_match.group(1)) * 60
        time_str = re.sub(r'\d+m\s*', '', time_str)
    
    # Parse seconds (remaining part)
    sec_match = re.search(r'([\d.]+)', time_str)
    if sec_match:
        total_seconds += float(sec_match.group(1))
    
    return total_seconds

def parse_times_file(file_path):
    """Parse times.txt file and extract timing data"""
    data = {}
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Find all directory sections (standard format: [DIRECTORY] ... [END_DIRECTORY])
    dir_sections = re.findall(r'\[DIRECTORY\](.*?)\[END_DIRECTORY\]', content, re.DOTALL)
    
    for section_text in dir_sections:
        # Extract directory name
        name_match = re.search(r'name=(.+)', section_text)
        if not name_match:
            continue
        dir_name = name_match.group(1).strip()
        
        # Parse step times (format: stepX.X: time-value or stepX.X: ERROR)
        times = {}
        step_pattern = r'step(\d+(?:\.\d+)?): ([\d.]+[smh]?(?:\s+[\d.]+[smh]?)*|ERROR)'
        matches = re.findall(step_pattern, section_text)
        
        for step_name, time_str in matches:
            if time_str == 'ERROR':
                times[step_name] = 0  # Treat ERROR as 0 for plotting
            else:
                times[step_name] = parse_time(time_str)
        
        data[dir_name] = times
    
    return data

def main():
    # Parse command line arguments
    import sys
    plot_all_steps = False
    work_dir = None
    
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '-a':
            plot_all_steps = True
        elif arg in ['-h', '--help']:
            print("Usage: python tools/graph.py [-a] <work_dir>")
            print("Options:")
            print("  -a         Plot all steps (step1, step2, step3, step4)")
            print("             Without -a: only plot step1 and step2")
            print("  <work_dir> Directory containing times.txt")
            sys.exit(0)
        elif arg.startswith('-'):
            print(f"Error: Unknown option: {arg}")
            print("Usage: python tools/graph.py [-a] <work_dir>")
            sys.exit(1)
        else:
            if work_dir is None:
                work_dir = arg
            else:
                print(f"Error: Multiple working directories specified")
                sys.exit(1)
        i += 1
    
    if work_dir is None:
        print("Error: Working directory not specified")
        print("Usage: python tools/graph.py [-a] <work_dir>")
        sys.exit(1)
        
    work_path = Path(work_dir)
    
    # Parse times.txt
    times_file = work_path / "times.txt"
    if not times_file.exists():
        print(f"Error: {times_file} not found")
        return
    
    data = parse_times_file(times_file)
    
    # Prepare data for plotting
    # Mapping: directory name -> (display name, node count)
    configs = [
        ('smt_output_fattree04pol', 'FT4', 20),
        ('smt_output_fattree08pol', 'FT8', 80),
        ('smt_output_fattree12pol', 'FT12', 180),
        ('smt_output_fattree16pol', 'FT16', 320),
        ('smt_output_fattree20pol', 'FT20', 500),
        ('smt_output_fattree24pol', 'FT24', 720),
        ('smt_output_fattree28pol', 'FT28', 980),
        ('smt_output_fattree32pol', 'FT32', 1280)
    ]
    
    # Check which configurations are missing
    missing_configs = []
    for dir_name, display_name, nodes in configs:
        if dir_name not in data:
            missing_configs.append((display_name, dir_name))
    
    if missing_configs:
        print(f"\nNote: {len(missing_configs)} configuration(s) not found in times.txt (will be skipped in plot):")
        for display_name, dir_name in missing_configs:
            print(f"  - {display_name} ({dir_name})")
        print()
    
    # Always prepare data for all 8 configurations
    minesweeper_times = []
    subspecs_times = []
    subspecs_stable_states_times = []
    subspecs_global_specs_times = []
    node_counts = []
    display_names = []
    
    for dir_name, display_name, nodes in configs:
        node_counts.append(nodes)
        display_names.append(display_name)
        
        if dir_name not in data:
            # Missing data - use None so matplotlib skips these points
            minesweeper_times.append(None)
            subspecs_times.append(None)
            # Always append to SS and GS lists (even if not plotting all steps)
            subspecs_stable_states_times.append(None)
            subspecs_global_specs_times.append(None)
            print(f"{display_name} ({nodes}): [No data]")
        else:
            times = data[dir_name]
            
            # Calculate objects:
            # 1. Minesweeper = step1
            minesweeper_time = times.get('1', 0)
            
            # 2. Subspecs = step2.1 + step2.2 + step2.3 + step2.4 + step2.5
            subspecs_time = (
                times.get('2.1', 0) +
                times.get('2.2', 0) +
                times.get('2.3', 0) +
                times.get('2.4', 0) +
                times.get('2.5', 0)
            )
            
            minesweeper_times.append(minesweeper_time)
            subspecs_times.append(subspecs_time)
            
            print(f"{display_name} ({nodes}):")
            print(f"  Minesweeper: {minesweeper_time:.2f}s")
            print(f"  Subspecs: {subspecs_time:.2f}s")
            
            if plot_all_steps:
                # 3. Subspecs Stable States = step3.4 + step3.5
                subspecs_stable_states_time = (
                    times.get('3.4', 0) +
                    times.get('3.5', 0)
                )
                
                # 4. Subspecs Global Specification = step4.4 + step4.5
                subspecs_global_specs_time = (
                    times.get('4.4', 0) +
                    times.get('4.5', 0)
                )
                
                subspecs_stable_states_times.append(subspecs_stable_states_time)
                subspecs_global_specs_times.append(subspecs_global_specs_time)
                print(f"  Subspecs (SS): {subspecs_stable_states_time:.2f}s")
                print(f"  Subspecs (GS): {subspecs_global_specs_time:.2f}s")
            else:
                # Even if not plotting all steps, append None to maintain list length
                subspecs_stable_states_times.append(None)
                subspecs_global_specs_times.append(None)
    
    # Create plot
    fig, ax = plt.subplots(1, 1, figsize=(12, 7))
    
    # Use evenly spaced x positions (0, 1, 2, ..., 7) instead of node counts
    num_configs = len(node_counts)
    x_positions = np.arange(num_configs)
    
    # Ensure we have lists for all four series (fill with None if not available)
    if not plot_all_steps:
        # If not plotting all steps, still create empty lists for SS and GS
        if len(subspecs_stable_states_times) == 0:
            subspecs_stable_states_times = [None] * num_configs
        if len(subspecs_global_specs_times) == 0:
            subspecs_global_specs_times = [None] * num_configs
    
    # Plot lines (matplotlib will automatically skip None values)
    # Always plot all four lines to ensure legend shows all four items
    ax.plot(x_positions, minesweeper_times, marker='o', linewidth=2, markersize=8, 
            color='#2E86AB', label='Minesweeper', linestyle='-')
    ax.plot(x_positions, subspecs_times, marker='s', linewidth=2, markersize=8, 
            color='#C73E1D', label='Subspecs', linestyle='-')
    ax.plot(x_positions, subspecs_stable_states_times, marker='^', linewidth=2, markersize=8, 
            color='#F18F01', label='Subspecs (SS)', linestyle='-')
    ax.plot(x_positions, subspecs_global_specs_times, marker='d', linewidth=2, markersize=8, 
            color='#DAA520', label='Subspecs (GS)', linestyle='-')
    
    ax.set_ylabel('Time (minutes)', fontsize=20)
    ax.set_xticks(x_positions)
    ax.set_xticklabels([f'{name}\n({nodes})' for name, nodes in zip(display_names, node_counts)], fontsize=18)
    
    # Set x-axis limits with padding on both sides
    ax.set_xlim(x_positions[0] - 0.5, x_positions[-1] + 0.5)
    
    # Set y-axis ticks to fixed minute values (0, 15, 30, 45, 60, 75, 90, 105, 120 mins)
    y_ticks_minutes = [0, 15, 30, 45, 60, 75, 90, 105, 120]
    y_ticks_seconds = [m * 60 for m in y_ticks_minutes]
    ax.set_yticks(y_ticks_seconds)
    ax.set_yticklabels([str(m) for m in y_ticks_minutes], fontsize=18)
    # Set y-axis limits with padding at the top (0 to 130 minutes to leave space above 120)
    ax.set_ylim(0, 130 * 60)
    
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.legend(fontsize=18, loc='upper left')
    
    plt.tight_layout()
    
    # Save the plot
    output_file = work_path / "timing_comparison.png"
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"\nPlot saved to: {output_file}")
    
    # Also save as PDF
    output_file_pdf = work_path / "timing_comparison.pdf"
    plt.savefig(output_file_pdf, bbox_inches='tight')
    print(f"Plot saved to: {output_file_pdf}")
    
    plt.show()

if __name__ == "__main__":
    main()

