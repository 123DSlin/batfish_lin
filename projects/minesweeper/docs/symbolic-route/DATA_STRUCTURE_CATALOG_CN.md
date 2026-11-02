# Symbolic Route 数据结构、文件作用与测试对应表

## 1. 范围说明

本文依据 `symbolicroute` 包的 Java 源码和测试源码整理。数据结构分为：

- 核心值对象：描述 guard、路由、身份、消息和来源；
- RIB/传播状态：保存候选、贡献、delta、依赖和收敛状态；
- 拓扑与故障对象：描述 session、物理链路和链路赋值；
- 协议边界对象：封装 BGP、IS-IS、重分发和 static route 所需上下文；
- Pipeline 输入/结果/输出：描述全网运行的输入和稳定结果。

“直接测试”表示测试类直接构造或调用该类型；“间接测试”表示通过 engine、pipeline 或场景验证。

## 2. Guard 数据结构

| 类型 | 源码文件 | 保存的数据及作用 | 关键约束 | 对应测试文件 |
| --- | --- | --- | --- | --- |
| `RouteGuard` | `RouteGuard.java` | 所有符号条件的统一接口；定义 AND、OR、NOT、简化、SAT、逻辑等价和 AST 导出 | 核心路由结构只依赖接口，不直接依赖 Z3 | `GuardedRibTest.java`、`BooleanGuardAstTest.java` |
| `BooleanGuardAst` | `BooleanGuardAst.java` | 保存 `TRUE/FALSE/VARIABLE/NOT/AND/OR` 节点、变量名和子节点；用于规范化及序列化 | VARIABLE 才有 variableId；复合节点通过 children 表达 | `BooleanGuardAstTest.java` |
| `AstRouteGuard` | `AstRouteGuard.java` | 不依赖 solver 的 AST guard 实现 | 适用于轻量布尔代数；复杂 SAT 能力不等同 Z3 | 主要由 symbolic traffic 路径间接覆盖 |
| `Z3RouteGuard` | `Z3RouteGuard.java` | 同时封装 Z3 `BoolExpr` 和 `BooleanGuardAst`；执行 SAT、等价及 k-failure 查询 | 运算必须使用兼容的 Z3 context/guard 实现 | `GuardedRibTest.java`、各 convergence/pipeline 测试 |
| `Z3RouteGuardFactory` | `Z3RouteGuardFactory.java` | 在一个 Z3 context 内创建变量、true/false guard，并从 AST 重建 guard | 所有经该 factory 创建的 expression 共享 context | `BooleanGuardAstTest.java`、`GuardedRibTest.java` |

## 3. 核心路由和身份数据结构

| 类型 | 源码文件 | 字段/保存内容 | 功能与关键约束 | 对应测试文件 |
| --- | --- | --- | --- | --- |
| `SymbolicRoute<R>` | `SymbolicRoute.java` | key、concrete route、availability guard、provenance | 表示一个符号候选；构造时要求 key 内 route 等于 payload；`withAvailabilityGuard` 返回新对象 | `SymbolicRouteModelTest.java`、`GuardedRibTest.java` |
| `SymbolicRouteKey` | `SymbolicRouteKey.java` | router、VRF、完整 `AbstractRouteDecorator` | RIB candidate 的稳定身份；protocol/prefix 从 route 派生；`toString()` 不是完整 identity | `SymbolicRouteModelTest.java`、`GuardedRibTest.java` |
| `SymbolicRouteContributionId` | `SymbolicRouteContributionId.java` | messageId、sender、receiver | 一条有向通告贡献的身份；多个 contribution 可支持同一 candidate | `SymbolicRouteModelTest.java`、`GuardedRibTest.java`、`SymbolicRouteConvergenceEngineTest.java` |
| `SymbolicRouteProvenance` | `SymbolicRouteProvenance.java` | origin、current、previous、incoming interface、router path、parent message id | 保存传播来源；path 必须从 origin 开始、以 current 结束，并进行不可变复制 | `SymbolicRouteModelTest.java`、`SymbolicRouteExporterTest.java` |
| `SymbolicRouteMessage<R>` | `SymbolicRouteMessage.java` | messageId、sender、receiver、sessionId、stage、route、guard、provenance | engine 队列中的协议消息；stage 区分 EGRESS/INGRESS | `SymbolicRouteModelTest.java`、`SymbolicRouteIngressProcessorTest.java`、`SymbolicRouteConvergenceEngineTest.java` |
| `SymbolicRouteSeed<R>` | `SymbolicRouteSeed.java` | messageId、origin router、route、guard、可选 link failure key | 把本地起源 route 转为 sender=receiver=origin 的 INGRESS message | `SymbolicRouteNetworkFactoryTest.java`、`LinkFailureKeyTest.java`、pipeline 场景测试 |
| `SymbolicStaticRoute` | `SymbolicStaticRoute.java` | message id、contribution message id、router、annotated static route、configuration guard | 尚待 next-hop-IP 激活计算的 static route 输入 | `BatfishProtocolSemanticsTest.java`、`BatfishSymbolicRoutePipelineTest.java` |

### 3.1 三种身份的区别

```text
SymbolicRouteKey
  └─ 标识 RIB 中“哪一个候选”

SymbolicRouteContributionId
  └─ 标识“哪一条有向消息正在支持该候选”

SymbolicRouteSession.sessionId
  └─ 标识“消息经过哪一条有向协议邻接”
```

不能使用 message text、route `toString()`、输出记录或列表位置替代上述身份。

## 4. Guarded RIB 数据结构

| 类型 | 源码文件 | 保存的数据及作用 | 状态变化 | 对应测试文件 |
| --- | --- | --- | --- | --- |
| `GuardedRib<R>` | `GuardedRib.java` | candidate map、candidate→contribution map、contribution→sessionId map、preference comparator | contribution 写入后 OR availability；扫描严格更优 route 计算 selection；返回 delta | `GuardedRibTest.java`、`SymbolicRouteIngressProcessorTest.java`、`SymbolicRouteConvergenceEngineTest.java` |
| `GuardedRibEntry<R>` | `GuardedRibEntry.java` | `SymbolicRoute`、selection guard | candidate 的只读计算视图；availability 从 symbolic route 取得 | `GuardedRibTest.java`、`SymbolicRouteExporterTest.java` |
| `GuardedRibUpdateType` | `GuardedRibUpdateType.java` | `ADDED`、`REMOVED`、`GUARDS_CHANGED` | RIB 对外暴露的三类 candidate 变化 | `GuardedRibTest.java`、engine 测试间接覆盖 |
| `GuardedRibUpdate<R>` | `GuardedRibUpdate.java` | update type、nullable old entry、nullable new entry | ADDED 只有 new，REMOVED 只有 old，GUARDS_CHANGED 同时含 old/new | `GuardedRibTest.java`、`SymbolicRouteConvergenceEngineTest.java` |
| `GuardedRibDelta<R>` | `GuardedRibDelta.java` | 不可变 update list | 表示一次 put/remove 影响的全部 candidate；允许 empty/no-op | `GuardedRibTest.java`、Ingress/Engine 测试 |
| `SymbolicRouteIngressResult<R>` | `SymbolicRouteIngressResult.java` | destination candidate key、RIB delta | Ingress 安装的返回对象，让 engine 知道哪个 key 变化及变化内容 | `SymbolicRouteIngressProcessorTest.java`、`SymbolicRouteConvergenceEngineTest.java` |

`GuardedRib` 内部最关键的三个 Map：

```text
_routes[key] = 合并后的 candidate
_contributions[key][contributionId] = 单个来源的 symbolic route
_contributionSessionIds[contributionId] = 原始有向 session
```

## 5. 传播与收敛状态结构

| 类型 | 源码文件 | 保存的数据及作用 | 关键实现点 | 对应测试文件 |
| --- | --- | --- | --- | --- |
| `SymbolicRoutePropagationDependencies` | `SymbolicRoutePropagationDependencies.java` | parent→children 和 child→parents 双向 Map | `replaceParents` 先移除 child 旧入边；用于保存传播因果关系 | `SymbolicRouteExporterTest.java`、`SymbolicRouteConvergenceEngineTest.java` |
| `SymbolicRouteIngressProcessor<R>` | `SymbolicRouteIngressProcessor.java` | receiver、RIB、ingress policy、key factory | `prepare` 先做策略和 identity 验证，`install` 才改变 RIB | `SymbolicRouteIngressProcessorTest.java` |
| `PreparedCandidate<R>` | `SymbolicRouteIngressProcessor.java` 内部类 | contribution id、candidate、sessionId | prepare/install 之间的临时不可变对象，防止校验失败后部分写入 | `SymbolicRouteConvergenceEngineTest.java` 间接覆盖 |
| `SymbolicRouteExporter<R>` | `SymbolicRouteExporter.java` | sender、receiver、sessionId、link guard、egress policy、message-id factory、dependency graph | 使用 `selectionGuard AND linkGuard`；生成 child message 并延伸 provenance | `SymbolicRouteExporterTest.java` |
| `SymbolicRouteConvergenceEngine<R>` | `SymbolicRouteConvergenceEngine.java` | ingress registry、outgoing exporters、contribution locations、advertisement records、stable listeners | 全局 FIFO 处理 advertise/withdraw；delta 触发旧导出撤回和新导出 | `SymbolicRouteConvergenceEngineTest.java` |
| `WorkItem<R>` | `SymbolicRouteConvergenceEngine.java` 内部类 | type、message 或 withdrawal id、expected guard | 队列项分 ADVERTISE/WITHDRAW；expected guard 防止旧撤回删除新状态 | `SymbolicRouteConvergenceEngineTest.java` 间接覆盖 |
| `ContributionLocation` | `SymbolicRouteConvergenceEngine.java` 内部类 | receiver、candidate key、安装时 guard | 定位 contribution 当前安装位置，并参与 stale-withdrawal 判断 | `SymbolicRouteConvergenceEngineTest.java` 间接覆盖 |
| `AdvertisementRecord` | `SymbolicRouteConvergenceEngine.java` 内部类 | child contribution id、child guard | 记录每个 exporter/candidate/parent 已产生的 child | `SymbolicRouteConvergenceEngineTest.java` 间接覆盖 |
| `SymbolicRouteConvergenceResult` | `SymbolicRouteConvergenceResult.java` | processed messages、processed withdrawals、RIB updates | 一次 queue drain 的计数结果，不保存 RIB 内容 | engine、pipeline、reconciler 测试 |
| `SymbolicRouteNetwork<R>` | `SymbolicRouteNetwork.java` | engine、router→RIB、initial advertisements、dependency graph | 已装配网络的运行门面；`converge()` 重放 initial advertisements | `SymbolicRouteNetworkFactoryTest.java` |

## 6. 协议扩展接口

| 类型 | 源码文件 | 作用 | 对应测试文件 |
| --- | --- | --- | --- |
| `SymbolicRouteProtocolAdapter<R>` | `SymbolicRouteProtocolAdapter.java` | 向通用 engine 提供 preference、import、export、key 和 message-id 语义 | BGP/IS-IS/MAIN adapter 测试 |
| `SymbolicRouteIngressPolicy<R>` | `SymbolicRouteIngressPolicy.java` | 函数式 import policy 边界 | `SymbolicRouteIngressProcessorTest.java` |
| `SymbolicRouteEgressPolicy<R>` | `SymbolicRouteEgressPolicy.java` | 函数式 export policy 边界 | `SymbolicRouteExporterTest.java` |
| `SymbolicRouteKeyFactory<R>` | `SymbolicRouteKeyFactory.java` | import 后根据最终 route 创建 candidate key | `SymbolicRouteIngressProcessorTest.java` |
| `SymbolicRouteMessageIdFactory<R>` | `SymbolicRouteMessageIdFactory.java` | 为 exported route 创建稳定基础 message id | `SymbolicRouteExporterTest.java`、`SymbolicRouteNetworkFactoryTest.java` |
| `SymbolicRouteNetworkFactory` | `SymbolicRouteNetworkFactory.java` | 从 routers、sessions、seeds、adapter 装配 RIB、processor、exporter 和 engine | `SymbolicRouteNetworkFactoryTest.java` |

## 7. 链路和故障数据结构

| 类型 | 源码文件 | 字段/作用 | 关键约束 | 对应测试文件 |
| --- | --- | --- | --- | --- |
| `LinkFailureKey` | `LinkFailureKey.java` | 排序后的两个 router；生成稳定 guard name | 无方向；拒绝 self-link | `LinkFailureKeyTest.java` |
| `SymbolicRouteSession` | `SymbolicRouteSession.java` | sessionId、sender、receiver、link guard、failure key | session 有方向；failure key 必须与 endpoints 对应 | `LinkFailureKeyTest.java`、`SymbolicRouteNetworkFactoryTest.java` |
| `TopologyLinkGuards` | `TopologyLinkGuards.java` | endpoint→failure key、failure key→guard 两张不可变 Map | 同一物理链路的两个 endpoint 应映射到 canonical key | `LinkFailureKeyTest.java`、parsed pipeline 测试间接覆盖 |
| `LinkAvailabilityAssignment` | `LinkAvailabilityAssignment.java` | failure key→Boolean up/down | 极性为 true=up、false=failed；支持 failure count/budget | `LinkAvailabilityAssignmentTest.java` |
| `BatfishTopologyGuardInitializer` | `BatfishTopologyGuardInitializer.java` | 从 Batfish interface topology 构造 canonical key 和 guard | topology endpoint 是初始化输入，输出供 seed/session 共享 | parsed pipeline 和 traffic demo 测试间接覆盖 |

## 8. Batfish 协议上下文与结果对象

| 类型 | 源码文件 | 保存的数据及功能 | 对应测试文件 |
| --- | --- | --- | --- |
| `BatfishBgpEdge` | `BatfishBgpEdge.java` | session id、sender/receiver VRF、Configuration、peer、process、session properties、peer IP/interface | `BatfishBgpProtocolAdapterTest.java`、pipeline 测试 |
| `BatfishIsisEdge` | `BatfishIsisEdge.java` | session id、`IsisEdge`、两端 Configuration 和 Interface | IS-IS algorithm/L2/pipeline 测试 |
| `BatfishRoutingPolicyResult<R>` | `BatfishRoutingPolicyResult.java` | outcome 和可选 transformed output route | 明确区分 ACCEPTED、DENIED、POLICY_NOT_FOUND | `BatfishRoutingPolicyProcessorTest.java` |
| `BatfishRedistributionKey` | `BatfishRedistributionKey.java` | source message、router、target VRF/protocol 等重分发身份 | 作为 installed redistribution 的稳定 Map key | `BatfishRedistributionReconcilerTest.java` |
| `BatfishBgpRedistributionRule` | `BatfishBgpRedistributionRule.java` | rule id、router、source/target VRF、policy、target protocol | 描述一条 MAIN→BGP 配置边界 | `BatfishSymbolicRoutePipelineTest.java`、BGP pipeline 测试 |

## 9. Reconciler 持久状态

这些类型不只是 DTO，而是持有跨 stable snapshot 的状态。

| 类型 | 源码文件 | 主要持久字段/作用 | 对应测试文件 |
| --- | --- | --- | --- |
| `BatfishMainRibReconciler` | `BatfishMainRibReconciler.java` | sources、plane names、SourceKey→messageId、SourceKey→active MAIN route | IS-IS/BGP 的 selected contribution 与 MAIN contribution 做 semantic diff | `BatfishIsisAlgorithm2Test.java`、`BatfishIsisLevel2PipelineTest.java`、pipeline 测试 |
| `BatfishIsisLevelTransitionReconciler` | `BatfishIsisLevelTransitionReconciler.java` | TransitionKey→messageId/active transition | 把符合条件的 L1 contribution 协调成 L2 contribution | `BatfishIsisLevel2PipelineTest.java` |
| `BatfishRedistributionReconciler<R>` | `BatfishRedistributionReconciler.java` | redistribution key→installed contribution/route/guard | 根据 policy outcome 执行 advertise、withdraw 或 replace | `BatfishRedistributionReconcilerTest.java` |
| `BatfishBgpRedistributionReconciler` | `BatfishBgpRedistributionReconciler.java` | rule/source identity、last guard、generic route reconciler、防重入状态 | 扫描 MAIN selected branches 并执行 BGP redistribution | `BatfishBgpProtocolAdapterTest.java`、pipeline 测试 |
| `BatfishStaticRouteReconciler` | `BatfishStaticRouteReconciler.java` | owned keys、static route→active guard、started/reconciling/pending | 从 scratch MAIN 重算 recursive static 最小不动点并应用差异 | `BatfishProtocolSemanticsTest.java` |

## 10. Pipeline 输入、结果和输出结构

| 类型 | 源码文件 | 保存的数据及作用 | 对应测试文件 |
| --- | --- | --- | --- |
| `BatfishSymbolicRoutePipelineInput` | `BatfishSymbolicRoutePipelineInput.java` | configurations、MAIN seeds、recursive static、redistribution rules、BGP/IS-IS edges/sessions/seeds、concrete MAIN RIBs | 全网 symbolic route 运行的强类型输入 | `BatfishSymbolicRoutePipelineTest.java`、parsed pipeline 测试 |
| `BatfishSymbolicRoutePipelineResult` | `BatfishSymbolicRoutePipelineResult.java` | MAIN/BGP/IS-IS L1/L2 networks、reconcilers、convergence results、SID/SR-policy DB、link-variable map | 稳定状态聚合对象，并生成 readable/raw/JSON/forwarding views | pipeline、IS-IS、SR policy、traffic demo 测试 |
| `SymbolicRibRecord` | `SymbolicRibRecord.java` | plane、router、VRF、prefix、protocol、next hop、metric、admin、route text、guards、contribution/path | 最终 RIB 的确定性可序列化报告视图，不参与 route identity | `ToleranceFourRouterParsedPipelineTest.java`、pipeline/traffic demo 测试 |
| `SymbolicControlPlaneExport` | `SymbolicControlPlaneExport.java` | schema/version 和完整控制面导出记录 | 面向机器消费的版本化输出结构 | `SymbolicRouteExporterTest.java` 及 pipeline 输出路径间接覆盖 |

## 11. 数据结构到测试文件的快速反查

| 想验证的内容 | 首选测试文件 |
| --- | --- |
| guard AST、Z3 等价和 SAT | `BooleanGuardAstTest.java`、`GuardedRibTest.java` |
| key、route、message、provenance、contribution identity | `SymbolicRouteModelTest.java` |
| candidate/contribution Map、availability/selection、delta | `GuardedRibTest.java` |
| ingress 数据转换和安装 | `SymbolicRouteIngressProcessorTest.java` |
| exporter message、link guard、provenance、dependency | `SymbolicRouteExporterTest.java` |
| FIFO、advertisement records、withdrawal、replacement | `SymbolicRouteConvergenceEngineTest.java` |
| router/session/seed 装配 | `SymbolicRouteNetworkFactoryTest.java` |
| static route fixed point | `BatfishProtocolSemanticsTest.java` |
| routing policy result | `BatfishRoutingPolicyProcessorTest.java` |
| redistribution identity/lifecycle | `BatfishRedistributionReconcilerTest.java` |
| BGP edge 和 adapter | `BatfishBgpProtocolAdapterTest.java` |
| IS-IS L1/L2 state | `BatfishIsisAlgorithm2Test.java`、`BatfishIsisLevel2PipelineTest.java` |
| 顶层输入校验和联合收敛 | `BatfishSymbolicRoutePipelineTest.java` |
| parsed snapshot 和最终 records | `ToleranceFourRouterParsedPipelineTest.java` |
| symbolic 与 concrete dataplane 对照 | `TrafficDemoSingleLinkFailureTest.java` |
| SR policy 输出 | `ParsedSrPolicyPipelineTest.java`、`ToleranceSrTeDemoConfigTest.java` |

