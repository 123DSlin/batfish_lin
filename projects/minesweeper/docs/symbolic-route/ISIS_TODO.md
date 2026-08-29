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

The parsed pipeline accepts an `IsisTopology`, converges dedicated `ISIS_L1` and `ISIS_L2` guarded
RIBs, installs selected candidates into `MAIN`, and emits separate protocol-detail report sections.

## Stage 6.2 L2 and level transition / L2 与层级转换

Stage 6.2 adds native Level-2 interface routes and sessions. At a non-overloaded L1/L2 router,
selected L1 branches are converted with Batfish
`IsisProtocolHelper.convertRouteLevel1ToLevel2`; their `selectionGuard` becomes the availability
guard of a stable L2 contribution. Attach and down-bit routes are rejected by that Batfish helper.

Stage 6.2 新增原生 L2 interface route、L2 session 和独立 `ISIS_L2` Guarded RIB。对于非
overload 的 L1/L2 路由器，pipeline 使用 Batfish `convertRouteLevel1ToLevel2()` 将已选择的
L1 branch 转换成 L2 contribution，并将原 L1 `selectionGuard` 作为其 L2 availability guard。
attach/down 路由由 Batfish helper 拒绝升级。

An L1/L2 router originates Batfish-compatible attached default into L1. The route is advertised to
L1-only neighbors and may enter their MAIN RIB, but is not upgraded to L2 and is rejected from the
originating L1/L2 router's MAIN RIB, matching Batfish `IsisRib` behavior.

Stage 6.3 replaces the one-shot conversion with `BatfishIsisLevelTransitionReconciler`. The L1
engine invokes it synchronously only after draining its global FIFO. It scans selected L1 branches,
maintains stable source-candidate-to-L2-contribution identities, and drives L2 advertisement,
guard update, replacement, or recursive withdrawal to another stable state. A caller may therefore
mutate L1 through its convergence engine without rerunning the whole pipeline.

Stage 6.3 将一次性转换替换为持续的跨层 reconciler。L1 全局队列清空后同步触发 reconcile，
对 source candidate 与 L2 contribution 建立稳定映射；L1 withdrawal、guard update 和 route
replacement 都会转换成相应的 L2 delta，并在返回前完成 L2 后代递归撤回和重新收敛。

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

`BatfishIsisLevel2PipelineTest` additionally checks:

- parser-normalized L1-only, L1/L2, and L2-only domains;
- native L2 sessions and receiver-side metric accumulation;
- an L1 prefix upgraded and propagated through L2 with one combined guard;
- attached-default acceptance at an L1-only neighbor and rejection at L2/the L1L2 origin MAIN;
- three L2 metric tiers and equal-cost candidates;
- explicit fail-closed rejection of unsupported overload semantics.
- incremental L1 withdrawal, equivalent candidate guard update, and atomic route replacement;
- automatic removal/recreation of all derived L2 descendants without rerunning the pipeline.

## Remaining stages / 后续阶段

Stage 6.1 is not complete IS-IS support. The following remain unsupported and must not be silently
accepted:

- overload behavior;
- dynamic redistribution from changed MAIN state into downstream protocol planes;
- external L1/L2 routes and export/redistribution policy;
- broadcast LAN pseudonodes and parallel-link failure identities;
- concrete Batfish differential tests over enumerated failure assignments;
- `k`-failure pruning;
- iBGP session guards derived from IS-IS reachability;
- SR-MPLS/SRv6 advertisements, SID database, policy selection, or traffic execution.

Attached-default, L1-to-L2 lifecycle, and L1/L2-to-MAIN reconciliation are implemented; overload
remains fail-closed.
The remaining items belong to later stages. SR work must begin only after the IS-IS reachability
guards on which its Node-SID and adjacency-SID semantics depend are complete.
