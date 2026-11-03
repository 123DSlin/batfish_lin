#!/usr/bin/env python3
"""Reproducible lookup microbenchmark; not a BGP convergence/solver benchmark."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def worker(loader, routers, prefixes, branches):
    spec = importlib.util.spec_from_file_location('benchmark_symbolic_rib', loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    entries = []
    guard = {'ast': {'operator': 'TRUE'}}
    for router in range(routers):
        for prefix in range(prefixes):
            for branch in range(branches):
                entries.append(module.RouteEntry(f'r{router:03}_p{prefix:03}_b{branch}',
                    'MAIN', f'r{router}', 'default', f'10.{router}.{prefix}.0/24',
                    'BGP', 'benchmark', {}, guard, guard, ()))
        for identifier, network in [('default', '0.0.0.0/0'), ('fallback', '10.0.0.0/8')]:
            entries.append(module.RouteEntry(f'r{router:03}_{identifier}', 'MAIN', f'r{router}',
                'default', network, 'BGP', 'benchmark', {}, guard, guard, ()))
    started = time.perf_counter()
    rib = module.SymbolicRib([], entries[::-1])
    build_seconds = time.perf_counter() - started
    queries = [(f'r{i % routers}', f'10.{i % routers}.{(i // routers) % prefixes}.1')
               for i in range(min(1024, routers * prefixes))]
    times = []; hashes = []
    for _ in range(3):
        digest = hashlib.sha256(); started = time.perf_counter()
        for router, destination in queries:
            result = rib.forwarding_entries(router=router, vrf='default', destination=destination)
            digest.update('|'.join(e.candidate_id for e in result).encode())
        times.append(time.perf_counter() - started); hashes.append(digest.hexdigest())
    if len(set(hashes)) != 1:
        raise RuntimeError('Query results changed across repeated lookups')
    return {'entries': len(entries), 'routers': routers, 'prefixes_per_router': prefixes,
            'branches_per_prefix': branches, 'queries_per_pass': len(queries),
            'build_seconds': build_seconds, 'query_pass_seconds': times,
            'median_query_seconds': statistics.median(times), 'result_sha256': hashes[0],
            'cache_info': rib.query_cache_info() if hasattr(rib, 'query_cache_info') else None,
            'loader_sha256': hashlib.sha256(loader.read_bytes()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-root', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker-loader', type=Path)
    parser.add_argument('--routers', type=int, default=32)
    parser.add_argument('--prefixes', type=int, default=128)
    parser.add_argument('--branches', type=int, default=3)
    args = parser.parse_args()
    if not (1 <= args.routers <= 256 and 1 <= args.prefixes <= 256 and args.branches > 0):
        parser.error('IPv4 fixture requires 1..256 routers/prefixes and positive branch count')
    if args.worker_loader:
        print(json.dumps(worker(args.worker_loader, args.routers, args.prefixes, args.branches)))
    else:
        if args.baseline_root is None or args.output is None:
            parser.error('--baseline-root and --output are required')
        results = {}
        for side, root in [('before', args.baseline_root.resolve()), ('after', ROOT)]:
            command = [sys.executable, str(Path(__file__).resolve()), '--worker-loader',
                       str(root / 'consistency' / 'branch_loader.py'), '--routers', str(args.routers),
                       '--prefixes', str(args.prefixes), '--branches', str(args.branches)]
            p = subprocess.run(command, text=True, capture_output=True, check=True, timeout=180)
            results[side] = json.loads(p.stdout)
        results['results_identical'] = results['before']['result_sha256'] == results['after']['result_sha256']
        results['median_lookup_speedup'] = (results['before']['median_query_seconds'] /
                                            results['after']['median_query_seconds'])
        results['scope'] = 'synthetic query-only benchmark; excludes SMT generation, convergence and solving'
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2) + '\n')
        print(json.dumps(results, indent=2))
        raise SystemExit(0 if results['results_identical'] else 1)
