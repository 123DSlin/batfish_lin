# Symbolic Route Implementation Log

This is an append-only audit log. Existing stage entries should be corrected with a dated
amendment instead of being silently rewritten after their code is committed.

## Stage 1: Protocol-neutral symbolic route model

### Git record

- Branch: `feature/yu-symbolic-route`
- Base: `1708bbda7c`
- Implementation commit: `bc9f1bb8d4`
- Commit message: `feat(minesweeper): add protocol-neutral symbolic route model`
- Remote status when first recorded: not pushed; superseded by the push record below

### Objective

Establish immutable, protocol-neutral data structures required by guarded route propagation before
introducing Z3, failure variables, BGP, OSPF, or a convergence engine.

### Files added

| File | Responsibility |
| --- | --- |
| `symbolicroute/RouteGuard.java` | Representation-independent Boolean guard contract. |
| `symbolicroute/SymbolicRoute.java` | Concrete Batfish route paired with a RIB presence guard and provenance. |
| `symbolicroute/SymbolicRouteKey.java` | Candidate identity used by a future guarded RIB. |
| `symbolicroute/SymbolicRouteProvenance.java` | Origin, previous/current router, traversed path, and parent message identity. |
| `symbolicroute/SymbolicRouteMessage.java` | Guarded ingress/egress message representation. |
| `symbolicroute/SymbolicRibUpdateType.java` | Initial RIB update categories. |
| `symbolicroute/SymbolicRibUpdate.java` | Validated add/remove/presence-guard-change update. |
| `symbolicroute/SymbolicRibDelta.java` | Immutable collection of RIB updates. |
| `symbolicroute/SymbolicRouteModelTest.java` | Contract tests for identity, immutability, provenance, message stages, and deltas. |

All paths above are relative to:

```text
projects/minesweeper/src/main/java/org/batfish/minesweeper/
```

except the test, which is under the corresponding `src/test/java` tree.

### Design decisions

1. `SymbolicRoute` does not extend SMT `SymbolicRouteBase`. The former represents a concrete route
   with a symbolic topology condition; the latter represents symbolic SMT route attributes.
2. Only the RIB presence guard is stored on `SymbolicRoute`. Selection/export guards depend on all
   current RIB candidates and will be computed dynamically by the future route selector.
3. `RouteGuard` hides the underlying Boolean representation so Z3 can later be replaced or
   complemented by BDD/MTBDD implementations.
4. `SymbolicRibUpdate` already supports guard changes and removals. These are required for Hoyan's
   late-higher-priority-route withdrawal algorithm, where propagation is not monotonic.
5. Route attributes remain Batfish route objects. Protocol-specific adapters will produce route
   keys and perform comparisons without placing BGP/OSPF fields in the core model.

### Verification performed

- Java formatting: passed using Google Java Format 1.9.
- `git diff --check`: passed.
- Targeted test:

  ```bash
  bazel test //projects/minesweeper:minesweeper_tests \
    --test_filter=org.batfish.minesweeper.symbolicroute.SymbolicRouteModelTest
  ```

  Result: passed.

- Architecture scan found no direct `BoolExpr`, Z3, BGP, or OSPF dependency in the new main-source
  package.

### Baseline issues observed

These failures were outside the files changed in this stage:

1. The full Minesweeper test suite had one existing failure:
   `SearchRoutePoliciesAnswererTest.testMatchGeneralRegexCommunity`.
2. Minesweeper PMD reported existing violations in old files such as `Encoder`, `Graph`,
   `TransferSSA`, and the existing SMT symbolic route classes. It reported no violation in the new
   `symbolicroute` package.

### Known limitations

- There is no concrete `RouteGuard` implementation yet.
- `SymbolicRouteKey` temporarily uses a protocol-adapter-provided stable attribute fingerprint;
  protocol-specific structured key types may replace this before real RIB integration.
- There is no guarded RIB, ranking, propagation, withdrawal, serialization, or tolerance binding.
- `SymbolicRouteMessage` currently models ingress and egress stages only.

### Rollback

If the implementation commit has been published, use:

```bash
git revert bc9f1bb8d4
```

If it has not been published, do not rewrite history without first confirming that no later work
depends on it.

### Git workflow amendment (2026-08-21)

At the repository owner's request, audit-document updates are committed separately and pushed by
the assistant. Business-code changes continue to be presented for review before commit. The push
record for this stage is completed after the audit commit is created and published.

---

Future stages should append a section containing at least: objective, affected files, invariants,
tests, baseline failures, limitations, implementation and audit commit hashes, and rollback
guidance.
