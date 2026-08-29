# IS-IS Symbolic Route Status / IS-IS 符号路由状态

## Implemented scope / 已实现范围

Stage 6.1 implements HoYAN Algorithm 2 for parser-derived IPv4 IS-IS Level-1 point-to-point
circuits. It reuses Batfish `IsisTopology`, `IsisEdge`, `IsisRoute`, interface-level costs,
administrative costs, and `IsisRib.routePreferenceComparator`; the protocol-neutral symbolic
engine still owns guards, the global FIFO queue, propagation dependencies, and recursive
withdrawal.

Stage 6.1 已实现基于 Batfish 解析结果的 IPv4 IS-IS Level-1 点到点线路，并按照 HoYAN
Algorithm 2 执行带权符号传播。Batfish 负责合法邻接、结构化 `IsisRoute`、接收侧接口 cost、
管理距离和 RIB 优选；现有协议无关引擎负责 topology condition、全局 FIFO、传播依赖和递归
撤回。

The implemented contract is deliberately fail-closed:

- only circuits whose Batfish circuit type includes Level-1 are admitted;
- both directed endpoints must be active at Level-1;
- numbered point-to-point interfaces and one canonical `LinkFailureKey` are required;
- an active interface route and its IS-IS session use the same link-aliveness guard;
- passive interface routes use `true`, as they do not depend on a physical adjacency;
- repeated-router paths are denied on import;
- equal-metric candidates remain separate ECMP candidates, while strictly larger metrics are
  suppressed by the availability of all better candidates.

当前边界采用显式拒绝策略：只接受包含 L1 的线路、两端 L1 active、编号点到点接口及唯一
canonical `LinkFailureKey`。active 接口起源路由和 IS-IS session 共享相同链路 guard；passive
接口使用 `true`。路径重复进入同一路由器时拒绝导入。等 metric 候选互不抑制，较高 metric
候选受所有更优候选 availability 的否定约束。

The parsed pipeline now accepts an `IsisTopology`, converges a dedicated `ISIS_L1` guarded RIB,
installs selected candidates into `MAIN`, and emits an `IS-IS LEVEL-1 RIB` report section.

## Verified behavior / 已验证行为

`BatfishIsisAlgorithm2Test` uses a five-router parser-normalized topology and checks:

- topology-derived directed sessions and canonical failure identity;
- Batfish receiver-interface metric accumulation;
- three strict metric tiers (20, 30, and 40);
- two equal-cost metric-30 candidates;
- failure-dependent fallback selection guards;
- active-interface origin guards;
- recursive withdrawal of an origin and all descendants;
- installation into MAIN and protocol-plane reporting.

## Remaining stages / 后续阶段

Stage 6.1 is not complete IS-IS support. The following remain unsupported and must not be silently
accepted:

- Level-2 and separate L1/L2 guarded RIBs;
- L1-to-L2 leaking and down-bit handling;
- overload and attached default behavior;
- external L1/L2 routes and export/redistribution policy;
- broadcast LAN pseudonodes and parallel-link failure identities;
- concrete Batfish differential tests over enumerated failure assignments;
- `k`-failure pruning;
- iBGP session guards derived from IS-IS reachability;
- SR-MPLS/SRv6 advertisements, SID database, policy selection, or traffic execution.

These items belong to Stage 6.2 and later. SR work must begin only after the IS-IS reachability
guards on which its Node-SID and adjacency-SID semantics depend are complete.
