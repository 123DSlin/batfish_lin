# Symbolic Route Integration

This directory records the design and implementation history of the YU/Hoyan-style symbolic route
simulator being integrated into Minesweeper.

The records serve two purposes:

1. explain the intended semantics and architecture before protocol implementations are added; and
2. provide an audit trail linking each implementation stage to files, tests, limitations, and Git
   commits.

## Intended semantics

The simulator follows Hoyan's guarded route propagation model, which YU consumes as guarded RIBs.
A route has concrete protocol attributes and a symbolic topology condition describing when it is
present. Route preference is computed from the concrete attributes and is independent of the guard.

For a RIB route `r_i`, with strictly higher-priority routes `r_1 ... r_(i-1)`, its export condition
is:

```text
E(r_i) = R(r_i) AND NOT R(r_1) AND ... AND NOT R(r_(i-1))
```

Propagation over link `l` adds the link-aliveness condition:

```text
I(message, receiver) = E(message, sender) AND alive(l)
```

The implementation must support guard reductions and withdrawals when a higher-priority route
arrives after a lower-priority route has already propagated.

## Architecture boundaries

The core is protocol-neutral:

```text
symbolic route model
        +
guard algebra
        +
guarded RIB and propagation engine
        |
        +-- BGP adapter
        +-- OSPF adapter
        +-- connected/static adapters
        +-- redistribution
```

Core model classes must not directly depend on:

- BGP- or OSPF-specific route classes;
- Z3 `BoolExpr`;
- Minesweeper's SMT `SymbolicRouteBase` hierarchy.

Protocol adapters will reuse Batfish concrete route, policy, session, and preference semantics.
Minesweeper's SMT route records remain a separate representation used later for tolerance seed
encodings and consistency checks.

## Audit files

- [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md): append-only stage-by-stage implementation log.
- [REVIEW_GUIDE.md](REVIEW_GUIDE.md): invariants and questions to use during code review.

## Git workflow

The working branch is `feature/yu-symbolic-route`, based on `tolerance-development` at
`1708bbda7c`.

Business-code changes are prepared and validated for review before they are committed. Audit
documents are maintained by the assistant in a separate commit and pushed to GitHub automatically.
Each stage records the implementation and audit commit hashes, verification results, known
limitations, and rollback commands.
