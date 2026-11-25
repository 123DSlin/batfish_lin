# Preserved pre-optimization Plus

This is a reconstructed pre-optimization Plus baseline for
`DEMOIDEA/semantic_domains_20261125/versioned_results`. It is not a claim of
a byte-identical historical source archive: that run saved input hashes and
queries, but no complete source snapshot. See `PRESERVATION.json` and the
reproduction audit for provenance and equivalence results.

It keeps complete semantic configuration domains, native full-network device
equations, candidate recovery certification, counterexample Bad regions,
per-fault reference/Support checks, and verified line-to-field specialization.
It uses a new solver process per query. It has no device summaries, symbolic
Support, persistent session, relation scope or run-context cache.

Run from the workspace root, with a fresh output:

```bash
python3 -B batfish/tools/plus_aotonetsubspec_versioned_20261125/run_preserved.py \
  DEMOIDEA/semantic_domains_20261125/versioned_inputs/demo1_q1/input \
  --property-preserving --all-configs --k 2 --consistency-workers 2 \
  --timeout 90 --output /tmp/plus-legacy-q1
```

The optimized implementation remains in `../plus_aotonetsubspec`.
The backend remains `regions`; the finite configuration-enumeration backend
is not a replacement for this baseline. Existing versioned_results are read
only reference artifacts and are never overwritten by reproduction runs.

Both Demo1 semantic_subspecs.txt files were reproduced byte-for-byte. Each
case also passed 232 Domain/Bad/Support/Allowed equivalence checks.
Use `python3 -B verify_baseline.py` to check the frozen code. The recommended
`run_preserved.py` checks source hashes before executing the original CLI.
