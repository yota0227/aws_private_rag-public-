#!/usr/bin/env python3
"""
Performance Results Parser

This script parses performance test results from Trinity regression runs.
It supports addr_pinger and trinity_performance tests (sc, mc2, and mc4 variants).
It extracts performance data from perf_res_*.txt files and outputs to CSV.

Usage: python parse_perf_logs.py <path_to_out_directory>
"""

import sys
import re
import csv
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional

try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    PLOTTING_AVAILABLE = True
except ImportError:
    PLOTTING_AVAILABLE = False


# Theoretical throughput values (B/cycle) based on transfer size
# Linear from 0 to 64 B/cycle from 4 to 128 bytes, then constant at 64
THEORETICAL_VALUES = {
    4: 4.0,
    32: 32.0,
    64: 64.0,
    128: 64.0,
    256: 64.0,
    512: 64.0,
    1024: 64.0,
    2048: 64.0,
    4096: 64.0,
}


def get_theoretical_throughput(transfer_size: float) -> float:
    """Get theoretical throughput value for given transfer size."""
    # Direct lookup for defined sizes
    if transfer_size in THEORETICAL_VALUES:
        return THEORETICAL_VALUES[transfer_size]

    # Linear interpolation between defined points
    sorted_sizes = sorted(THEORETICAL_VALUES.keys())

    # Find the two points to interpolate between
    for i in range(len(sorted_sizes) - 1):
        x1, x2 = sorted_sizes[i], sorted_sizes[i + 1]
        if x1 <= transfer_size <= x2:
            y1, y2 = THEORETICAL_VALUES[x1], THEORETICAL_VALUES[x2]
            # Linear interpolation: y = y1 + (y2-y1) * (x-x1) / (x2-x1)
            return y1 + (y2 - y1) * (transfer_size - x1) / (x2 - x1)

    # For sizes beyond our range
    if transfer_size > max(sorted_sizes):
        return THEORETICAL_VALUES[max(sorted_sizes)]
    elif transfer_size < min(sorted_sizes):
        return 0.0

    return 0.0


def setup_logging(log_file: Path, verbose: bool = False) -> None:
    """Setup logging configuration."""
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )

    # Setup file handler (always enabled)
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # Setup root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)

    # Add console handler only if verbose mode is enabled
    if verbose:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)
        logger.addHandler(console_handler)

    # Log matplotlib availability
    if not PLOTTING_AVAILABLE:
        logging.warning("matplotlib not available. Plotting functionality disabled.")
        logging.info("To enable plotting, install matplotlib: pip install matplotlib")


def parse_addr_pinger_perf_file(perf_path: Path) -> Optional[Dict]:
    """
    Parse a single addr_pinger perf_res_*.txt file and extract performance data.

    Returns dict with extracted data or None if parsing fails.
    """
    try:
        with open(perf_path, 'r') as f:
            content = f.read()
    except (IOError, OSError) as e:
        logging.warning(f"Could not read {perf_path}: {e}")
        return None

    # Initialize result dictionary
    result = {
        'test_dir': perf_path.parent.name,
        'transfer_size_per_chunk': None,
        'total_data_transferred': None,
        'write_first_timestamp': None,
        'write_last_timestamp': None,
        'write_latency': None,
        'write_throughput': None,
        'write_duration': None,
        'read_first_timestamp': None,
        'read_last_timestamp': None,
        'read_latency': None,
        'read_throughput': None,
        'read_duration': None,
        'noc2axi_write_buffer_latency': None,
        'noc2axi_read_buffer_latency': None
    }

    # Parse transfer size per chunk
    chunk_size_match = re.search(r'Transfer size per chunk:\s*(\d+)\s*bytes', content)
    if chunk_size_match:
        result['transfer_size_per_chunk'] = int(chunk_size_match.group(1))

    # Parse total data transferred
    total_data_match = re.search(r'Total data transferred:\s*(\d+)\s*bytes.*?\(([\d.]+\s*\w+)\)', content)
    if total_data_match:
        result['total_data_transferred'] = f"{total_data_match.group(1)} bytes ({total_data_match.group(2)})"

    # Parse write performance
    write_first_match = re.search(r'First write request timestamp:\s*([\d.]+)\s*ns', content)
    write_last_match = re.search(r'Last write response timestamp:\s*([\d.]+)\s*ns', content)
    write_latency_match = re.search(r'Write latency:\s*([\d.]+)\s*ns', content)
    write_throughput_match = re.search(r'Write throughput:\s*([\d.]+)\s*B/cycle', content)

    if write_first_match and write_last_match:
        result['write_first_timestamp'] = float(write_first_match.group(1))
        result['write_last_timestamp'] = float(write_last_match.group(1))
        result['write_duration'] = result['write_last_timestamp'] - result['write_first_timestamp']

    if write_latency_match:
        result['write_latency'] = float(write_latency_match.group(1))

    if write_throughput_match:
        result['write_throughput'] = float(write_throughput_match.group(1))

    # Parse read performance
    read_first_match = re.search(r'First read request timestamp:\s*([\d.]+)\s*ns', content)
    read_last_match = re.search(r'Last read data timestamp:\s*([\d.]+)\s*ns', content)
    read_latency_match = re.search(r'Read latency:\s*([\d.]+)\s*ns', content)
    read_throughput_match = re.search(r'Read throughput:\s*([\d.]+)\s*B/cycle', content)

    if read_first_match and read_last_match:
        result['read_first_timestamp'] = float(read_first_match.group(1))
        result['read_last_timestamp'] = float(read_last_match.group(1))
        result['read_duration'] = result['read_last_timestamp'] - result['read_first_timestamp']

    if read_latency_match:
        result['read_latency'] = float(read_latency_match.group(1))

    if read_throughput_match:
        result['read_throughput'] = float(read_throughput_match.group(1))

    # Parse noc2axi buffer latencies
    noc2axi_write_match = re.search(r'Noc2Axi write buffer latency:\s*([\d.]+)\s*cycles', content)
    noc2axi_read_match = re.search(r'Noc2Axi read buffer latency:\s*([\d.]+)\s*cycles', content)

    if noc2axi_write_match:
        result['noc2axi_write_buffer_latency'] = float(noc2axi_write_match.group(1))

    if noc2axi_read_match:
        result['noc2axi_read_buffer_latency'] = float(noc2axi_read_match.group(1))

    # Check if we found at least basic data
    if chunk_size_match or total_data_match or write_first_match or read_first_match:
        return result
    else:
        logging.warning(f"No performance data found in {perf_path}")
        return None


def parse_trinity_performance_perf_file(perf_path: Path) -> Optional[Dict]:
    """
    Parse a single trinity_performance perf_res_*.txt file and extract performance data.
    Trinity performance tests may have similar format to addr_pinger but with different approach.

    Returns dict with extracted data or None if parsing fails.
    """
    try:
        with open(perf_path, 'r') as f:
            content = f.read()
    except (IOError, OSError) as e:
        logging.warning(f"Could not read {perf_path}: {e}")
        return None

    # Initialize result dictionary with fields matching addr_pinger format
    result = {
        'test_dir': perf_path.parent.name,
        'transfer_size': None,
        'number_of_transfers': None,
        'total_data_transferred': None,
        'write_first_timestamp': None,
        'write_last_timestamp': None,
        'write_latency': None,
        'write_throughput': None,
        'write_duration': None,
        'read_first_timestamp': None,
        'read_last_timestamp': None,
        'read_latency': None,
        'read_throughput': None,
        'read_duration': None,
        'noc2axi_read_buffer_latency': None,
        'noc2axi_write_buffer_latency': None
    }

    # Parse transfer size (for trinity_performance, might be different pattern)
    transfer_size_match = re.search(r'Transfer size(?:\s+per\s+chunk)?:\s*(\d+)\s*bytes', content)
    if transfer_size_match:
        result['transfer_size'] = int(transfer_size_match.group(1))

    # Parse number of transfers (specific to trinity_performance)
    num_transfers_match = re.search(r'Number of transfers:\s*(\d+)', content)
    if num_transfers_match:
        result['number_of_transfers'] = int(num_transfers_match.group(1))

    # Parse total data transferred
    total_data_match = re.search(r'Total data transferred:\s*(\d+)\s*bytes.*?\(([\d.]+\s*\w+)\)', content)
    if total_data_match:
        result['total_data_transferred'] = f"{total_data_match.group(1)} bytes ({total_data_match.group(2)})"

    # Parse write performance
    write_first_match = re.search(r'First write request timestamp:\s*([\d.]+)\s*ns', content)
    write_last_match = re.search(r'Last write response timestamp:\s*([\d.]+)\s*ns', content)
    write_latency_match = re.search(r'Write latency:\s*([\d.]+)\s*ns', content)
    write_throughput_match = re.search(r'Write throughput:\s*([\d.]+)\s*B/cycle', content)

    if write_first_match and write_last_match:
        result['write_first_timestamp'] = float(write_first_match.group(1))
        result['write_last_timestamp'] = float(write_last_match.group(1))
        result['write_duration'] = result['write_last_timestamp'] - result['write_first_timestamp']

    if write_latency_match:
        result['write_latency'] = float(write_latency_match.group(1))

    if write_throughput_match:
        result['write_throughput'] = float(write_throughput_match.group(1))

    # Parse read performance
    read_first_match = re.search(r'First read request timestamp:\s*([\d.]+)\s*ns', content)
    read_last_match = re.search(r'Last read data timestamp:\s*([\d.]+)\s*ns', content)
    read_latency_match = re.search(r'Read latency:\s*([\d.]+)\s*ns', content)
    read_throughput_match = re.search(r'Read throughput:\s*([\d.]+)\s*B/cycle', content)

    if read_first_match and read_last_match:
        result['read_first_timestamp'] = float(read_first_match.group(1))
        result['read_last_timestamp'] = float(read_last_match.group(1))
        result['read_duration'] = result['read_last_timestamp'] - result['read_first_timestamp']

    if read_latency_match:
        result['read_latency'] = float(read_latency_match.group(1))

    if read_throughput_match:
        result['read_throughput'] = float(read_throughput_match.group(1))

    # Parse noc2axi buffer latencies (same as addr_pinger tests)
    noc2axi_write_match = re.search(r'Noc2Axi write buffer latency:\s*([\d.]+)\s*cycles', content)
    noc2axi_read_match = re.search(r'Noc2Axi read buffer latency:\s*([\d.]+)\s*cycles', content)

    if noc2axi_write_match:
        result['noc2axi_write_buffer_latency'] = float(noc2axi_write_match.group(1))

    if noc2axi_read_match:
        result['noc2axi_read_buffer_latency'] = float(noc2axi_read_match.group(1))

    # Check if we found at least basic data
    if transfer_size_match or total_data_match or write_first_match or read_first_match:
        return result
    else:
        logging.warning(f"No performance data found in {perf_path}")
        return None


def create_throughput_vs_transfer_size_with_noc2axi_lines(results: List[Dict], output_dir: Path) -> None:
    """Create throughput vs transfer size plot with lines for different noc2axi latencies + theoretical line."""
    if not PLOTTING_AVAILABLE:
        logging.info("Skipping throughput vs transfer size plot - matplotlib not available")
        return

    if not results:
        logging.warning("No data available for throughput vs transfer size plotting")
        return

    # Group data by noc2axi latency values
    noc2axi_groups = {}
    for result in results:
        if (result['transfer_size_per_chunk'] is not None and
            result['noc2axi_write_buffer_latency'] is not None and
            result['write_throughput'] is not None and
            result['read_throughput'] is not None):

            noc2axi_latency = result['noc2axi_write_buffer_latency']
            if noc2axi_latency not in noc2axi_groups:
                noc2axi_groups[noc2axi_latency] = {
                    'transfer_sizes': [],
                    'write_throughputs': [],
                    'read_throughputs': []
                }

            noc2axi_groups[noc2axi_latency]['transfer_sizes'].append(result['transfer_size_per_chunk'])
            noc2axi_groups[noc2axi_latency]['write_throughputs'].append(result['write_throughput'])
            noc2axi_groups[noc2axi_latency]['read_throughputs'].append(result['read_throughput'])

    if not noc2axi_groups:
        logging.warning("No valid data found for throughput vs transfer size plotting")
        return

    plt.figure(figsize=(12, 8))
    colors = ['b', 'r', 'g', 'c', 'm', 'y', 'k']

    # Write throughput subplot
    plt.subplot(2, 1, 1)
    color_idx = 0

    for noc2axi_latency, data in sorted(noc2axi_groups.items()):
        sorted_data = sorted(zip(data['transfer_sizes'], data['write_throughputs']))
        transfer_sizes, write_throughputs = zip(*sorted_data)

        color = colors[color_idx % len(colors)]
        plt.plot(transfer_sizes, write_throughputs, f'{color}o-',
                label=f'Noc2Axi {int(noc2axi_latency)} cycles', markersize=6, linewidth=2)
        color_idx += 1

    # Add theoretical line for write
    if noc2axi_groups:
        theoretical_sizes = [4, 64, 128, 256, 512, 1024, 2048, 4096]
        theoretical_throughputs = [get_theoretical_throughput(ts) for ts in theoretical_sizes]
        plt.plot(theoretical_sizes, theoretical_throughputs, 'k--',
                label='Theoretical', linewidth=2, alpha=0.7)

    plt.xlabel('Transfer Size per Chunk (bytes)')
    plt.ylabel('Write Throughput (B/cycle)')
    plt.title('Write Throughput vs Transfer Size')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.ylim(0, 70)
    plt.xlim(0, 4200)
    plt.xticks([4, 64, 128, 256, 512, 1024, 2048, 4096],
               ['4', '64', '128', '256', '512', '1024', '2048', '4096'], rotation=45)

    # Read throughput subplot
    plt.subplot(2, 1, 2)
    color_idx = 0

    for noc2axi_latency, data in sorted(noc2axi_groups.items()):
        sorted_data = sorted(zip(data['transfer_sizes'], data['read_throughputs']))
        transfer_sizes, read_throughputs = zip(*sorted_data)

        color = colors[color_idx % len(colors)]
        plt.plot(transfer_sizes, read_throughputs, f'{color}o-',
                label=f'Noc2Axi {int(noc2axi_latency)} cycles', markersize=6, linewidth=2)
        color_idx += 1

    # Add theoretical line for read
    if noc2axi_groups:
        theoretical_sizes = [4, 64, 128, 256, 512, 1024, 2048, 4096]
        theoretical_throughputs = [get_theoretical_throughput(ts) for ts in theoretical_sizes]
        plt.plot(theoretical_sizes, theoretical_throughputs, 'k--',
                label='Theoretical', linewidth=2, alpha=0.7)

    plt.xlabel('Transfer Size per Chunk (bytes)')
    plt.ylabel('Read Throughput (B/cycle)')
    plt.title('Read Throughput vs Transfer Size')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.ylim(0, 70)
    plt.xlim(0, 4200)
    plt.xticks([4, 64, 128, 256, 512, 1024, 2048, 4096],
               ['4', '64', '128', '256', '512', '1024', '2048', '4096'], rotation=45)

    plt.tight_layout()

    plot_path = output_dir / 'throughput_vs_transfer_size.png'
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    logging.info(f"Throughput vs transfer size plot saved to {plot_path}")
    plt.close()


def create_throughput_vs_noc2axi_with_transfer_size_lines(results: List[Dict], output_dir: Path) -> None:
    """Create throughput vs noc2axi latency plot with lines for different transfer sizes."""
    if not PLOTTING_AVAILABLE:
        logging.info("Skipping throughput vs noc2axi plot - matplotlib not available")
        return

    if not results:
        logging.warning("No data available for throughput vs noc2axi plotting")
        return

    # Group data by transfer size
    transfer_size_groups = {}
    for result in results:
        if (result['transfer_size_per_chunk'] is not None and
            result['noc2axi_write_buffer_latency'] is not None and
            result['write_throughput'] is not None and
            result['read_throughput'] is not None):

            transfer_size = result['transfer_size_per_chunk']
            if transfer_size not in transfer_size_groups:
                transfer_size_groups[transfer_size] = {
                    'noc2axi_latencies': [],
                    'write_throughputs': [],
                    'read_throughputs': []
                }

            transfer_size_groups[transfer_size]['noc2axi_latencies'].append(result['noc2axi_write_buffer_latency'])
            transfer_size_groups[transfer_size]['write_throughputs'].append(result['write_throughput'])
            transfer_size_groups[transfer_size]['read_throughputs'].append(result['read_throughput'])

    if not transfer_size_groups:
        logging.warning("No valid data found for throughput vs noc2axi plotting")
        return

    plt.figure(figsize=(12, 8))
    colors = ['b', 'r', 'g', 'c', 'm', 'y', 'k']

    # Write throughput subplot
    plt.subplot(2, 1, 1)
    color_idx = 0

    for transfer_size, data in sorted(transfer_size_groups.items()):
        if len(data['noc2axi_latencies']) < 1:
            continue

        sorted_data = sorted(zip(data['noc2axi_latencies'], data['write_throughputs']))
        noc2axi_latencies, write_throughputs = zip(*sorted_data)

        color = colors[color_idx % len(colors)]
        plt.plot(noc2axi_latencies, write_throughputs, f'{color}o-',
                markersize=6, linewidth=2, label=f'{int(transfer_size)} bytes')
        color_idx += 1

    plt.xlabel('Noc2Axi Buffer Latency (cycles)')
    plt.ylabel('Write Throughput (B/cycle)')
    plt.title('Write Throughput vs Noc2Axi Buffer Latency')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.ylim(0, 70)

    # Read throughput subplot
    plt.subplot(2, 1, 2)
    color_idx = 0

    for transfer_size, data in sorted(transfer_size_groups.items()):
        if len(data['noc2axi_latencies']) < 1:
            continue

        sorted_data = sorted(zip(data['noc2axi_latencies'], data['read_throughputs']))
        noc2axi_latencies, read_throughputs = zip(*sorted_data)

        color = colors[color_idx % len(colors)]
        plt.plot(noc2axi_latencies, read_throughputs, f'{color}o-',
                markersize=6, linewidth=2, label=f'{int(transfer_size)} bytes')
        color_idx += 1

    plt.xlabel('Noc2Axi Buffer Latency (cycles)')
    plt.ylabel('Read Throughput (B/cycle)')
    plt.title('Read Throughput vs Noc2Axi Buffer Latency')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.ylim(0, 70)

    plt.tight_layout()

    plot_path = output_dir / 'throughput_vs_noc2axi_latency.png'
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    logging.info(f"Throughput vs noc2axi latency plot saved to {plot_path}")
    plt.close()


def create_latency_vs_transfer_size_with_noc2axi_lines(results: List[Dict], output_dir: Path) -> None:
    """Create overall latency vs transfer size plot with lines for different noc2axi latencies."""
    if not PLOTTING_AVAILABLE:
        logging.info("Skipping latency vs transfer size plot - matplotlib not available")
        return

    if not results:
        logging.warning("No data available for latency vs transfer size plotting")
        return

    # Group data by noc2axi latency values
    noc2axi_groups = {}
    for result in results:
        if (result['transfer_size_per_chunk'] is not None and
            result['noc2axi_write_buffer_latency'] is not None and
            result['write_latency'] is not None and
            result['read_latency'] is not None):

            noc2axi_latency = result['noc2axi_write_buffer_latency']
            if noc2axi_latency not in noc2axi_groups:
                noc2axi_groups[noc2axi_latency] = {
                    'transfer_sizes': [],
                    'write_latencies': [],
                    'read_latencies': []
                }

            noc2axi_groups[noc2axi_latency]['transfer_sizes'].append(result['transfer_size_per_chunk'])
            noc2axi_groups[noc2axi_latency]['write_latencies'].append(result['write_latency'])
            noc2axi_groups[noc2axi_latency]['read_latencies'].append(result['read_latency'])

    if not noc2axi_groups:
        logging.warning("No valid data found for latency vs transfer size plotting")
        return

    plt.figure(figsize=(12, 8))
    colors = ['b', 'r', 'g', 'c', 'm', 'y', 'k']

    # Write latency subplot
    plt.subplot(2, 1, 1)
    color_idx = 0

    for noc2axi_latency, data in sorted(noc2axi_groups.items()):
        sorted_data = sorted(zip(data['transfer_sizes'], data['write_latencies']))
        transfer_sizes, write_latencies = zip(*sorted_data)

        color = colors[color_idx % len(colors)]
        plt.plot(transfer_sizes, write_latencies, f'{color}o-',
                label=f'Noc2Axi {int(noc2axi_latency)} cycles', markersize=6, linewidth=2)
        color_idx += 1

    plt.xlabel('Transfer Size per Chunk (bytes)')
    plt.ylabel('Write Latency (ns)')
    plt.title('Write Latency vs Transfer Size')
    plt.legend()
    plt.grid(True, alpha=0.3)

    # Read latency subplot
    plt.subplot(2, 1, 2)
    color_idx = 0

    for noc2axi_latency, data in sorted(noc2axi_groups.items()):
        sorted_data = sorted(zip(data['transfer_sizes'], data['read_latencies']))
        transfer_sizes, read_latencies = zip(*sorted_data)

        color = colors[color_idx % len(colors)]
        plt.plot(transfer_sizes, read_latencies, f'{color}o-',
                label=f'Noc2Axi {int(noc2axi_latency)} cycles', markersize=6, linewidth=2)
        color_idx += 1

    plt.xlabel('Transfer Size per Chunk (bytes)')
    plt.ylabel('Read Latency (ns)')
    plt.title('Read Latency vs Transfer Size')
    plt.legend()
    plt.grid(True, alpha=0.3)

    plt.tight_layout()

    plot_path = output_dir / 'latency_vs_transfer_size.png'
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    logging.info(f"Latency vs transfer size plot saved to {plot_path}")
    plt.close()


def create_trinity_throughput_vs_transfer_size_with_axi_lines(results: List[Dict], output_dir: Path, test_type: str = 'sc') -> None:
    """Create throughput vs transfer size plot for trinity_performance tests with lines for different AXI latencies."""
    if not PLOTTING_AVAILABLE:
        logging.info("Skipping trinity throughput vs transfer size plot - matplotlib not available")
        return

    if not results:
        logging.warning("No data available for trinity throughput vs transfer size plotting")
        return

    # Group data by noc2axi latency values (same as addr_pinger)
    noc2axi_groups = {}
    for result in results:
        if (result['transfer_size'] is not None and
            result['noc2axi_write_buffer_latency'] is not None and
            result['write_throughput'] is not None and
            result['read_throughput'] is not None):

            noc2axi_latency = result['noc2axi_write_buffer_latency']
            if noc2axi_latency not in noc2axi_groups:
                noc2axi_groups[noc2axi_latency] = {
                    'transfer_sizes': [],
                    'write_throughputs': [],
                    'read_throughputs': []
                }

            noc2axi_groups[noc2axi_latency]['transfer_sizes'].append(result['transfer_size'])
            noc2axi_groups[noc2axi_latency]['write_throughputs'].append(result['write_throughput'])
            noc2axi_groups[noc2axi_latency]['read_throughputs'].append(result['read_throughput'])

    if not noc2axi_groups:
        logging.warning("No valid data found for trinity throughput vs transfer size plotting")
        return

    plt.figure(figsize=(12, 8))
    colors = ['b', 'r', 'g', 'c', 'm', 'y', 'k', 'orange']

    # Write throughput subplot
    plt.subplot(2, 1, 1)
    color_idx = 0

    for noc2axi_latency, data in sorted(noc2axi_groups.items()):
        sorted_data = sorted(zip(data['transfer_sizes'], data['write_throughputs']))
        transfer_sizes, write_throughputs = zip(*sorted_data)

        color = colors[color_idx % len(colors)]
        plt.plot(transfer_sizes, write_throughputs, f'{color}o-',
                label=f'Noc2Axi {int(noc2axi_latency)} cycles', markersize=6, linewidth=2)
        color_idx += 1

    # Add theoretical line for write
    if noc2axi_groups:
        theoretical_sizes = [128, 256, 512, 1024, 2048, 4096]
        theoretical_throughputs = [get_theoretical_throughput(ts) for ts in theoretical_sizes]
        plt.plot(theoretical_sizes, theoretical_throughputs, 'k--',
                label='Theoretical', linewidth=2, alpha=0.7)

    plt.xlabel('Transfer Size (bytes)')
    plt.ylabel('Write Throughput (B/cycle)')
    plt.title(f'Trinity Performance {test_type.upper()}: Write Throughput vs Transfer Size')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.ylim(0, 70)
    plt.xlim(0, 4200)
    plt.xticks([128, 256, 512, 1024, 2048, 4096],
               ['128', '256', '512', '1024', '2048', '4096'], rotation=45)

    # Read throughput subplot
    plt.subplot(2, 1, 2)
    color_idx = 0

    for noc2axi_latency, data in sorted(noc2axi_groups.items()):
        sorted_data = sorted(zip(data['transfer_sizes'], data['read_throughputs']))
        transfer_sizes, read_throughputs = zip(*sorted_data)

        color = colors[color_idx % len(colors)]
        plt.plot(transfer_sizes, read_throughputs, f'{color}o-',
                label=f'Noc2Axi {int(noc2axi_latency)} cycles', markersize=6, linewidth=2)
        color_idx += 1

    # Add theoretical line for read
    if noc2axi_groups:
        theoretical_sizes = [128, 256, 512, 1024, 2048, 4096]
        theoretical_throughputs = [get_theoretical_throughput(ts) for ts in theoretical_sizes]
        plt.plot(theoretical_sizes, theoretical_throughputs, 'k--',
                label='Theoretical', linewidth=2, alpha=0.7)

    plt.xlabel('Transfer Size (bytes)')
    plt.ylabel('Read Throughput (B/cycle)')
    plt.title(f'Trinity Performance {test_type.upper()}: Read Throughput vs Transfer Size')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.ylim(0, 70)
    plt.xlim(0, 4200)
    plt.xticks([128, 256, 512, 1024, 2048, 4096],
               ['128', '256', '512', '1024', '2048', '4096'], rotation=45)

    plt.tight_layout()

    plot_path = output_dir / f'trinity_{test_type}_throughput_vs_transfer_size.png'
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    logging.info(f"Trinity {test_type} throughput vs transfer size plot saved to {plot_path}")
    plt.close()


def create_trinity_throughput_vs_axi_with_transfer_size_lines(results: List[Dict], output_dir: Path, test_type: str = 'sc') -> None:
    """Create throughput vs AXI latency plot for trinity_performance tests with lines for different transfer sizes."""
    if not PLOTTING_AVAILABLE:
        logging.info("Skipping trinity throughput vs AXI plot - matplotlib not available")
        return

    if not results:
        logging.warning("No data available for trinity throughput vs AXI plotting")
        return

    # Group data by transfer size
    transfer_size_groups = {}
    for result in results:
        if (result['transfer_size'] is not None and
            result['noc2axi_write_buffer_latency'] is not None and
            result['write_throughput'] is not None and
            result['read_throughput'] is not None):

            transfer_size = result['transfer_size']
            if transfer_size not in transfer_size_groups:
                transfer_size_groups[transfer_size] = {
                    'noc2axi_latencies': [],
                    'write_throughputs': [],
                    'read_throughputs': []
                }

            transfer_size_groups[transfer_size]['noc2axi_latencies'].append(result['noc2axi_write_buffer_latency'])
            transfer_size_groups[transfer_size]['write_throughputs'].append(result['write_throughput'])
            transfer_size_groups[transfer_size]['read_throughputs'].append(result['read_throughput'])

    if not transfer_size_groups:
        logging.warning("No valid data found for trinity throughput vs AXI plotting")
        return

    plt.figure(figsize=(12, 8))
    colors = ['b', 'r', 'g', 'c', 'm', 'y', 'k', 'orange']

    # Write throughput subplot
    plt.subplot(2, 1, 1)
    color_idx = 0

    for transfer_size, data in sorted(transfer_size_groups.items()):
        if len(data['noc2axi_latencies']) < 1:
            continue

        sorted_data = sorted(zip(data['noc2axi_latencies'], data['write_throughputs']))
        noc2axi_latencies, write_throughputs = zip(*sorted_data)

        color = colors[color_idx % len(colors)]
        plt.plot(noc2axi_latencies, write_throughputs, f'{color}o-',
                markersize=6, linewidth=2, label=f'{int(transfer_size)} bytes')
        color_idx += 1

    plt.xlabel('Noc2Axi Buffer Latency (cycles)')
    plt.ylabel('Write Throughput (B/cycle)')
    plt.title(f'Trinity Performance {test_type.upper()}: Write Throughput vs Noc2Axi Buffer Latency')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.ylim(0, 70)

    # Read throughput subplot
    plt.subplot(2, 1, 2)
    color_idx = 0

    for transfer_size, data in sorted(transfer_size_groups.items()):
        if len(data['noc2axi_latencies']) < 1:
            continue

        sorted_data = sorted(zip(data['noc2axi_latencies'], data['read_throughputs']))
        noc2axi_latencies, read_throughputs = zip(*sorted_data)

        color = colors[color_idx % len(colors)]
        plt.plot(noc2axi_latencies, read_throughputs, f'{color}o-',
                markersize=6, linewidth=2, label=f'{int(transfer_size)} bytes')
        color_idx += 1

    plt.xlabel('Noc2Axi Buffer Latency (cycles)')
    plt.ylabel('Read Throughput (B/cycle)')
    plt.title(f'Trinity Performance {test_type.upper()}: Read Throughput vs Noc2Axi Buffer Latency')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.ylim(0, 70)

    plt.tight_layout()

    plot_path = output_dir / f'trinity_{test_type}_throughput_vs_noc2axi_latency.png'
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    logging.info(f"Trinity {test_type} throughput vs noc2axi latency plot saved to {plot_path}")
    plt.close()


def create_trinity_latency_vs_transfer_size_with_axi_lines(results: List[Dict], output_dir: Path, test_type: str = 'sc') -> None:
    """Create latency vs transfer size plot for trinity_performance tests with lines for different AXI latencies."""
    if not PLOTTING_AVAILABLE:
        logging.info("Skipping trinity latency vs transfer size plot - matplotlib not available")
        return

    if not results:
        logging.warning("No data available for trinity latency vs transfer size plotting")
        return

    # Group data by noc2axi latency values
    noc2axi_groups = {}
    for result in results:
        if (result['transfer_size'] is not None and
            result['noc2axi_write_buffer_latency'] is not None and
            result['write_latency'] is not None and
            result['read_latency'] is not None):

            noc2axi_latency = result['noc2axi_write_buffer_latency']
            if noc2axi_latency not in noc2axi_groups:
                noc2axi_groups[noc2axi_latency] = {
                    'transfer_sizes': [],
                    'write_latencies': [],
                    'read_latencies': []
                }

            noc2axi_groups[noc2axi_latency]['transfer_sizes'].append(result['transfer_size'])
            noc2axi_groups[noc2axi_latency]['write_latencies'].append(result['write_latency'])
            noc2axi_groups[noc2axi_latency]['read_latencies'].append(result['read_latency'])

    if not noc2axi_groups:
        logging.warning("No valid data found for trinity latency vs transfer size plotting")
        return

    plt.figure(figsize=(12, 8))
    colors = ['b', 'r', 'g', 'c', 'm', 'y', 'k', 'orange']

    # Write latency subplot
    plt.subplot(2, 1, 1)
    color_idx = 0

    for noc2axi_latency, data in sorted(noc2axi_groups.items()):
        sorted_data = sorted(zip(data['transfer_sizes'], data['write_latencies']))
        transfer_sizes, write_latencies = zip(*sorted_data)

        color = colors[color_idx % len(colors)]
        plt.plot(transfer_sizes, write_latencies, f'{color}o-',
                label=f'Noc2Axi {int(noc2axi_latency)} cycles', markersize=6, linewidth=2)
        color_idx += 1

    plt.xlabel('Transfer Size (bytes)')
    plt.ylabel('Write Latency (ns)')
    plt.title(f'Trinity Performance {test_type.upper()}: Write Latency vs Transfer Size')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.xticks([128, 256, 512, 1024, 2048, 4096],
               ['128', '256', '512', '1024', '2048', '4096'], rotation=45)

    # Read latency subplot
    plt.subplot(2, 1, 2)
    color_idx = 0

    for noc2axi_latency, data in sorted(noc2axi_groups.items()):
        sorted_data = sorted(zip(data['transfer_sizes'], data['read_latencies']))
        transfer_sizes, read_latencies = zip(*sorted_data)

        color = colors[color_idx % len(colors)]
        plt.plot(transfer_sizes, read_latencies, f'{color}o-',
                label=f'Noc2Axi {int(noc2axi_latency)} cycles', markersize=6, linewidth=2)
        color_idx += 1

    plt.xlabel('Transfer Size (bytes)')
    plt.ylabel('Read Latency (ns)')
    plt.title(f'Trinity Performance {test_type.upper()}: Read Latency vs Transfer Size')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.xticks([128, 256, 512, 1024, 2048, 4096],
               ['128', '256', '512', '1024', '2048', '4096'], rotation=45)

    plt.tight_layout()

    plot_path = output_dir / f'trinity_{test_type}_latency_vs_transfer_size.png'
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    logging.info(f"Trinity {test_type} latency vs transfer size plot saved to {plot_path}")
    plt.close()


def create_trinity_comparison_plots_by_noc2axi_latency(results_dict: Dict[str, List[Dict]], output_dir: Path) -> None:
    """Create comparison plots for sc/mc2/mc4 grouped by noc2axi latency values."""
    if not PLOTTING_AVAILABLE:
        logging.info("Skipping trinity comparison plots - matplotlib not available")
        return

    # Check if we have results for multiple test types
    available_types = [test_type for test_type, results in results_dict.items() if results]
    if len(available_types) < 2:
        logging.info("Skipping trinity comparison plots - need at least 2 test types")
        return

    # Collect all unique noc2axi latencies across all test types
    all_latencies = set()
    for test_type in available_types:
        for result in results_dict[test_type]:
            if result.get('noc2axi_write_buffer_latency') is not None:
                all_latencies.add(result['noc2axi_write_buffer_latency'])

    if not all_latencies:
        logging.warning("No noc2axi latency data found for comparison plots")
        return

    # Colors for different test types
    test_type_colors = {'sc': 'b', 'mc2': 'r', 'mc4': 'g'}

    # Create a comparison plot for each unique noc2axi latency
    for noc2axi_latency in sorted(all_latencies):
        # Collect data for this specific latency across all test types
        latency_data = {}

        for test_type in available_types:
            latency_data[test_type] = {
                'transfer_sizes': [],
                'write_throughputs': [],
                'read_throughputs': []
            }

            for result in results_dict[test_type]:
                if (result.get('transfer_size') is not None and
                    result.get('noc2axi_write_buffer_latency') == noc2axi_latency and
                    result.get('write_throughput') is not None and
                    result.get('read_throughput') is not None):

                    latency_data[test_type]['transfer_sizes'].append(result['transfer_size'])
                    latency_data[test_type]['write_throughputs'].append(result['write_throughput'])
                    latency_data[test_type]['read_throughputs'].append(result['read_throughput'])

        # Skip if no data for this latency
        if not any(latency_data[test_type]['transfer_sizes'] for test_type in available_types):
            continue

        plt.figure(figsize=(16, 6))

        # Write throughput subplot (left side)
        plt.subplot(1, 2, 1)

        for test_type in available_types:
            if latency_data[test_type]['transfer_sizes']:
                # Sort data by transfer size
                sorted_data = sorted(zip(
                    latency_data[test_type]['transfer_sizes'],
                    latency_data[test_type]['write_throughputs']
                ))
                transfer_sizes, write_throughputs = zip(*sorted_data)

                color = test_type_colors.get(test_type, 'k')
                plt.plot(transfer_sizes, write_throughputs, f'{color}o-',
                        label=f'{test_type.upper()}', markersize=6, linewidth=2)

        # Add theoretical line for write
        theoretical_sizes = [128, 256, 512, 1024, 2048, 4096]
        theoretical_throughputs = [get_theoretical_throughput(ts) for ts in theoretical_sizes]
        plt.plot(theoretical_sizes, theoretical_throughputs, 'k--',
                label='Theoretical', linewidth=2, alpha=0.7)

        plt.xlabel('Transfer Size (bytes)')
        plt.ylabel('Write Throughput (B/cycle)')
        plt.title(f'Write Throughput vs Transfer Size\n(Noc2Axi Latency = {int(noc2axi_latency)} cycles)')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.ylim(0, 70)
        plt.xlim(0, 4200)
        plt.xticks([128, 256, 512, 1024, 2048, 4096],
                   ['128', '256', '512', '1024', '2048', '4096'], rotation=45)

        # Read throughput subplot (right side)
        plt.subplot(1, 2, 2)

        for test_type in available_types:
            if latency_data[test_type]['transfer_sizes']:
                # Sort data by transfer size
                sorted_data = sorted(zip(
                    latency_data[test_type]['transfer_sizes'],
                    latency_data[test_type]['read_throughputs']
                ))
                transfer_sizes, read_throughputs = zip(*sorted_data)

                color = test_type_colors.get(test_type, 'k')
                plt.plot(transfer_sizes, read_throughputs, f'{color}o-',
                        label=f'{test_type.upper()}', markersize=6, linewidth=2)

        # Add theoretical line for read
        plt.plot(theoretical_sizes, theoretical_throughputs, 'k--',
                label='Theoretical', linewidth=2, alpha=0.7)

        plt.xlabel('Transfer Size (bytes)')
        plt.ylabel('Read Throughput (B/cycle)')
        plt.title(f'Read Throughput vs Transfer Size\n(Noc2Axi Latency = {int(noc2axi_latency)} cycles)')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.ylim(0, 70)
        plt.xlim(0, 4200)
        plt.xticks([128, 256, 512, 1024, 2048, 4096],
                   ['128', '256', '512', '1024', '2048', '4096'], rotation=45)

        plt.tight_layout()

        # Save plot with latency value in filename
        plot_path = output_dir / f'trinity_comparison_noc2axi_{int(noc2axi_latency)}_cycles.png'
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        logging.info(f"Trinity comparison plot for noc2axi {int(noc2axi_latency)} cycles saved to {plot_path}")
        plt.close()


def find_regression_directory(out_dir: Path, summary_log_path: Path) -> Optional[Path]:
    """
    Find the Trinity Performance Regression directory in regression mode.

    When multiple directories exist, finds the one that hasn't been parsed yet.
    Returns the path to the Trinity_Performance_Regression* directory
    or None if not found or all already parsed.
    """
    if not out_dir.exists() or not out_dir.is_dir():
        logging.error(f"Directory {out_dir} does not exist or is not a directory")
        return None

    # Find all directories matching the pattern
    regression_dirs = []
    for item in out_dir.iterdir():
        if (item.is_dir() and
            item.name.startswith('Trinity_Performance_Regression')):
            regression_dirs.append(item)

    if len(regression_dirs) == 0:
        logging.error("No Trinity_Performance_Regression* directory found in regression mode")
        with open(summary_log_path, 'w') as f:
            f.write("No Trinity_Performance_Regression directories found\n")
        return None

    # Log all found directories to summary
    with open(summary_log_path, 'w') as f:
        f.write(f"Found {len(regression_dirs)} Trinity_Performance_Regression directories:\n")
        for d in regression_dirs:
            f.write(f"  - {d.name}\n")

    if len(regression_dirs) == 1:
        logging.info(f"Found regression directory: {regression_dirs[0].name}")
        with open(summary_log_path, 'a') as f:
            f.write(f"Selected: {regression_dirs[0].name} (only option)\n")
        return regression_dirs[0]

    # Multiple directories found - find unparsed one
    unparsed_dirs = []
    parsed_dirs = []

    for regression_dir in regression_dirs:
        log_file = regression_dir / 'parse_ddr_perf_logs.log'
        success_marker = "PARSING_COMPLETED_SUCCESSFULLY"

        is_parsed = False
        if log_file.exists():
            try:
                with open(log_file, 'r') as f:
                    content = f.read()
                    if success_marker in content:
                        is_parsed = True
            except (IOError, OSError):
                pass  # Treat as unparsed if can't read

        if is_parsed:
            parsed_dirs.append(regression_dir)
        else:
            unparsed_dirs.append(regression_dir)

    # Update summary log
    with open(summary_log_path, 'a') as f:
        f.write(f"\nParsed directories ({len(parsed_dirs)}):\n")
        for d in parsed_dirs:
            f.write(f"  - {d.name}\n")
        f.write(f"\nUnparsed directories ({len(unparsed_dirs)}):\n")
        for d in unparsed_dirs:
            f.write(f"  - {d.name}\n")

    if len(unparsed_dirs) == 0:
        logging.error("All Trinity_Performance_Regression directories have already been parsed")
        with open(summary_log_path, 'a') as f:
            f.write("\nResult: All directories already parsed\n")
        return None
    elif len(unparsed_dirs) == 1:
        selected = unparsed_dirs[0]
        logging.info(f"Found {len(regression_dirs)} regression directories, "
                    f"selecting unparsed one: {selected.name}")
        with open(summary_log_path, 'a') as f:
            f.write(f"\nSelected: {selected.name} (unparsed)\n")
        return selected
    else:
        # Multiple unparsed directories - select the newest one
        selected = max(unparsed_dirs, key=lambda d: d.stat().st_mtime)
        logging.info(f"Found {len(unparsed_dirs)} unparsed regression directories, "
                    f"selecting newest: {selected.name}")
        with open(summary_log_path, 'a') as f:
            f.write(f"\nSelected: {selected.name} (newest unparsed)\n")
        return selected


def find_addr_pinger_test_directories(out_dir: Path) -> List[Path]:
    """Find all addr_pinger test directories."""
    test_dirs = []

    if not out_dir.exists() or not out_dir.is_dir():
        logging.error(f"Directory {out_dir} does not exist or is not a directory")
        return test_dirs

    for item in out_dir.iterdir():
        if item.is_dir() and item.name.startswith('addr_pinger_') and 'perf_test' in item.name:
            test_dirs.append(item)

    return sorted(test_dirs)


def find_trinity_performance_test_directories(out_dir: Path, test_type: str = 'sc') -> List[Path]:
    """Find all trinity_performance test directories of the specified type (sc, mc2, or mc4)."""
    test_dirs = []

    if not out_dir.exists() or not out_dir.is_dir():
        logging.error(f"Directory {out_dir} does not exist or is not a directory")
        return test_dirs

    # Construct the prefix based on test type
    prefix = f'trinity_performance_{test_type}_'

    for item in out_dir.iterdir():
        if item.is_dir() and item.name.startswith(prefix):
            test_dirs.append(item)

    return sorted(test_dirs)


def main():
    parser = argparse.ArgumentParser(
        description='Parse performance test results and generate plots')
    parser.add_argument('out_dir', help='Path to output directory')
    parser.add_argument('--no-plots', action='store_true',
                        help='Skip plot generation')
    parser.add_argument('--plots-only', action='store_true',
                        help='Generate plots from existing CSV file only')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable console output (default: log to file only)')
    parser.add_argument('--regression', '-r', action='store_true',
                        help='Use regression mode: look for nested Trinity_Performance_Regression* directory')

    args = parser.parse_args()
    out_dir = Path(args.out_dir)

    # Determine output directory (for logs, CSV, plots)
    output_dir = out_dir
    if args.regression:
        # Create summary log in the out directory for regression mode
        summary_log_path = out_dir / 'regression_parsing_summary.log'
        regression_dir = find_regression_directory(out_dir, summary_log_path)
        if regression_dir is None:
            sys.exit(1)
        output_dir = regression_dir

    # Setup logging
    log_file = output_dir / 'parse_ddr_perf_logs.log'
    setup_logging(log_file, args.verbose)
    csv_filename = output_dir / 'performance_results.csv'

    # Handle plots-only mode
    if args.plots_only:
        # Check for both CSV files
        addr_pinger_csv_filename = output_dir / 'addr_pinger_performance_results.csv'
        trinity_performance_csv_filename = output_dir / 'trinity_performance_results.csv'

        # Read addr_pinger CSV if it exists
        addr_pinger_results = []
        if addr_pinger_csv_filename.exists():
            try:
                with open(addr_pinger_csv_filename, 'r') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        # Convert numeric fields back to numbers
                        for key in ['transfer_size_per_chunk', 'write_first_timestamp',
                                    'write_last_timestamp', 'write_duration',
                                    'write_latency', 'write_throughput', 'noc2axi_write_buffer_latency',
                                    'read_first_timestamp', 'read_last_timestamp',
                                    'read_duration', 'read_latency', 'read_throughput', 'noc2axi_read_buffer_latency']:
                            if row[key] and row[key] != 'None':
                                try:
                                    row[key] = float(row[key])
                                except ValueError:
                                    row[key] = None
                        addr_pinger_results.append(row)
            except (IOError, OSError) as e:
                logging.error(f"Error reading addr_pinger CSV file: {e}")
                sys.exit(1)

        # Read trinity_performance CSV files for all test types
        trinity_performance_results = {'sc': [], 'mc2': [], 'mc4': []}
        for test_type in ['sc', 'mc2', 'mc4']:
            csv_file = output_dir / f'trinity_performance_{test_type}_results.csv'
            if csv_file.exists():
                try:
                    with open(csv_file, 'r') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            # Convert numeric fields back to numbers
                            for key in ['transfer_size', 'number_of_transfers', 'write_first_timestamp',
                                        'write_last_timestamp', 'write_duration',
                                        'write_latency', 'write_throughput', 'noc2axi_write_buffer_latency',
                                        'read_first_timestamp', 'read_last_timestamp',
                                        'read_duration', 'read_latency', 'read_throughput', 'noc2axi_read_buffer_latency']:
                                if row[key] and row[key] != 'None':
                                    try:
                                        row[key] = float(row[key])
                                    except ValueError:
                                        row[key] = None
                            trinity_performance_results[test_type].append(row)
                except (IOError, OSError) as e:
                    logging.error(f"Error reading trinity_performance {test_type} CSV file: {e}")
                    sys.exit(1)

        if not addr_pinger_results and not any(trinity_performance_results.values()):
            logging.error("No CSV files found for plots-only mode")
            sys.exit(1)

        # Generate plots only
        if addr_pinger_results:
            logging.info("Generating addr_pinger plots from existing CSV...")
            create_throughput_vs_transfer_size_with_noc2axi_lines(addr_pinger_results, output_dir)
            create_throughput_vs_noc2axi_with_transfer_size_lines(addr_pinger_results, output_dir)
            create_latency_vs_transfer_size_with_noc2axi_lines(addr_pinger_results, output_dir)

        for test_type in ['sc', 'mc2', 'mc4']:
            if trinity_performance_results[test_type]:
                logging.info(f"Generating trinity_performance {test_type} plots from existing CSV...")
                create_trinity_throughput_vs_transfer_size_with_axi_lines(trinity_performance_results[test_type], output_dir, test_type)
                create_trinity_throughput_vs_axi_with_transfer_size_lines(trinity_performance_results[test_type], output_dir, test_type)
                create_trinity_latency_vs_transfer_size_with_axi_lines(trinity_performance_results[test_type], output_dir, test_type)

        # Generate comparison plots if we have multiple test types
        logging.info("Generating trinity_performance comparison plots from existing CSV...")
        create_trinity_comparison_plots_by_noc2axi_latency(trinity_performance_results, output_dir)
        return

    # Normal parsing mode
    # Find all test directories (use output_dir which is already set correctly for regression mode)
    addr_pinger_dirs = find_addr_pinger_test_directories(output_dir)
    trinity_performance_dirs = {'sc': [], 'mc2': [], 'mc4': []}

    for test_type in ['sc', 'mc2', 'mc4']:
        trinity_performance_dirs[test_type] = find_trinity_performance_test_directories(output_dir, test_type)

    total_trinity_dirs = sum(len(dirs) for dirs in trinity_performance_dirs.values())

    if not addr_pinger_dirs and total_trinity_dirs == 0:
        logging.error(f"No addr_pinger or trinity_performance test directories found in {output_dir}")
        sys.exit(1)

    logging.info(f"Found {len(addr_pinger_dirs)} addr_pinger test directories")
    for test_type in ['sc', 'mc2', 'mc4']:
        if trinity_performance_dirs[test_type]:
            logging.info(f"Found {len(trinity_performance_dirs[test_type])} trinity_performance_{test_type} test directories")

    # Parse addr_pinger tests
    addr_pinger_results = []
    addr_pinger_skipped = 0

    if addr_pinger_dirs:
        logging.info("Processing addr_pinger tests...")
        for test_dir in addr_pinger_dirs:
            # Look for perf_res_*.txt files in the test directory
            perf_files = list(test_dir.glob('perf_res_*.txt'))

            if not perf_files:
                logging.warning(f"No perf_res_*.txt files found in {test_dir}")
                addr_pinger_skipped += 1
                continue

            if len(perf_files) > 1:
                logging.warning(f"Multiple perf_res files found in {test_dir}, "
                               f"using first one: {perf_files[0].name}")

            perf_file = perf_files[0]
            logging.info(f"Parsing addr_pinger {perf_file}")
            result = parse_addr_pinger_perf_file(perf_file)
            if result:
                addr_pinger_results.append(result)
            else:
                addr_pinger_skipped += 1

    # Parse trinity_performance tests for all types
    trinity_performance_results = {'sc': [], 'mc2': [], 'mc4': []}
    trinity_performance_skipped = {'sc': 0, 'mc2': 0, 'mc4': 0}

    for test_type in ['sc', 'mc2', 'mc4']:
        if trinity_performance_dirs[test_type]:
            logging.info(f"Processing trinity_performance_{test_type} tests...")
            for test_dir in trinity_performance_dirs[test_type]:
                # Look for perf_res_*.txt files in the test directory
                perf_files = list(test_dir.glob('perf_res_*.txt'))

                if not perf_files:
                    logging.warning(f"No perf_res_*.txt files found in {test_dir}")
                    trinity_performance_skipped[test_type] += 1
                    continue

                if len(perf_files) > 1:
                    logging.warning(f"Multiple perf_res files found in {test_dir}, "
                                   f"using first one: {perf_files[0].name}")

                perf_file = perf_files[0]
                logging.info(f"Parsing trinity_performance_{test_type} {perf_file}")
                result = parse_trinity_performance_perf_file(perf_file)
                if result:
                    trinity_performance_results[test_type].append(result)
                else:
                    trinity_performance_skipped[test_type] += 1

    # Write addr_pinger results to CSV
    if addr_pinger_results:
        addr_pinger_csv_filename = output_dir / 'addr_pinger_performance_results.csv'
        addr_pinger_fieldnames = [
            'test_dir',
            'transfer_size_per_chunk', 'total_data_transferred',
            'write_first_timestamp', 'write_last_timestamp', 'write_duration',
            'write_latency', 'write_throughput', 'noc2axi_write_buffer_latency',
            'read_first_timestamp', 'read_last_timestamp', 'read_duration',
            'read_latency', 'read_throughput', 'noc2axi_read_buffer_latency'
        ]

        try:
            with open(addr_pinger_csv_filename, 'w', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=addr_pinger_fieldnames)
                writer.writeheader()
                writer.writerows(addr_pinger_results)

            logging.info(f"Successfully wrote {len(addr_pinger_results)} addr_pinger records to "
                        f"{addr_pinger_csv_filename}")
            if addr_pinger_skipped > 0:
                logging.info(f"Skipped {addr_pinger_skipped} addr_pinger files (no valid data found)")

        except (IOError, OSError) as e:
            logging.error(f"Error writing addr_pinger CSV file: {e}")
            sys.exit(1)

    # Write trinity_performance results to CSV for each test type
    trinity_performance_fieldnames = [
        'test_dir',
        'transfer_size', 'number_of_transfers', 'total_data_transferred',
        'write_first_timestamp', 'write_last_timestamp', 'write_duration',
        'write_latency', 'write_throughput', 'noc2axi_write_buffer_latency',
        'read_first_timestamp', 'read_last_timestamp', 'read_duration',
        'read_latency', 'read_throughput', 'noc2axi_read_buffer_latency'
    ]

    for test_type in ['sc', 'mc2', 'mc4']:
        if trinity_performance_results[test_type]:
            trinity_performance_csv_filename = output_dir / f'trinity_performance_{test_type}_results.csv'

            try:
                with open(trinity_performance_csv_filename, 'w', newline='') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=trinity_performance_fieldnames)
                    writer.writeheader()
                    writer.writerows(trinity_performance_results[test_type])

                logging.info(f"Successfully wrote {len(trinity_performance_results[test_type])} trinity_performance_{test_type} records to "
                            f"{trinity_performance_csv_filename}")
                if trinity_performance_skipped[test_type] > 0:
                    logging.info(f"Skipped {trinity_performance_skipped[test_type]} trinity_performance_{test_type} files (no valid data found)")

            except (IOError, OSError) as e:
                logging.error(f"Error writing trinity_performance_{test_type} CSV file: {e}")
                sys.exit(1)

    # Check if we have any results at all
    has_trinity_results = any(trinity_performance_results[test_type] for test_type in ['sc', 'mc2', 'mc4'])
    if not addr_pinger_results and not has_trinity_results:
        logging.error("No valid data found to write to CSV")
        sys.exit(1)

    # Generate plots unless disabled
    if not args.no_plots:
        logging.info("Generating plots...")

        # Generate addr_pinger plots
        if addr_pinger_results:
            logging.info("Generating addr_pinger plots...")
            create_throughput_vs_transfer_size_with_noc2axi_lines(addr_pinger_results, output_dir)
            create_throughput_vs_noc2axi_with_transfer_size_lines(addr_pinger_results, output_dir)
            create_latency_vs_transfer_size_with_noc2axi_lines(addr_pinger_results, output_dir)

        # Generate trinity_performance plots for each test type
        for test_type in ['sc', 'mc2', 'mc4']:
            if trinity_performance_results[test_type]:
                logging.info(f"Generating trinity_performance_{test_type} plots...")
                create_trinity_throughput_vs_transfer_size_with_axi_lines(trinity_performance_results[test_type], output_dir, test_type)
                create_trinity_throughput_vs_axi_with_transfer_size_lines(trinity_performance_results[test_type], output_dir, test_type)
                create_trinity_latency_vs_transfer_size_with_axi_lines(trinity_performance_results[test_type], output_dir, test_type)

        # Generate comparison plots if we have multiple test types
        logging.info("Generating trinity_performance comparison plots...")
        create_trinity_comparison_plots_by_noc2axi_latency(trinity_performance_results, output_dir)

    # Final success message
    logging.info("PARSING_COMPLETED_SUCCESSFULLY")

    # Update summary log for regression mode
    if args.regression:
        with open(summary_log_path, 'a') as f:
            f.write(f"\nParsing completed successfully for: {output_dir.name}\n")
            f.write(f"Results saved to: {output_dir}\n")


if __name__ == '__main__':
    main()