# Batfish 集成、HoYAN Algorithm 2 与 SR/Traffic 的关系

## 1. 本文要回答什么

本文只梳理本仓库新增的 Batfish 集成代码，并回答三个问题：

1. HoYAN Algorithm 2 在本实现中落在哪些模块；
2. Batfish 的协议语义、跨 RIB 协调和顶层 pipeline 如何组成一个完整控制面；
3. SR 与 traffic-flow 为什么依赖这个控制面，但不属于 HoYAN Algorithm 2 本身。

仓库中有两组容易混淆的“Algorithm 1/2”：

| 名称 | Algorithm 1 | Algorithm 2 | 本文关系 |
| --- | --- | --- | --- |
| HoYAN / SIGCOMM 2020 | 带 topology condition 的通用路由传播 | 把 IS-IS 映射为带 metric 的传播并复用算法 1 | 本文主线 |
| 后续 YU traffic-flow 工作 | `simulate(f)`，按跳计算 `M[l,S]` | `forward`，完成 IP/SR 转发 | 控制面的下游消费者 |

因此，“Batfish 集成与 HoYAN Algorithm 2 的关系”首先是**控制面关系**；SR/traffic 是在该控制面稳定之后继续计算的数据面。

## 2. HoYAN Algorithm 1 与 Algorithm 2 的最小语义

### 2.1 Algorithm 1：协议无关传播骨架

对一个前缀，Algorithm 1 维护消息队列和每台设备的候选 RIB：

- ingress policy 决定消息是否进入候选集；
- route selection 按优先级选择路由；
- topology condition 与出链路存活条件合取后继续传播；
- 更高优先级路由晚到时，更新低优先级路由的有效条件；
- propagation tree 支持递归 withdrawal。

仓库中的协议无关对应物是：

- `SymbolicRouteConvergenceEngine`：全局消息队列、传播、撤回和稳定点；
- `SymbolicRouteIngressProcessor`：import、candidate identity 和 RIB 安装；
- `GuardedRib`：候选贡献、availability guard、selection guard 和 delta；
- `SymbolicRouteExporter`：export、链路 guard 合取和后代依赖；
- `SymbolicRoutePropagationDependencies`：替代论文中的 propagation tree；
- `SymbolicRouteProtocolAdapter<R>`：把具体协议语义注入上述通用骨架。

### 2.2 Algorithm 2：IS-IS 不是第二套传播引擎

HoYAN Algorithm 2 的核心不是新建另一种收敛框架，而是在 Algorithm 1 上替换两项协议语义：

1. 每跳累加 IS-IS cost；
2. route selection 优先选择更小的累计 metric。

论文采用“把 IS-IS 映射为带 `ISIS-weight` 的 BGP 节点”的表述。本仓库没有真的把 IS-IS route
伪装成 BGP route，而是保留 Batfish 的 `IsisRoute` 类型，并让它复用同一个 symbolic engine。
这是实现形式上的变化，不是算法语义上的变化。

对应代码集中在：

- `BatfishIsisTopologyAdapter`：从 Batfish `IsisTopology` 构造 L1/L2 session 和 seed；
- `BatfishIsisProtocolAdapter`：在 import 时累加接收接口 cost、设置 next hop/admin，并调用
  `IsisRib.routePreferenceComparator`；
- `BatfishIsisLevelTransitionReconciler`：实现 L1 到 L2 的 guarded route transition；
- `SymbolicRouteConvergenceEngine`：仍负责 Algorithm 1 的队列、guard 传播和 withdrawal。

最准确的概括是：

```text
HoYAN Algorithm 2
  = Algorithm 1 的通用 symbolic propagation
  + Batfish IS-IS topology/configuration adapter
  + Batfish IS-IS metric 与 preference 语义
  + 本实现补充的 L1/L2 生命周期
```

## 3. 新增 Batfish 代码的四层划分

### 3.1 Protocol Adapters：把 Batfish 语义接入通用传播核

这一层回答“收到或发出一条协议路由时，具体应该发生什么”。

| 模块 | 作用 | 与 HoYAN 的关系 |
| --- | --- | --- |
| `BatfishIsisTopologyAdapter` | 从规范化配置和 IS-IS topology 建立 directed sessions、L1/L2 seeds、canonical link guard | Algorithm 2 的网络映射和初始化 |
| `BatfishIsisProtocolAdapter` | cost 累加、next hop/admin 设置、level 检查、loop 拒绝、IS-IS preference | Algorithm 2 第 13/15/26 行语义 |
| `BatfishBgpProtocolAdapter` | 复用 Batfish BGP import/export policy、属性转换和 preference | Algorithm 1 的 BGP 具体化 |
| `BatfishRoutingPolicyProcessor` | 执行 Batfish routing policy，区分 accepted/denied/missing | ingress/egress policy 的具体化 |
| `BatfishMainRibRouteAdapter` | 使用 Batfish MAIN RIB preference 和 LPM 语义 | 跨协议最终选择 |
| `BatfishInterfaceRouteInitializer` | 从接口生成 typed connected/local seed，并附加接口存活 guard | 控制面的本地起源 |

这里 Batfish 的价值不是提供队列算法，而是提供经过 parser/vendor conversion 后的结构化配置、
拓扑、typed route、policy 和 comparator。symbolicroute 层负责把这些 concrete semantics 提升为
guarded semantics。

### 3.2 Redistribution and Cross-RIB Reconciliation：让多个独立 RIB 达到联合稳定点

HoYAN 论文只简要说明 BGP RIB 与 IS-IS RIB 独立计算后再模拟 redistribution。真实 Batfish 集成
必须进一步处理 MAIN、静态路由、L1/L2 和 BGP 之间的反馈环。

| Reconciler | 数据方向 | 主要职责 |
| --- | --- | --- |
| `BatfishIsisLevelTransitionReconciler` | `ISIS_L1 -> ISIS_L2` | L1/L2 leaking/upgrade 的 advertise、guard update、replace、withdraw |
| `BatfishMainRibReconciler` | `ISIS_L1/L2, BGP -> MAIN` | 汇总协议 RIB 的 selected branches，再由 MAIN comparator 跨协议优选 |
| `BatfishStaticRouteReconciler` | `MAIN -> recursive static -> MAIN` | 用 Batfish LPM/activation 语义求 recursive static 最小不动点 |
| `BatfishBgpRedistributionReconciler` | `MAIN connected/static -> BGP` | 执行 redistribution rule 与 policy，持续同步到 BGP RIB |
| `BatfishRedistributionReconciler<R>` | 通用 source/target RIB | 用稳定 identity 做 semantic diff 和生命周期更新 |

这些类不能简单归入“协议适配器”。adapter 是单条消息的协议语义；reconciler 是两个稳定状态
之间的持续协调器。它们监听 engine 的 stable-state 边界，比较 desired 与 active state，只产生
必要的 advertisement/withdrawal/replacement，并用 reentrancy barrier 防止同步回调环。

控制面反馈关系如下：

```text
interface connected/local -----> MAIN <----- ISIS L1/L2
configured static ------------->  |  <----- BGP
recursive static <-------------+  |
                                  |
                                  +---- redistribution ----> BGP

ISIS L1 ---- level transition ----> ISIS L2
```

因此这里计算的不是某一个 RIB 的一次性结果，而是多个协议 RIB 与 MAIN RIB 的**联合不动点**。

### 3.3 Pipeline Assembly：固定装配顺序并闭合反馈环

`BatfishParsedSnapshotPipelineInputBuilder` 负责把 Batfish 已解析快照转换为强类型输入：

1. 从 L3 topology 建立 canonical `LinkFailureKey` 和 link guard；
2. 从接口生成 connected/local MAIN seeds；
3. 区分直接静态路由与 recursive static；
4. 从 `IsisTopology` 构造 L1/L2 edge、session 和 seed；
5. 从 `BgpTopology` 构造 eBGP edge 与 session；
6. 带入 concrete MAIN RIB context 和 redistribution rules。

`BatfishSymbolicRoutePipeline.run` 的实际装配顺序是：

```text
1. MAIN seeds 收敛
2. 启动 recursive-static reconciler
3. 创建 ISIS_L1 与 ISIS_L2 network
4. 先收敛 native L2
5. 注册 L1 -> L2 transition listener
6. 注册 ISIS_L1/L2 -> MAIN listeners
7. 收敛 L1，连带推动 L2 与 MAIN
8. 创建 BGP network，并注册 BGP -> MAIN listener
9. 启动 MAIN -> BGP redistribution，闭合反馈环
10. 基于稳定 IS-IS underlay 构建 guarded SID database
11. 基于 SID database 解析 guarded SR policy
12. 聚合为 PipelineResult，并导出 RIB/SR/guard/failure identity
```

这个顺序解释了为什么 SR 初始化位于最后：它读取已经稳定的 underlay，不参加 MAIN 的路由优选。

### 3.4 SR 与 Batfish 集成：控制面的下游扩展

SR 支持分为三段：

1. **Batfish parser/datamodel**：把 vendor syntax 转换为 `SegmentRoutingConfig`、SRGB/SRLB、
   prefix/adjacency/binding SID 和 SR policy/candidate path；
2. **symbolicsr**：`GuardedSidReconciler` 从 IS-IS guarded reachability 构造 SID database，
   `GuardedSrPolicyReconciler` 再解析 segment list、label stack 和 candidate path guard；
3. **symbolictraffic**：traffic pipeline 消费 MAIN forwarding branches 和 SR policy branches，执行
   IP/SR 转发并生成链路负载/SMT encoding。

关键依赖链是：

```text
Batfish config/topology
        |
        v
HoYAN-style guarded control plane
  ISIS_L1/L2 + BGP + MAIN
        |
        +----> guarded SID database ----> guarded SR policies
        |                                      |
        +---------- MAIN forwarding -----------+
                                               v
                                  YU traffic Algorithm 1/2
                                  M[l,S], forwardIp/forwardSr
```

SR 与 HoYAN Algorithm 2 的直接关系只有 underlay：Prefix/Node/Adjacency SID 的可达性 guard 来自
IS-IS L1/L2 的 symbolic route selection。SR candidate weight、label-stack forwarding 和 traffic
load 不属于 HoYAN Algorithm 2。

## 4. 论文算法与实现代码逐项对应

| HoYAN 概念 | 实现对象 | 说明 |
| --- | --- | --- |
| route message `m(i->j)` | `SymbolicRouteMessage` | message identity 与 candidate identity 分离 |
| topology condition `R(r)` | `RouteGuard` / `BooleanGuardAst` | 可组合、可序列化、可求值的布尔 AST |
| link availability `a(i->j)` | `SymbolicRouteSession.linkGuard` + `LinkFailureKey` | 两个方向 session 共享无向物理故障 identity |
| device RIB | `GuardedRib` | 同时保存 contribution view 和 candidate view |
| route selection | protocol adapter comparator + `GuardedRib` selection guard | 更优候选的 guard 被纳入低优先级候选条件 |
| propagation queue | `SymbolicRouteConvergenceEngine.WorkItem` | 全网 FIFO，处理 advertise/withdraw |
| propagation tree | `SymbolicRoutePropagationDependencies` | 支持后代递归撤回 |
| `update_condition` | guard algebra + guarded RIB recomputation | 条件更新产生 delta，并继续传播 |
| `withdraw` | engine withdrawal + dependency indexes | 删除 contribution 并递归影响 descendants |
| `ISIS-weight += link cost` | `BatfishIsisProtocolAdapter.processImport` | 使用接收接口 cost 累加 metric |
| IS-IS route selection | `IsisRib.routePreferenceComparator` | 复用 Batfish 协议优选规则 |
| independent BGP/IS-IS RIBs | 独立 `SymbolicRouteNetwork<R>` | 每个 plane 使用自己的 route type 和 adapter |
| redistribution | reconciler 集合 | 比论文描述更完整的持续生命周期实现 |

## 5. 本实现相对 HoYAN Algorithm 2 的扩展

以下内容是工程化扩展，不能全部算作论文 Algorithm 2 原文：

- 保留 typed `IsisRoute`，而非真的将 IS-IS 降成 BGP route；
- 分离 L1 与 L2 guarded RIB，并持续协调 L1→L2 transition；
- 用 Batfish MAIN RIB comparator 完成 IS-IS/BGP/static/connected 跨协议选择；
- 支持 recursive static 的 symbolic activation 和最小不动点；
- 支持 MAIN→BGP redistribution 的持续 advertise/replace/withdraw；
- 建立 canonical link failure identity，使 route、SR 和 traffic 共用同一故障变量；
- 导出版本化、无损的 symbolic control plane JSON；
- 在稳定 IS-IS underlay 上增加 SID/SR-policy 生命周期；
- 将稳定控制面交给后续 traffic-flow 引擎。

## 6. 当前能力边界

阅读或写论文时，建议把结论限制为：

- 已实现基于 Batfish normalized configuration/topology 的 IPv4 point-to-point IS-IS L1/L2
  guarded propagation；
- 已复用 Batfish metric、admin、routing policy、RIB preference 和 static activation 语义；
- 已把 IS-IS、BGP、MAIN、connected/static 与配置支持范围内的 redistribution 装配为持续协调的
  symbolic control plane；
- SR 是该控制面的 guarded 下游，traffic 是 MAIN/SR 的 forwarding 下游。

不应从上述实现直接推导出：

- 完整覆盖所有 Batfish IS-IS/BGP 特性；
- HoYAN Algorithm 2 本身定义了 SR 或 traffic-flow；
- SR policy 参与了 MAIN RIB preference；
- 只运行一次协议 RIB 就自然得到跨 RIB 联合稳定点；该能力来自本仓库的 reconciler/pipeline。

## 7. 推荐阅读顺序

1. `SymbolicRouteConvergenceEngine`：先理解 Algorithm 1 的通用运行时；
2. `GuardedRib`：理解 availability guard、selection guard 与 delta；
3. `BatfishIsisProtocolAdapter`：看 Algorithm 2 只改变了哪些协议语义；
4. `BatfishIsisTopologyAdapter`：看 parser/topology 如何变成 symbolic sessions/seeds；
5. `BatfishIsisLevelTransitionReconciler` 与 `BatfishMainRibReconciler`：看跨 level/plane 协调；
6. `BatfishStaticRouteReconciler` 与 `BatfishBgpRedistributionReconciler`：看反馈环；
7. `BatfishSymbolicRoutePipeline`：最后看完整装配顺序；
8. `GuardedSidReconciler`、`GuardedSrPolicyReconciler`：看 SR 如何消费稳定 underlay；
9. `SymbolicTrafficPipeline`：看 traffic-flow 如何消费 MAIN/SR 输出。

