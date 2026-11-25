# BGP router scale benchmark

Run from the Batfish repository root with Bazel, Z3 and the NetSubspec Python dependencies available.

```bash
python3 tools/router_scale/router_scale.py --routers 4 8 16 --fat-tree-k 4 --workers 4 \
  --policies uniform neighbor-preference
```

The default sweep uses 4, 8, 16, 32, 64, 128, 256, 512 and 1000 routers
for Ring (degree 2) and Sparse (degree 3). Sparse adds a deterministic
perfect matching to the ring. FatTree uses canonical even radices 4, 8,
16 and 28, with 20, 80, 320 and 980 routers. Hosts are omitted.
Use `--topologies` to select a subset and `--fat-tree-k` to select other even radices.
Use `--generate-only` to create the configuration matrix without invoking Batfish.

All cases use eBGP, a single advertised
`5.5.5.5/32` at `r0`, and at most one link failure. The ingress is the
opposite router in Ring and Sparse and an edge router in the last pod
in FatTree. The default `uniform` policy assigns local preference 200 to
all imports. `neighbor-preference` gives imports from the lowest-numbered
neighbor local preference 250 and keeps the other imports at 200.

- `cases/<case>/configs/` contains generated device configurations.
- `reports/` contains timestamped TXT and JSON reports with one row per case.
- `runs/<timestamp>/<case>/` contains logs, SMT, seeds and subspec outputs.

Generation timings separate configuration loading, concrete dataplane
calculation, symbolic input construction, symbolic convergence and exports.
Pipeline timings separate SMT slicing, seed construction and consistency,
branch solving and final aggregation. Stages 3 and 4 together measure
subspec derivation. Z3 timings count subprocess elapsed time, including
tactics and I/O. Simplification timings include their nested Z3 calls.
For concurrent calls, active wall time measures the union of the intervals
and task sums count each call. The report counts route candidates and guard
ASTs, eligible and checked branches, SMT constant declarations and assertions
per file, SMT bytes, and branch/final constraint-atom occurrences.

By default, after a successful symbolic run with at most 32 routers, the
benchmark generates an independent Traverse input from the same configurations,
computes a concrete dataplane for every legal failure scenario, and solves
and intersects those subspecs. It then checks final line and field subspecs
for SMT equivalence, with input provenance checks and per-target outcomes
in `failure_intersection_check/report.json`. Symbolic, Traverse, and
equivalence wall times are separate. Set `--traverse-max-routers 0` to
disable Traverse or change the cutoff. `--traverse-timeout` applies
separately to Traverse and equivalence (default 240 seconds each).

The default symbolic case wall limit is 600 seconds and the symbolic and
equivalence query limit is 30 seconds. A timed-out or failed case retains its logs and partial results,
and the sweep continues. Peak RSS is sampled over the process tree and can
double-count shared pages. Generated configurations and run outputs are ignored by Git.
