# Symbolic Route Review Guide

Use this checklist when reviewing every symbolic-route change.

## Core architecture

- Does core code remain independent of BGP- and OSPF-specific attributes?
- Is the guard representation hidden behind `RouteGuard`?
- Are Minesweeper SMT route records kept separate from guarded concrete routes?
- Are collections defensively copied and exposed as immutable views?
- Are route and message identities stable enough for propagation dependencies and withdrawal?

## Hoyan semantics

- Is a route's RIB presence guard distinct from its dynamically computed export guard?
- Does export of a lower-priority route require the absence of all strictly better routes?
- Does propagation add link/node aliveness at the correct pipeline boundary?
- Can a late higher-priority route reduce a previously propagated guard?
- Are removals and guard changes propagated transitively rather than handled as additions only?
- Are equal-preference alternatives preserved when later traffic execution needs distinct next hops?

## Protocol reuse

- Does the adapter call Batfish's concrete policy/session/route-preference implementation where
  accessible?
- If behavior is reimplemented, is there a differential test against Batfish?
- Are BGP assumptions kept out of OSPF/common code?
- Are redistribution and main-RIB selection modeled as explicit layers?

## Testing

- Does the stage include focused unit tests?
- Are arrival-order permutations tested when convergence is affected?
- Is the symbolic result evaluated under concrete failure assignments and compared with Batfish?
- Are existing baseline failures distinguished from new regressions?
- Do formatting, `git diff --check`, and relevant static checks pass?

## Audit record

- Is the corresponding implementation-log entry complete?
- Does it list all affected files and non-obvious design decisions?
- Are limitations explicit rather than hidden in TODOs only?
- Are implementation/audit commit hashes, remote status, and rollback commands supplied?
