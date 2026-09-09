# Symbolic Route Implementation Log

This is an append-only audit log. Existing stage entries should be corrected with a dated
amendment instead of being silently rewritten after their code is committed.

## 中文阅读说明

本文档是追加式实现日志。代码提交后，如果需要修正已有记录，应增加带日期的补充说明，
而不是直接覆盖历史结论。每个阶段至少记录目标、变更文件、关键不变量、验证结果、已知
限制、实现/审计提交哈希和回退方法。

## 阶段 1：协议无关的符号路由模型

### 目标与提交

- 工作分支：`feature/yu-symbolic-route`
- 基线提交：`1708bbda7c`
- 实现提交：`bc9f1bb8d4`
- 目标：在引入 Z3、故障变量、BGP/OSPF 适配器和收敛引擎之前，先建立不可变、协议
  无关的 guarded route 数据模型。

### 已增加的能力

- `RouteGuard`：抽象布尔 guard 运算，不绑定 Z3 或 BDD。
- `SymbolicRoute`：把具体 Batfish 路由、RIB 存在条件和来源信息组合起来。
- `SymbolicRouteKey`：为未来 guarded RIB 提供候选路由身份。
- `SymbolicRouteProvenance`：记录起点、前一/当前路由器、经过路径及父消息。
- `SymbolicRouteMessage`：区分 ingress 和 egress 阶段的符号路由消息。
- `SymbolicRibUpdate` 与 `SymbolicRibDelta`：表示新增、删除和存在条件变化。

### 关键设计选择

1. `SymbolicRoute` 不继承 Minesweeper 的 `SymbolicRouteBase`。前者表示“具体路由属性 +
   符号拓扑条件”，后者表示 SMT 中符号化的路由属性。
2. `SymbolicRoute` 只保存 RIB 存在条件。选择/导出条件依赖同一 RIB 的全部候选路由，
   将由后续 selector 动态计算。
3. guard 表示通过接口隔离，以免传播核心与特定求解器耦合。
4. 更新类型从第一阶段就支持删除和 guard 变化，为处理“更优路由晚到”产生的撤回与
   级联重算做准备。
5. 协议专有的 route key、比较和 policy 逻辑由 adapter 负责，公共模型中不放置
   BGP/OSPF 专有字段。

### 验证与限制

定向单元测试、Java 格式检查和 `git diff --check` 已通过，新包没有直接依赖 Z3、BGP
或 OSPF。当前尚无具体 guard 实现、guarded RIB、排序/传播/撤回引擎、序列化以及与
tolerance 的绑定。完整命令、基线问题和回退方法见下方英文审计记录。

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

## 阶段 2：Guard Algebra 与 Guarded RIB（2026-08-24）

### 目标

按照 Hoyan Algorithm 1 和论文第 5.4 节实现符号 guard 运算及协议无关的 guarded RIB，
并明确区分：

- `availabilityGuard`：路由规则在 RIB 中存在的拓扑条件，即论文中的 `R(r)`；
- `selectionGuard`：该候选能被 route selector 选中并送往 egress 的条件。

对于候选 `r_i`，guarded RIB 动态计算：

```text
selectionGuard(r_i) = availabilityGuard(r_i)
                      AND NOT availabilityGuard(r_1)
                      ...
                      AND NOT availabilityGuard(r_(i-1))
```

这里只排除严格更优候选；同优先级候选互不抑制，以保留后续 ECMP/traffic execution 所需
的 next-hop 分支。

### 实现内容

- `Z3RouteGuard` 和 `Z3RouteGuardFactory`：Z3 Boolean guard 的构造、逻辑运算、化简、
  可满足性和语义等价判断。
- `GuardedRib`：注入协议 adapter 提供的 route comparator，保存 availability guard，
  每次新增、替换或删除候选后重新推导 selection guard。
- `GuardedRibEntry`：同时暴露候选的 availability guard 与派生 selection guard，但不把
  selection guard 写回 `SymbolicRoute`。
- `GuardedRibDelta`、`GuardedRibUpdate`：显式区分新增、删除和 guards 变化，供后续
  Algorithm 1 propagation tree/withdraw 逻辑消费。
- `SymbolicRoute` 的主要术语由 presence guard 改为 availability guard；旧 getter/setter
  暂时保留为 deprecated 兼容入口。

### 已验证的不变量

1. `availabilityGuard` 不会因为更优候选到达而改变。
2. 更优候选晚到会缩小低优先级候选的 `selectionGuard` 并产生 change delta。
3. 删除更优候选会恢复低优先级候选的 `selectionGuard`。
4. 更新更优候选的 availability guard 会重新计算所有受影响的低优先级候选。
5. 同优先级候选互不抑制。
6. 不同到达顺序得到语义等价的最终 guards。
7. guard 的等价性使用 Z3 语义判断，不依赖表达式字符串或 AST 排列顺序。

多层优先级测试补充（2026-08-24）：

- 三级候选验证最低层的 selection guard 同时排除最高层与中间层 availability guard；
- 最高优先级候选晚到时，两个已有下层候选都产生 `GUARDS_CHANGED`；
- 删除中间优先级候选时，只恢复其下层候选，上层 selection guard 保持不变；
- 四级候选以非优先级顺序到达时，最低层仍累计排除全部三个严格更优候选。

Guarded RIB 边界语义补充（2026-08-24）：

- 重复插入相同候选不产生 update；相同 key 且 availability guard 语义等价（即使 Z3
  AST 顺序不同）的替换也不产生 update。
- priority group 按“严格更优”关系处理：同一组 ECMP 候选互不抑制，但组内每个候选都
  同时受全部更高优先级组候选抑制。测试覆盖两个高优先级 ECMP 候选和两个低优先级
  ECMP 候选，并采用交错到达顺序。
- 不可满足的 availability guard 等价于候选不存在：新候选不进入 RIB 且不产生 delta；
  若同 key 候选已存在，则按删除处理，并重新计算所有受影响的低优先级 selection guard。
- 不可满足性测试使用 `a AND NOT a`，确保策略依赖语义 SAT 判断而非仅识别语法上的
  `false` 常量。

定向测试命令：

```bash
bazel test //projects/minesweeper:minesweeper_tests \
  --test_filter='org.batfish.minesweeper.symbolicroute.(GuardedRibTest|SymbolicRouteModelTest)'
```

结果：通过。`//projects/minesweeper:minesweeper_tests_pmd` 和主源码
`//projects/minesweeper:pmd` 均通过。

### PMD compatibility cleanup amendment (2026-08-24)

首次运行全量主源码 PMD 时，当前分支中旧的 Minesweeper/tolerance 代码暴露出未使用
import/局部变量、具体集合类型、参数重赋值、空代码块和循环末尾分支等违规。虽然新增
`symbolicroute` 包没有出现在违规列表中，但为了让本阶段的完整质量门禁真正通过，已对
以下既有文件做语义保持的清理：

- `Graph.java`
- `smt/Encoder.java`
- `smt/EncoderSlice.java`
- `smt/PropertyChecker.java`
- `smt/SymbolicRoute.java`
- `smt/SymbolicRouteBV.java`
- `smt/SymbolicRouteBase.java`
- `smt/TransferSSA.java`

清理方式包括删除未使用项、使用 `List` 接口、以局部变量替代参数重赋值、将明确的
no-op 分支改为等价控制流，以及将输出目录查找重构为无提前跳出的有界循环。最终使用
`--nocache_test_results` 验证：主源码 PMD、测试源码 PMD 和 symbolic-route 定向测试
全部通过。Java 8 source/target 的“已过时”信息来自 JDK 工具链，是编译警告而非测试失败。

完整 Minesweeper 测试最初还暴露出
`SearchRoutePoliciesAnswererTest.testMatchGeneralRegexCommunity` 的非确定性断言：策略正则
`^.*$` 允许任意 community，但测试固定期待 Z3 选择 `0:0`。测试现已给输入增加明确的
`0:0` constraint，既保留“通用正则接受该 community”的测试目标，又消除对 solver model
取值顺序的依赖。最终完整验收结果：

```text
//projects/minesweeper:minesweeper_tests      PASSED (182 tests)
//projects/minesweeper:pmd                    PASSED
//projects/minesweeper:minesweeper_tests_pmd  PASSED
```

### Stage 2 scope correction (2026-08-24 16:04 CST)

- Correction commit: `0d2ac98068`
- Original implementation commit: `241ba44b21`

Stage 2 实现提交曾为消除仓库既有 PMD 违规而修改 `Graph`、SMT encoder、property checker、
transfer 和 search-policy test 文件，并引入整文件格式化噪声。这些改动与 guarded RIB
无关，审计和合并风险过高，现已通过纠正提交撤回。

以下 9 个文件已使用 Git blob hash 逐个验证，与 `241ba44b21^`（Stage 2 实现提交前）
字节级一致：

- `Graph.java`
- `smt/Encoder.java`
- `smt/EncoderSlice.java`
- `smt/PropertyChecker.java`
- `smt/SymbolicRoute.java`
- `smt/SymbolicRouteBV.java`
- `smt/SymbolicRouteBase.java`
- `smt/TransferSSA.java`
- `SearchRoutePoliciesAnswererTest.java`

纠正后 Stage 2 只保留 `symbolicroute` 包和对应 focused tests 的修改。恢复后重新运行
`GuardedRibTest` 与 `SymbolicRouteModelTest`，结果通过。全局 PMD 和原 search-policy
非确定性测试重新归为分支基线问题，不再通过修改无关核心代码来规避。

### Baseline test reproduction (2026-08-24 16:10 CST)

在独立临时 worktree 中 checkout 最早基线提交
`1708bbda7cb6000105896a47a0bc1fc46f49f772`，执行未过滤的
`//projects/minesweeper:minesweeper_tests`。基线共运行 169 个测试，并在
`SearchRoutePoliciesAnswererTest.testMatchGeneralRegexCommunity` 第 393 行出现同一失败。
因此该失败在 Stage 1 提交之前已存在，不是 Stage 1 或 Stage 2 引入。临时 worktree 已在
验证后删除，当前功能分支工作区保持干净。

随后检查更早的祖先提交 `a0f78dba38ddf8ecf4f68840cde456babd5d452e`。该版本在当前
macOS 环境中因 Bazel sandbox 引用不存在的 `/System/Volumes/Data/home/deza` 而无法完成
构建，因此没有声称在该提交上直接复现 JUnit 失败。但 Git 验证显示：

- `a0f78dba38` 是 `1708bbda7c` 的祖先；
- 两个提交中的 `SearchRoutePoliciesAnswererTest.java` blob hash 均为
  `73bb28c84f66c275ea5f4831d6b4da39c75e79c1`；
- 对应的 `question/searchroutepolicies` 主源码目录在两个提交之间无差异。

因此，直接证据已经证明失败存在于 Stage 1 基线 `1708bbda7c`；更早提交的代码身份也
表明该测试及被测实现不是在 `1708bbda7c` 中引入或修改的，但由于旧版本构建环境问题，
不把它表述为已在 `a0f78dba38` 上直接运行复现。

继续检查更早祖先 `17569485af4064ed08e8ace12d7910aa9c38457b`（2026-08-24
16:29 CST）。该版本同样因旧 Bazel sandbox 的 `/System/Volumes/Data/home/deza` 路径而
无法构建。其 `SearchRoutePoliciesAnswererTest.java` blob 仍为相同的 `73bb28c...`，且
对应实现到 `a0f78dba38` 无差异。

根因是测试使用 community regex `^.*$`，却固定断言无约束 Z3 model 必须选择 `0:0`。
最小修复仅修改该测试，为输入 route 增加 `0:0` community constraint；不修改 Graph、
Encoder、policy answerer 或 symbolic-route 实现。修改范围为 1 个测试文件，8 行新增、
1 行替换。修复后未过滤的完整 Minesweeper 测试通过。该测试修复作为独立变更留在工作区
等待审查，不混入 Stage 2 guarded RIB 实现提交。

### 当前边界

- comparator 仍由调用者注入；BGP/OSPF adapter 尚未接入 Batfish 的真实协议比较逻辑。
- 当前实现重算同一 router/prefix 范围内的候选，尚未实现增量依赖索引优化。
- 尚未实现 egress policy、链路 `alive(l)` 条件、消息队列、propagation tree 和递归
  withdraw；这些属于下一阶段。
- 实现代码当前位于工作区，等待代码审查后创建独立实现提交；审计文档由助手单独提交。

### 论文依据

Hoyan Algorithm 1 第 20 行更新传播条件，第 21 行建立 propagation tree，第 24-32 行执行
withdraw。论文第 5.4 节明确说明，RIB rule 的 topology condition 是 `R(r)`，从 RIB 到
egress 的 route update condition 才排除所有高优先级规则。

## Stage 2.1：稳定候选 Key 与传播贡献（2026-08-25 15:23 CST）

### 目标与论文对应

本次修改落实对 Hoyan Algorithm 1 与 YU §4.1/Figure 6 的复核结果：RIB route guard 表示
候选存在条件；多个等价传播来源可对同一候选作出独立贡献，候选 availability guard 是各
贡献 guard 的逻辑析取；withdraw 只移除指定消息贡献，最后一个贡献消失后才删除候选。

### Key 与贡献身份

- `SymbolicRouteKey` 不再接收自由字符串 `sourceId` 和 `attributeFingerprint`。
- candidate key 由 router、VRF 和 Batfish concrete route 构成；protocol 和 prefix 从 route
  派生，避免调用者构造互相矛盾的字段。
- `SymbolicRoute` 构造时验证 key 内的 concrete route 与 payload 相同，禁止同 key 静默
  替换成不同 route。
- 新增 `SymbolicRouteContributionId(messageId, sender, receiver)`，明确区分传播消息身份与
  route candidate 身份，为后续 propagation tree 和 recursive withdrawal 提供键。
- `GuardedRib.putContribution` 聚合同一候选的 contributions；
  `removeContribution` 只撤回指定 contribution。
- route selection 的 RIB scope 新增 VRF 隔离，避免不同 VRF 的同 prefix route 相互抑制。

### 新增测试

1. 两个消息来源的 guard 被 OR 合并，分别撤回时不会提前删除候选。
2. 同一 contribution 使用逻辑等价 guard 重放不产生无效 update。
3. 不同 VRF 的候选互不参与优先级抑制。
4. key equality 使用 RIB scope 与 concrete route identity。
5. key route 与 `SymbolicRoute` payload 不一致时拒绝构造。
6. contribution identity 包含 message ID 及有向 sender/receiver。

### 验证结果与边界

- `GuardedRibTest`、`SymbolicRouteModelTest`：通过。
- 未过滤的完整 `//projects/minesweeper:minesweeper_tests`：通过。
- `minesweeper_tests_pmd`：通过。
- `git diff --check`：通过。
- 主源码 `//projects/minesweeper:pmd` 仍只报告 Stage 2 scope correction 已记录的旧
  `Graph`、`Encoder`、`EncoderSlice`、`PropertyChecker` 和 SMT 文件违规；本次
  `symbolicroute` 文件没有违规，且未修改这些核心旧文件。
- 当前 contribution API 尚未连接 work queue/propagation tree；这是 Stage 3 的职责。
- 当前 key 覆盖 IPv4 `Prefix` 模型；IPv6/address-family 扩展将在协议 adapter 接入前增加。

### Git 记录

- 实现提交：`d6f913850f6e2efb41e9d41bb1b6fcb5c43f0556`
- 实现提交时间：2026-08-25 15:23 CST（提交信息精确到分钟）
- 审计文档更新时间：2026-08-25 15:25 CST
- 回退实现：`git revert d6f913850f`
- 审计提交和远端 push 状态由紧随其后的审计提交记录。

## Stage 3.1：初始化、Work Queue、Ingress 与 RIB 更新（2026-08-25 15:39 CST）

### 算法范围

本阶段严格限定为 Hoyan Algorithm 1 第 2–10 行：

- 第 2–3 行：接收并初始化 route advertisements；
- 第 4–5 行：用确定性 FIFO work queue 逐条消费消息；
- 第 6–7 行：执行 receiver ingress policy，DENY 消息不进入 RIB；
- 第 8–9 行：对 ACCEPT 后的 concrete route 构造 candidate key，并调用 Stage 2 guarded
  RIB 完成 route selection 与 contribution update；
- 第 10 行：为后续 egress/propagation 收集非空 RIB deltas。

本阶段尚未实现 Algorithm 1 第 11–32 行的 late-higher-priority、egress、link guard、
propagation dependency 与 recursive withdrawal。

### 实现结构

- `SymbolicRouteWorkQueue`：协议无关、确定性的 FIFO 消息队列。
- `SymbolicRouteIngressPolicy`：协议 adapter 契约，返回 DENY 或处理后的 concrete route。
- `SymbolicRouteKeyFactory`：在 ingress policy 完成后为处理后的 route 构造 scoped key。
- `SymbolicRouteIngressProcessor`：绑定单一 receiver RIB，消费初始消息直至队列为空。
- BGP/OSPF policy 细节没有复制到公共核心；后续 adapter 应调用 Batfish 对应的真实
  `RoutingPolicy.process` 和协议 route builder/session API。

### 已验证语义

1. 初始化消息严格按 FIFO 顺序执行且最终队列为空。
2. ingress DENY 不产生 RIB entry 或 delta。
3. ingress 修改后的 route 同时决定 key 与 RIB payload，输入 route 不会误入 RIB。
4. 同一消息用逻辑等价 guard 重放不产生无效 delta。
5. 不同消息产生相同 candidate 时 availability guard 做逻辑 OR。
6. ingress processor 拒绝 EGRESS 消息。
7. processor 绑定 receiver，拒绝写入其他 router 的消息；key factory 结果也必须属于该
   receiver。

### 验证与基线

- Stage 1–3.1 symbolic-route 定向测试：通过。
- 未过滤的完整 `//projects/minesweeper:minesweeper_tests`：通过。
- `//projects/minesweeper:minesweeper_tests_pmd`：通过。
- `git diff --check`：通过。
- 主源码 PMD 仍只报告已记录的旧核心文件基线违规；本阶段新增文件没有出现在违规列表，
  且没有修改 `Graph`、`Encoder`、`EncoderSlice` 或 `PropertyChecker`。

### Git 记录

- 实现提交：`20144c498e517954ec78877cf413093033d7b24c`
- 实现提交时间：2026-08-25 15:39 CST
- 审计文档更新时间：2026-08-25 15:40 CST
- 回退实现：`git revert 20144c498e`
- 审计提交与 push 状态由本记录的独立文档提交保存。

## Update 模型冗余清理（2026-08-25 15:45 CST）

### 清理原因

Stage 1 的 `SymbolicRibUpdate`、`SymbolicRibDelta`、`SymbolicRibUpdateType` 只描述
`SymbolicRoute` 的 availability guard 变化。Stage 2 引入的 `GuardedRibUpdate`、
`GuardedRibDelta`、`GuardedRibUpdateType` 基于 `GuardedRibEntry`，同时表达 availability
与 selection guard 的变化，已经完全取代前一组类型。旧类型没有生产调用，仅由孤立单元
测试引用，继续保留会让 Stage 3 propagation 出现两套 delta 语义。

### 已删除与保留

删除：

- `SymbolicRibUpdate.java`
- `SymbolicRibDelta.java`
- `SymbolicRibUpdateType.java`
- 上述孤立类型对应的测试
- `SymbolicRoute.getPresenceGuard/withPresenceGuard` 过渡别名

保留：

- `SymbolicRoute`：单个 concrete route candidate 与 availability guard；
- `GuardedRib`：候选集合、contribution 聚合和 route selection；
- `GuardedRibEntry`：availability 与派生 selection guard；
- `GuardedRibUpdate/Delta`：唯一正式的 RIB 变化模型。

### 验证与 Git

- 净删除 167 行；未修改 Minesweeper 核心旧文件。
- symbolic-route 定向测试：通过。
- 未过滤的完整 Minesweeper 测试：通过。
- test PMD 与 `git diff --check`：通过。
- 实现提交：`eeef747498a50a920a25557179a32c530d57e22d`
- 提交时间：2026-08-25 15:45 CST
- 回退：`git revert eeef747498`

## Stage 3.2：Egress、链路 Guard 与传播依赖（2026-08-25 16:06 CST）

### 算法范围

本阶段实现 Hoyan Algorithm 1 第 17–22 行的协议无关边界：对选中的 guarded RIB entry
应用 egress policy，生成发往 peer 的 advertisement，把 route 的 `selectionGuard` 与
链路存活 guard 合取，并建立 parent contribution 到 child advertisement 的 propagation
dependency。生成的消息已处于 receiver 的 `INGRESS` 边界，可由后续全网收敛引擎重新
放入 work queue。

### 实现结构

- `SymbolicRouteEgressPolicy`：由 BGP/OSPF adapter 实现的 ACCEPT/DENY/route transform
  契约。
- `SymbolicRouteMessageIdFactory`：由 adapter 提供稳定的输出 advertisement identity。
- `SymbolicRouteExporter`：验证 sender/RIB/provenance 边界，应用 policy，计算
  `selectionGuard AND linkGuard`，扩展 provenance path 并生成 INGRESS 消息。
- `SymbolicRoutePropagationDependencies`：使用 typed contribution identity 保存
  parent-to-child 集合；集合去重，且只对实际生成的消息建立依赖。

### 已验证语义

1. 输出 guard 使用 selection guard 而非 availability guard，并正确合取链路 guard。
2. egress DENY 不生成 advertisement，也不产生伪 dependency。
3. 不可满足的 `selectionGuard AND linkGuard` 被剪枝。
4. egress transform 后的 concrete route 被写入输出消息。
5. 多个 parent contribution 可共同依赖同一个聚合后的 child advertisement。
6. provenance path 从 sender 扩展至 receiver；单 parent 时保存 parent message ID。
7. exporter 拒绝不属于 sender RIB 的 entry。

### 验证、限制与 Git

- Stage 1–3.2 定向测试：通过。
- 未过滤的完整 Minesweeper 测试：通过。
- test PMD 与 `git diff --check`：通过。
- 主源码 PMD 仍只报告已记录的旧核心文件基线；新增文件没有违规。
- 尚未把 exporter 输出接回全局 work queue，也未实现依赖删除与 recursive withdrawal；
  因此本阶段不宣称已经实现 Algorithm 1 第 23–32 行或全网收敛。
- 实现提交：`fa3ec406d2e3d3ca6f49f8e91742ffc04df50cb7`
- 提交时间：2026-08-25 16:06 CST
- 回退：`git revert fa3ec406d2`

## Stage 3.3：多跳 Work Queue 单调收敛（2026-08-25 16:17 CST）

### 算法范围

本阶段把 Stage 3.1 ingress processor 与 Stage 3.2 exporter 接入网络级 FIFO work queue。
每条消息在 receiver 执行 ingress、更新 guarded RIB；只有非空 delta 才触发该 router 的
outgoing exporters，产生的下一跳消息重新进入队列。队列为空时返回处理消息数和 RIB
update 数，从而实现 Algorithm 1 第 23 行的单调传播收敛核心。

### 实现内容

- `SymbolicRouteConvergenceEngine`：注册每个 router 唯一的 ingress processor，校验每条
  exporter edge 的两端均存在，迭代处理全网 queue。
- `SymbolicRouteConvergenceResult`：记录 processed messages 与 effective RIB updates。
- `GuardedRib.getContributionIds`：向 exporter 提供当前 candidate 的全部父贡献。
- ingress processor/exporter 增加只读 receiver、RIB、sender 访问器，用于网络编排，不
  暴露可变内部集合。

### 测试覆盖

1. A→B→C 三路由器传播并收敛，C 的 guard 等价于 seed∧alive(A-B)∧alive(B-C)。
2. 相同 seed message 重放只处理入口消息，产生 0 个 RIB update，不继续传播。
3. egress DENY 正确剪断传播分支。
4. 发往未注册 receiver 的消息被拒绝。
5. exporter endpoints 必须都具有 ingress processor。

### 安全边界、验证与 Git

- 当前只宣称单调收敛核心。若变化会删除旧 RIB entry 或使先前 advertisement 消失，
  engine 显式抛出 `UnsupportedOperationException`，而不是留下过期下游 route。
- 解除该限制需要 Stage 3.4 的 advertisement registry、dependency removal 和 recursive
  withdrawal（Algorithm 1 第 24–32 行）。
- Stage 1–3.3 定向测试、完整 Minesweeper 测试、test PMD、`git diff --check` 均通过。
- 主源码 PMD 只报告既有基线文件；新增 convergence 文件没有违规。
- 实现提交：`09e080b84e1eece5fb4429cf6ec3d2a3c4d8f487`
- 实现提交时间：2026-08-25 16:17 CST
- 审计更新时间：2026-08-25 16:18 CST
- 回退：`git revert 09e080b84e`

## Stage 3.4：Advertisement Registry 与 Recursive Withdrawal（2026-08-25 16:36 CST）

### 算法范围

本阶段实现 Hoyan Algorithm 1 第 24–32 行，并解除 Stage 3.3 对非单调变化的临时限制。
当 RIB entry 被删除或 guard/selection 改变时，engine 先从 advertisement registry 找到
每个 outgoing peer 上的旧 child contribution，删除旧 dependency 并将 WITHDRAW 放入
全局 FIFO queue；随后按新 guard 生成 ADVERTISE。下游处理 withdrawal 后产生的新 RIB
delta 会重复相同流程，从而递归撤回全部后代，再传播新结果，直到 queue 为空。

### 实现结构

- `SymbolicRouteWorkItem`：统一表示 `ADVERTISE` 与带 expected-old-guard 的 `WITHDRAW`。
- `SymbolicRouteIngressResult`：一次 ACCEPT ingress 的 candidate key 与 RIB delta，避免
  convergence engine 猜测 policy transform 后的 key。
- convergence engine 持久保存：
  - contribution ID → receiver/key/当前 guard 的位置索引；
  - exporter/candidate key → 已发布 child ID/guard 的 advertisement registry。
- propagation dependencies 现在同时保存 parent→children 与 child→parents，并支持
  `replaceParents`、`removeChild`，不会在重传播时遗留旧边。
- withdrawal 携带 expected old guard；如果同 ID 的新版本已经到达，过期 withdrawal
  会被忽略，防止稳定 message ID 下的旧事件误删新 contribution。

### 已验证语义

1. A→B→C 上低优先级 route 先收敛后，高优先级 route 到达会产生递归 withdrawal。
2. 低优先级 route 使用收缩后的 `low AND NOT high` guard 重新传播，高优先级 route 同时
   正常传播至 C。
3. high-first 与 late-high 两种到达顺序得到逻辑等价的最终 guards。
4. 从根 contribution 发起 withdrawal 会删除 A、B、C 上的 route，并清除根的 child
   dependency。
5. 两个 contribution 支撑同一 candidate 时只撤回一个，candidate 和另一个来源仍保留，
   下游 guard 被正确缩小。
6. 重复 withdrawal 幂等，不产生消息或 RIB update。
7. 相同 child 重传播时原 parent edges 被完整替换，不留悬空 dependency。

### 验证、限制与 Git

- Stage 1–3.4 定向测试：通过。
- 未过滤的完整 Minesweeper 测试：通过。
- test PMD 与 `git diff --check`：通过。
- 主源码 PMD 只报告既有基线文件，本阶段文件没有违规。
- 当前仍显式拒绝“同一 contribution ID 经 ingress policy 后移动到不同 candidate key”；
  固定配置快照中的正常 guard 更新与 late-high 不触发此限制。协议 adapter 接入时将决定
  message identity 是否应随 transformed route 改变，或实现跨 key 原子迁移。
- 实现提交：`ef2d6e2767714b62269aeec28094de91ea4f8ada`
- 实现/审计更新时间：2026-08-25 16:36 CST
- 回退：`git revert ef2d6e2767`

## Stage 3.4 补强：Contribution Identity 与 Route Replacement（2026-08-25 16:49 CST）

### 明确的身份契约

1. 在固定配置快照下，同一 contribution ID 必须由 ingress policy 确定性地映射到同一
   candidate key（即同一 concrete transformed route 所属候选）。
2. 普通 guard 更新只更新该 contribution 的 availability guard，不得改变 concrete route
   或 candidate key。
3. 上游 route attributes 或配置策略变化导致 transformed route 改变时，调用显式
   `replace(oldContribution, replacementAdvertisement)`：旧 contribution 及其传播后代先
   递归撤回，再使用未占用的新 contribution identity 加入新 candidate。
4. 只有当新旧 route 在协议语义上本来就应同时存在时，调用方才应保留旧 identity，并用
   另一个新 identity 执行普通 advertisement；不得把 coexistence 表示成 replacement。

### 实现与安全性

- ingress 被拆成 `prepare` 与 `install` 两阶段。policy transform 和 key 构造先完成，
  convergence engine 在修改 RIB 前检查既有 identity 的 key，因此非法跨 key 更新会抛出
  `IllegalArgumentException`，且不会留下半写入的新 candidate。
- `replace` 要求旧 identity 已存在、新 identity 与旧 identity 不同且尚未被占用；校验通过
  后，在同一次 FIFO run 中顺序加入旧 contribution 的 WITHDRAW 与新 advertisement。
- 新增 `SymbolicRouteIngressCandidate`，仅承载已完成 ingress policy、但尚未写入 RIB 的
  contribution/candidate 对，不引入协议专属字段。

### 测试与验证

- route replacement 在 A→B 拓扑递归删除旧 route，并把新 identity/new route 传播到 A、B。
- 复用旧 identity、旧 identity 不存在或新 identity 已占用均被拒绝。
- 同一 identity 携带不同 concrete route 会在 RIB 写入前被拒绝；断言旧 candidate 保留且
  新 candidate 不存在，验证失败路径无状态污染。
- `SymbolicRouteConvergenceEngineTest`：通过。
- 未过滤的完整 `//projects/minesweeper:minesweeper_tests`：通过。
- `git diff --check`：通过。
- `//projects/minesweeper:pmd` 仍只报告 `Graph`、`Encoder`、`EncoderSlice`、
  `PropertyChecker` 等既有基线违规；本次 `symbolicroute` 文件没有新增 PMD 违规。
- 实现提交：`bb956a21f2`
- 实现/审计更新时间：2026-08-25 16:49 CST
- 回退：`git revert bb956a21f2`

## Stage 4.1：协议无关的 Symbolic Route Network 装配层（2026-08-25 21:02 CST）

### 阶段边界

本阶段只把 Stage 3.4 的 convergence engine 从“测试中手工拼装”提升为可由协议 adapter
驱动的网络级入口。没有实现 BGP、iBGP、IS-IS、OSPF、static 的具体协议语义，也没有
实现 HoYAn Algorithm 2、SR 或 symbolic traffic execution。

### 实现内容

- `SymbolicRouteProtocolAdapter`：集中声明 receiver preference comparator、import policy、
  import 后 candidate key、session export policy 和稳定 export message identity。协议专属
  属性仍由后续 adapter 处理，不进入通用 convergence engine。
- `SymbolicRouteSession`：表示一条有稳定 session ID 的定向协议邻接及 link guard；显式
  session ID 允许相同 router pair 上的并行 VRF/interface/protocol session 共存。
- `SymbolicRouteSeed`：把本地 originated route、初始 availability guard 和稳定 seed
  identity 转换成合法的 INGRESS advertisement/provenance。
- `SymbolicRouteNetworkFactory`：统一校验 router、session endpoint、session identity、seed
  identity，创建每台 router 的 guarded RIB/ingress processor，以及每条 session 的 exporter。
- `SymbolicRouteNetwork`：保存 immutable RIB registry、initial advertisements、共享
  propagation dependency registry 和 convergence engine，并提供统一 `converge()` 入口。
- `SymbolicRouteMessage`/`SymbolicRouteExporter`：传播 nullable session ID；本地 seed 的
  session ID 为 null，session advertisement 向 import adapter 暴露准确的 session context。

### Identity 与并行 Session 约束

1. session ID 在一个 assembled network 内必须唯一。
2. seed contribution identity 在 factory 阶段必须唯一。
3. export message ID 自动使用长度前缀的 session namespace；即使 adapter 对两条并行
   session 返回相同 route identity，也会形成两个不同 contribution，不会相互覆盖。
4. adapter identity 保持稳定时，重复运行同一 initial seed 是语义 no-op，不产生 RIB delta。

### 测试与验证

- A→B→C 由 factory 自动装配并收敛，C 的 guard 等价于 seed∧link(A-B)∧link(B-C)。
- session ID 从 exporter advertisement 正确传至各 receiver 的 import adapter；本地 seed
  的 session ID 为 null。
- 两条 A→B 并行 session 产生两个独立 contribution；B 的 availability guard 等价于
  `seed AND (link1 OR link2)`。
- 重复 router、未知 session endpoint、未知 seed origin、self-session、重复 session ID、
  重复 seed identity 均在装配阶段被拒绝。
- 重放同一稳定 seed：只消费 seed 消息，产生 0 个 RIB update。
- Stage 4.1 定向测试：通过。
- 未过滤的 `//projects/minesweeper:minesweeper_tests`：通过。
- `//projects/minesweeper:minesweeper_tests_pmd` 与 `git diff --check`：通过。
- 主源码 PMD 只报告此前确认存在于 `17569485af` 的 tolerance/SMT 基线违规；本阶段
  `symbolicroute` 文件没有新增 PMD 违规。
- 未修改 `Graph`、`Encoder`、`EncoderSlice`、`PropertyChecker` 或其他旧 SMT 核心文件。
- 实现提交：`f525a1a199`
- 实现/审计更新时间：2026-08-25 21:02 CST
- 回退：`git revert f525a1a199`

## Stage 4.2：复用 Batfish 精确 Main RIB 与 Static Route 语义（2026-08-25 21:38 CST）

### 复用边界

- `BatfishMainRibRouteAdapter` 直接委托 Batfish `Rib.comparePreference`，不在 Minesweeper
  内重新实现 administrative distance、metric 或跨协议主 RIB 偏好；仅转换 comparator 的
  正负号契约。
- `BatfishStaticRouteResolver` 直接调用 Batfish `Rib.longestPrefixMatch` 与
  `StaticRouteHelper.shouldActivateNextHopIpRoute`，不自行复制 static-route activation 判断。
- `SymbolicStaticRoute` 保持 `AnnotatedRoute<StaticRoute>` 强类型；只有进入协议无关 main RIB
  边界时才安全提升为 `AnnotatedRoute<AbstractRoute>`。
- 本地 static route 安装不虚构 routing policy：Batfish `VirtualRouter.initStaticRibs` 对
  discard、next-hop-interface 和 next-hop-VRF 路由直接初始化；next-hop-IP 路由由
  `VirtualRouter.activateStaticRoutes`/`StaticRouteHelper` 递归激活。协议间 redistribution
  policy 留给后续 BGP/OSPF/IS-IS adapter。

### Symbolic LPM 正确性约束

`Rib.longestPrefixMatch` 是 concrete semantic oracle，不能取代 symbolic LPM。解析 RIB 中
不同长度前缀可在不同 guard 下生效，因此实现将“参与 LPM 的 route”和“可以激活目标 static
route 的 route”分开：

1. Batfish concrete LPM 判定候选是否匹配 next-hop，以及一个前缀是否比另一个更具体；
2. 每个可激活候选的 symbolic guard 都与所有更长匹配前缀的 selection guard 的否定相与；
3. 更长前缀即使不能激活目标 static route，仍然遮蔽较短前缀；
4. 所有条件化候选再取析取，最后与 static route 的 configuration guard 相与。

因此不会把“较短前缀可用”错误近似成“static route 一定可激活”，避免过度估计激活范围。
`GuardedRib.sameRibScope` 同时按 router、VRF、network 隔离普通 route preference；不同前缀
之间的竞争只发生在上述 symbolic LPM 层。

### 递归解析与测试

- `resolveToFixedPoint` 按 Batfish activation oracle 反复计算 next-hop-IP static routes，使用
  稳定 contribution identity 更新 guarded main RIB，直到 guard 逻辑等价稳定。
- main-RIB preference 测试对比 adapter comparator 与 `Rib.comparePreference`。
- symbolic LPM 对所有两变量 guard 赋值逐项构造 concrete `Rib`，与
  `StaticRouteHelper.shouldActivateNextHopIpRoute` 做差分比较。
- 专门覆盖“不能激活目标的更长前缀仍遮蔽可激活短前缀”，防止 symbolic LPM 过度估计。
- 覆盖 connected → static → static 的逆序输入递归链，确认固定点 guard 等价。
- `//projects/minesweeper:minesweeper_tests`：通过。
- `//projects/minesweeper:minesweeper_tests_pmd`：通过。
- 主源码 `//projects/minesweeper:pmd` 仍只报告 34 条已确认的旧 tolerance/SMT 基线违规；
  新增 `symbolicroute` 文件无 PMD 命中。
- `git diff --check`：通过。
- 未修改 `Graph`、`Encoder`、`EncoderSlice`、`PropertyChecker`。
- 实现提交：`afb2b9dc37`
- 实现/审计更新时间：2026-08-25 21:38 CST
- 回退实现：`git revert afb2b9dc37`

## Stage 4.2 Correction：Static Fixed-point 可靠性（2026-08-25 21:56 CST）

### 审计发现与修正

1. **Fixed-point 原子性**：旧实现逐条计算并立即写入，导致同一轮后面的 route 看见本轮前面
   route 的新状态，结果依赖输入顺序；输入中途失败还可能留下部分安装。现改为同步轮次：先从
   同一 RIB 快照计算全部 next guards，再将有语义变化的 advertisement 作为一个 batch 提交。
   所有输入在首次 mutation 前统一验证；周期或运行时失败会撤回本解析器拥有的全部派生 static
   contributions，恢复为无派生 static route 的初始 RIB。
2. **终止检测**：删除不可靠的 `routes.size() + 1` 轮数假设。现在以整个 guard vector 的逻辑
   等价作为 fixed-point 判据，并保存历史语义状态；若新状态等价于非相邻历史状态，则显式报告
   semantic guard cycle，而不是误报超出轮数或留下任意中间结果。
3. **VRF 隔离**：本地 static contribution message ID 采用长度前缀的
   `static:<vrf-length>:<vrf>:<caller-id>` namespace。同一 router、同一 caller message ID 在
   blue/red VRF 中形成不同 contribution identity；candidate 与 LPM 仍严格按 source VRF 过滤。
4. **初始状态**：每次解析前先撤回本解析器对输入 static routes 的旧 contributions，避免上次
   运行结果自我维持。若相同 concrete static candidate 已由非解析器 contribution 安装，则在
   mutation 前拒绝运行，避免 Batfish `StaticRouteHelper` 的“route 已在 RIB”规则造成虚假自激活。

### 新增回归测试

- 逆序 recursive static chain 在同步轮次下收敛到相同 guard。
- 首次解析成功后撤回 connected support，再次解析必须得到 false，证明不会继承 stale static。
- blue/red VRF 使用相同 caller message ID 时分别得到各自 connected guard。
- batch 中后置非法 route 必须在第一条 route 安装前失败，RIB 不出现部分写入。
- 外部 contribution 预装相同 recursive static candidate 时必须拒绝，且原 RIB 不变。
- 原有 symbolic LPM 全赋值 differential test 与 longer-prefix blocker test 继续通过。

### 验证与版本

- `//projects/minesweeper:minesweeper_tests`：通过。
- `//projects/minesweeper:minesweeper_tests_pmd`：通过。
- `git diff --check`：通过。
- 未修改 `Graph`、`Encoder`、`EncoderSlice`、`PropertyChecker`。
- correction 实现提交：`35d8507a95`
- 实现/审计更新时间：2026-08-25 21:56 CST
- 回退 correction：`git revert 35d8507a95`

## Stage 4.3：Batfish Routing Policy 与 Redistribution 生命周期（2026-08-25 22:10 CST）

### 4.3a：精确策略执行

- `BatfishRoutingPolicyProcessor` 从目标 `Configuration.getRoutingPolicies()` 查找 policy，并
  直接调用 Batfish `RoutingPolicy.process(input, outputBuilder, direction)`；Minesweeper 不复制
  prefix/community/protocol match、statement control flow 或 attribute transformation。
- protocol-specific output builder 由调用方提供。公共层不猜测 OSPF external metric type、
  IS-IS level/system-id 或 BGP session attributes；这些 builder 必须由后续协议 adapter 使用
  Batfish 对应 helper 初始化。
- `BatfishRoutingPolicyResult` 明确区分 `ACCEPTED`、`DENIED`、`POLICY_NOT_FOUND`。只有
  ACCEPTED 携带强类型 `AnnotatedRoute<R>`；target VRF 在 policy boundary 明确标注。

### 4.3b：显式 Redistribution 状态迁移

- `BatfishRedistributionKey` 将 source message、router、source/target VRF、source/target
  protocol 和 policy name 共同纳入逻辑 identity，避免跨 VRF、协议或 policy 相互覆盖。
- `BatfishRedistributionReconciler` 将 policy outcome 映射到 Stage 3.4 生命周期：
  - 首次 ACCEPT：普通 advertisement；
  - concrete route 不变、guard 改变：复用 contribution identity 更新 availability；
  - transformed concrete route 改变：提升 generation，使用新 identity 调用原子 `replace`；
  - DENIED 或 POLICY_NOT_FOUND：撤回已有 contribution 及传播后代；
  - target VRF 或 target protocol 不匹配：mutation 前拒绝，保留旧 contribution。
- 本阶段只实现公共 policy/redistribution 边界，不自行构造 OSPF、IS-IS 或 BGP route。
  Stage 4.4 协议 adapter 将调用 Batfish protocol helper 创建相应 output builder/route，再把
  结果交给本阶段 reconciler。

### 测试与验证

- direct `RoutingPolicy.process` 与 processor 的 permit + `SetMetric` 输出逐项相等。
- DENY 与 policy missing 被区分，且均不产生 output route。
- guard-only 更新保持 contribution identity，并替换 availability guard。
- transformed route 改变触发 withdrawal + 新 identity，RIB 只保留新 route。
- ACCEPT 后 DENY 会撤回 contribution。
- 错误 target VRF 在 replacement 前被拒绝，旧 identity 和 route 保持不变。
- `//projects/minesweeper:minesweeper_tests`：通过。
- `//projects/minesweeper:minesweeper_tests_pmd`：通过。
- 主源码 PMD 仅报告既有 34 条 tolerance/SMT 基线违规，Stage 4.3 文件无命中。
- `git diff --check`：通过。
- 未修改 `Graph`、`Encoder`、`EncoderSlice`、`PropertyChecker`。
- 实现提交：`1c4a7e8191`
- 实现/审计更新时间：2026-08-25 22:10 CST
- 回退：`git revert 1c4a7e8191`

## Stage 4.3 测试补强与 BGP 边界澄清（2026-08-25 22:21 CST）

- 增加“policy 先修改 output builder、随后 reject”：结果必须为 DENIED、不得返回 transformed
  route，原始 `AnnotatedRoute<StaticRoute>` 及 metric 必须保持不变。
- 增加 `Direction.IN` 差分测试，processor 输出与直接调用 Batfish `RoutingPolicy.process`
  完全相等；原有 OUT 测试继续保留。
- 增加 static policy → `BatfishRedistributionReconciler` → guarded main RIB 的端到端测试，
  验证 transformed metric 和 symbolic availability guard 同时进入稳定 candidate。
- 明确不加入 BGP policy 测试：当前只完成 connected/static 与公共 policy/redistribution
  boundary，尚未实现 BGP session adapter、pre-export/post-export transformations、BGP
  propagation 和 BGP RIB。单独调用 `processBgpRoute` 只能测试 Batfish 自身，不能证明论文
  symbolic ingress/export 环节，故复杂 BGP policy 测试推迟到 BGP adapter 阶段。
- 当前 Stage 4.3 覆盖的是 static/connected 可合法使用的 policy execution 和 symbolic
  lifecycle；不宣称已经支持 BGP、OSPF 或 IS-IS。
- 完整 Minesweeper tests 与 test PMD：通过。
- 测试补强提交：`aab08cc93e`
- 更新时间：2026-08-25 22:21 CST
- 回退：`git revert aab08cc93e`

## Stage 4.4：Batfish-backed IPv4 BGP 基础 Pipeline（2026-08-25 22:37 CST）

### 实现

- `BatfishBgpRedistribution` 直接复用 `BgpProtocolHelper.convertNonBgpRouteToBgpRoute` 和
  Batfish `RoutingPolicy.processBgpRoute`，将 connected/static main-RIB route 转为本地 BGP。
- `BatfishBgpProtocolAdapter` 使用 `AnnotatedRoute<Bgpv4Route>` 保留 VRF，不使用裸 BGP route
  猜测 VRF；candidate key 按 receiver、source VRF 和完整 transformed route 构造。
- directed BGP edge 分别保存 export 方向所需的反向/incoming session properties 与 receiver
  import 方向的 session properties，避免把 head/tail AS/IP 方向混用。
- export 顺序直接复用 Batfish：`transformBgpRoutePreExport` → export policy →
  `transformBgpRoutePostExport`；import 顺序为 `transformBgpRouteOnImport` → import policy。
- BGP candidate preference 委托 `Bgpv4Rib.comparePreference`；symbolic comparator 只转换正负号。
- session endpoint 与 sender VRF 均显式校验，防止跨 session/VRF 静默传播。

### 测试与范围

- connected route 经 Batfish non-BGP conversion 后保留 `srcProtocol=CONNECTED` 和 target VRF。
- static → redistribution policy → local BGP → eBGP export/import → receiver guarded BGP RIB
  端到端通过；接收 guard 等价于 `sourceGuard AND linkGuard`，AS path 包含发送 AS。
- BGP preference comparator 与 Batfish `Bgpv4Rib.comparePreference` 差分一致。
- 完整 Minesweeper tests 与 test PMD：通过。
- 主源码 PMD 仍只有既有 34 条 tolerance/SMT 基线违规，新文件无命中。
- 未修改 `Graph`、`Encoder`、`EncoderSlice`、`PropertyChecker`。
- OSPF、IS-IS、Segment Routing 仅创建 TODO 文档，明确未实现，未加入占位协议逻辑。

### 尚未宣称完成的 BGP 能力

iBGP/route reflection、multipath/add-path、guard-dependent IGP-cost tie-break、confederation 和
动态 session replacement 尚需独立验收。特别是 concrete null-main-RIB `Bgpv4Rib` 不能代表
条件化 IGP cost；后续必须基于 guarded IGP state 提升该比较，不能用 concrete dataplane 代替。

- 基础实现提交：`374d7c3309`
- 更新时间：2026-08-25 22:37 CST
- 回退：`git revert 374d7c3309`

## Stage 4.4 审计修正：BGP advertisement identity 与 preference oracle（2026-08-26 11:14 CST）

### Identity 修正

- 删除 `exportedRoute.toString()` message ID。该字符串不是协议身份，无法隔离并行 session，
  也不能为 route replacement 保留可撤回的旧 identity。
- adapter 现在按 `sessionId + sender SymbolicRouteKey` 分配稳定、不透明的 candidate token；
  network factory 再使用无歧义的长度前缀给 token 加 session namespace。
- 同一 session/candidate 的 guard-only 重放复用 identity；transformed concrete route 改变会
  产生新 candidate identity，旧 contribution 由 Stage 3.4 dependency/replace 生命周期撤回。
- 不同父 contribution 产生相同 concrete candidate 时不错误丢失父关系：RIB 对 availability
  做 OR 聚合，但 contribution ID 与 dependency parent set 仍分别保存。

### Preference oracle 修正

- 删除全局、固定 `ROUTER_ID` 且 main RIB 为 null 的共享 `Bgpv4Rib`。
- 为每个 router/VRF 建立 Batfish `Bgpv4Rib` oracle，读取对应 `BgpProcess` 的 tie-break、
  eBGP/iBGP multipath、AS-path equivalence mode、cluster-list-as-IGP-cost，并使用调用方提供的
  该 VRF concrete main RIB 计算 next-hop IGP cost。
- 缺失 router/VRF main RIB 或跨 VRF comparison 立即拒绝，不静默退回近似比较。
- 范围边界：该 oracle 对固定 concrete underlay 精确；若 IGP reachability/cost 本身带 guard，
  后续必须实现 guarded preference lifting，不能以单一 concrete main RIB 代替 symbolic 语义。

### 定向验证

- 同一 candidate 重试 identity 稳定，identity 不包含 route 字符串。
- route attribute 改变得到新 identity，避免覆盖旧 advertisement 的撤回句柄。
- 同一 candidate 在一个固定快照内若产生不同 export route 会立即拒绝，要求调用方走原子
  route replacement；不会复用旧 ID 或遗留旧传播后代。
- receiver `b/default` 的两个 next hop 使用不同 main-RIB IGP metric；symbolic comparator 与
  用同一 receiver `BgpProcess`、同一 VRF main RIB 构造的 Batfish `Bgpv4Rib` 差分一致。
- 完整 `//projects/minesweeper:minesweeper_tests`：通过。
- `//projects/minesweeper:minesweeper_tests_pmd`：通过。
- 主源码 PMD 仍失败于既有 34 条 Graph/tolerance/SMT 基线违规；本轮 symbolicroute 文件无命中。
- `git diff --check`：通过。
- 未修改 `Graph`、`Encoder`、`EncoderSlice`、`PropertyChecker`。
- 最终验证更新时间：2026-08-26 11:19 CST。

## Stage 4.5：一次运行得到全网 Guarded RIB（2026-08-26 11:39 CST）

### Pipeline

- 新增 `BatfishSymbolicRoutePipeline.run(input)`，一次调用依次完成 main-RIB seed 收敛、
  recursive static fixed point、connected/static redistribution、本地 BGP origination 和 directed
  IPv4 eBGP 全网收敛。
- main RIB 与 BGP RIB 保持两个协议语义正确的 stable plane，不用一个错误的 comparator 混合；
  `BatfishSymbolicRoutePipelineResult` 将两者统一呈现为全网结果。
- redistribution 只接受当前已验收的 connected/static source，并直接复用
  `BatfishBgpRedistribution` 的 Batfish conversion 与 routing policy。
- pipeline 在运行前验证 configuration hostname、concrete router/VRF main RIB、edge/session
  一一对应、session endpoint、redistribution rule identity 和 route 所属 router，避免部分运行后
  才发现输入拓扑不一致。

### 输出

- `getAllRoutes()` 返回确定顺序的全部 main/BGP guarded candidates。
- `getRoutesByRouterAndVrf()` 返回 `router -> VRF -> entries`。
- 输出以全部输入 configuration 的 router/VRF 为骨架；没有任何 route 的 VRF 也保留空数组，
  因此不会从报告中消失。
- `toJson()` 使用 Batfish JSON mapper 产生 pretty JSON。
- 每条记录包括 plane、router、VRF、prefix、protocol、next hop、concrete route、
  availabilityGuard、selectionGuard、contribution IDs 和 router path。
- route 的字符串只用于人类可读报告，绝不参与 message/contribution identity。

### 测试

- 两路由器端到端：guarded connected 激活 recursive static，两者经 Batfish redistribution
  进入本地 BGP，再经过带 guard 的 eBGP session 到接收端。
- 最终得到 6 条记录：发送端 main RIB 2 条、发送端 BGP RIB 2 条、接收端 BGP RIB 2 条。
- recursive static 在接收端的 availability guard 等价于
  `connected_enabled AND static_enabled AND a_b_session`。
- 验证 router/VRF 分组、JSON guard 字段和 provenance router path。
- 增加无路由的第三台设备，验证其 default VRF 仍以空 RIB 出现在结果中。
- edge/session 不匹配在收敛开始前拒绝。
- 完整 Minesweeper tests：246 个测试通过。
- test PMD：通过。
- 主源码 PMD 仍只有既有 34 条 Graph/tolerance/SMT 基线违规；Stage 4.5 文件无命中。
- `git diff --check`：通过。
- 未修改 `Graph`、`Encoder`、`EncoderSlice`、`PropertyChecker`。

### 下一输入适配层

当前完成的是 typed normalized pipeline。等配置格式和 guard 命名/赋值规则确认后，再接入
“上传配置目录 -> Batfish parse/convert -> 自动生成 seeds/edges/sessions -> pipeline -> JSON”入口；
在此之前不猜测配置 guard，也不静默把未验收的 iBGP、OSPF、IS-IS 或 SR 当作已支持。

## Stage 4.5 论文对齐审计与 tolerance 四路由器实例（2026-08-26 12:03 CST）

### HoYAN / YU / tolerance Symbolic RIB 审计

- 逐项复核 HoYAN §5.3–5.4、Algorithm 1，YU §4.1/§4.4，以及 tolerance Step 2/Figure 4。
- `availabilityGuard` 对应候选 route 存在条件；`selectionGuard` 对应排除所有严格更优候选后
  的最终 selected branch。tolerance symbolic route 必须使用后者。
- ingress、normal preference、egress、link conjunction、equal-preference OR、propagation tree、
  late-higher-priority correction、recursive withdrawal 和无新 semantic delta 收敛均已对齐。
- 当前不支持 route aggregation、iBGP、IS-IS/OSPF、SR。`k`-failure pruning 尚未实现，但它是
  完整 SRIB 上的可选 bounded-domain 后处理，不影响未剪枝 SRIB 的语义正确性。
- 完整矩阵记录于 `PAPER_ALIGNMENT.md`。

### parser 驱动的论文实例

- 配置位于 `networks/tolerance-symbolic-route/configs`，而非 Minesweeper 私有 example 目录。
- 测试使用 `BatfishTestUtils.getBatfishFromTestrigText`，实际经过 Cisco parser 与
  vendor-independent conversion；pipeline 消费解析得到的 interface、connected route、
  BGP process、peer 和 routing policy 对象。
- 论文 prefix `P` 实例化为 `10.0.0.0/24`；`a1...a5` 分别对应 R1-R2、R1-R4、R1-R3、
  R2-R4、R3-R4 五条链路。
- R4 parser 输出的三个 import policies 分别设置 local preference 200、100、50。
- pipeline 实际得到 R4 三条 BGP candidates，其 selection guards 为：
  - R1-R2-R4：`a1 AND a4`；
  - R1-R4：`a2 AND NOT(a1 AND a4)`；
  - R1-R3-R4：`a3 AND a5 AND NOT(a2) AND NOT(a1 AND a4)`。
- 三者与 tolerance Figure 4 的 `g2`、`g1`、`g3` 逻辑等价；三条均在 `k=1` 域内可满足，
  因而本例加入 `k=1` pruning 也不会删除任何一条。

### 查询与防漏边界

- 新增精确 `getRoutes(router, vrf)`；已配置但为空的 RIB 返回空列表，未知 router/VRF 拒绝。
- redistribution policy 缺失现在抛出异常，不再与合法 policy DENY 一样静默跳过。
- 新增 missing policy、missing concrete main-RIB context、unmatched edge/session 测试。
- parser 集成测试断言 R4 恰有三条 BGP route、全网恰有六条 BGP route，并逐条对 guard 做
  Z3 逻辑等价检查，避免仅比较字符串而漏路由。
- 完整 Minesweeper tests：249 个测试通过；test PMD 通过。
- 主源码 PMD 仍仅报告既有 34 条 Graph/tolerance/SMT 基线违规，本轮文件无命中。
- `git diff --check`：通过；未修改 `Graph`、`Encoder`、`EncoderSlice`、`PropertyChecker`。
- 最终验证时间：2026-08-26 12:05 CST。

## Stage 4.5 可审计结果导出（2026-08-26 12:10 CST）

- 新增 `BatfishSymbolicRoutePipelineResult.toReadableText()`，按 router/VRF 输出适合人工审阅的
  deterministic 文本，同时保留空 VRF。
- 精简记录保留 plane、prefix、protocol、next hop、availability guard、selection guard 和
  router path；不暴露用于内部撤回的冗长 contribution identity。
- 新增 `tools/generate_tolerance_symbolic_rib.sh`：真实运行 Batfish parser integration test，
  只有全部断言通过后才提取本次 pipeline 的结果。
- 最终结果遵循既有 SMT 输出惯例，写入本次 reachability 分析动态创建的
  `smts/smt_output_XXXX/0_symbolic_routes.txt`，在一个文件中按 R1--R4 分类；该文件由运行
  结果生成，不是手写 expected output。
- `networks/tolerance-symbolic-route` 只保留 Batfish snapshot 的 `configs/*.cfg`；Bazel
  filegroup 位于顶层 `networks/BUILD`，脚本、expected output、guard metadata 和结果均不再
  混放在网络配置目录。
- 脚本失败时打印完整 Bazel 日志，避免命令无输出而无法定位。

## Stage 4.5 topology guard 与平面输出修正（2026-08-26 12:31 CST）

- 删除 tolerance integration test 中逐条手写的 `putLink(..., "aN", ...)`。
- 新增 `BatfishTopologyGuardInitializer`，从 Batfish parser 生成的 configuration/interface
  address 自动按共享 L3 prefix 发现链路端点；普通点到点 guard 使用排序后的设备名，例如
  `r1_r4`，双向接口共享同一 guard。
- topology guard 使用方向无关的强类型 `LinkFailureKey`。由于当前 Encoder 将内部链路按设备对
  合并，现阶段对并行链路和多接入网段显式拒绝，避免生成无法映射到 SMT failure variable 的
  虚假独立 guard。
- Symbolic RIB 改为与既有 `0_data_plane.txt` 相同的一行一路由平面表格，列为 Node、VRF、
  Network、RIB、Protocol、NextHopIP、NextHopInterface、AvailabilityGuard、SelectionGuard、Path。
- NextHopIP/NextHopInterface 从 Batfish typed `NextHopIp`/`NextHopInterface` 提取，不解析
  `toString()`。
- parser-backed pipeline 与结果生成通过；test PMD 通过。main PMD 仍只包含既有 34 条
  Graph/tolerance/SMT baseline，新增 symbolic-route 文件无命中。

## Stage 4.5 reachability 输出生命周期接入（2026-08-26 12:49 CST）

- 修正固定输出 `smt_output_0024` 的临时实现。`SmtReachabilityTest.setup()` 仍是唯一调用
  `Encoder.createOutputDirectory()` 的 owner，并通过 `SMT_OUTPUT_DIRECTORY=<path>` 公布本次
  实际目录；未修改 `Encoder` 的既有创建/搜索逻辑。
- `SmtReachabilityTest.setup()` 在同一个 Batfish 实例完成 concrete dataplane 后直接调用
  parser-backed symbolic pipeline，并向本次目录写入 `0_symbolic_routes.txt`；不需要运行任何
  第二命令。`tools/generate_tolerance_symbolic_rib.sh` 现在只是该 Bazel 测试命令的可选包装。
- 新增 `BatfishParsedSnapshotPipelineInputBuilder`，从 parsed configurations、concrete main
  RIB 和 Batfish BGP topology 自动建立 connected seeds、双向 eBGP edges/sessions 与 link
  guards；测试不再复制手工 edge 列表。
- reachability 问题设置为 ingress `r1`、final node `r4`、destination `192.0.14.2/32`。选择
  R4 的实际接口地址是为了让 Batfish destination-location 语义确实落在 R4；论文路由前缀
  `10.0.0.0/24` 仍用于 Symbolic RIB 的三候选优先级验证。
- 仅直接运行 `SmtReachabilityTest#testReachability`，实际自动创建 `smts/smt_output_0026`，
  其中同时存在 SMT encoding、concrete data plane、
  BGP routes、question metadata 和 `0_symbolic_routes.txt`；reachability assertion 与 symbolic
  guard assertions 均通过。
- `//projects/minesweeper:minesweeper_tests_pmd` 通过。allinone test PMD 仍命中原有 11 条
  SmtReachability/Fat4/Sp4 baseline（unused imports/fields 与 parameter reassignment），本次新增
  代码无命中。

## Stage 5.1 统一 failure identity：第一步（2026-08-26 13:18 CST）

- 新增方向无关的 `LinkFailureKey(firstRouter, secondRouter)`；`r1→r4` 与 `r4→r1` 在 equals、
  hashCode 和排序语义上完全相同，`r1_r4` 仅作为人类可读名称，业务逻辑不解析该字符串。
- `BatfishTopologyGuardInitializer` 改为先生成 `LinkFailureKey`，再创建显示用 guard variable；
  删除以前为并行链路附加 subnet、但无法对应 Encoder failure variable 的错误策略。
- 明确发现 Encoder 当前的关键边界：内部链路 failure 是 `Int 0/1` 且按 router pair 合并；
  symbolic-route guard 是 link-aliveness Boolean。当前 Symbolic RIB 阶段只要求 canonical
  identity、统一 up/down 极性与 failure counting，并让 connected、BGP session、forwarding edge
  引用同一 key；guard 编译到 Minesweeper BoolExpr 属于 tolerance Step 3。
- 新增 identity 正反向等价与 self-link 拒绝测试；与 parser-backed tolerance pipeline 一起通过。

### 论文范围纠正（2026-08-26 13:27 CST）

- 重读 tolerance Step 2、Step 3 与 Figure 5：Step 1 的 per-device SMT encoding 和 Step 2 的
  symbolic-route analysis 明确由 separate tools/models 产生，论文不要求共享 Z3 Context。
- Step 2 当前必须完成：canonical link identity；aliveness=true/up 与 failure=not(aliveness) 的
  统一极性；failure budget 按 down components 计数；connected seed、BGP session 和 forwarding
  edge 使用同一 `LinkFailureKey`；以及 k-failure pruning。
- guard 编译进 Minesweeper BoolExpr、seed encoding 和 consistency condition 属于 Step 3，延后
  实现。当前验收目标恢复为“正确生成经过 k-failure pruning 的 Symbolic RIB”。

## Stage 5.1 canonical link identity 贯通（2026-08-26 13:28 CST）

- 新增 `TopologyLinkGuards`，集中保存 `hostname:interface -> LinkFailureKey` 与
  `LinkFailureKey -> aliveness RouteGuard`，避免 connected 和 BGP 各自重新推导 link identity。
- `SymbolicRouteSeed` 与 `SymbolicRouteSession` 可显式携带 `LinkFailureKey`；parsed snapshot
  builder 对 connected seed 和对应 eBGP session 注入同一个对象，并拒绝 session endpoints 与
  key 不匹配。
- 新增 `MinesweeperLinkFailureKeys.fromGraphEdge`，正反向 internal forwarding edges 均映射到
  相同的方向无关 key；external/null-peer 与 abstract edge 不伪造 internal-link identity。
- 新增 `LinkAvailabilityAssignment`，唯一极性为 `true=up`、`false=failed`，failure count 只统计
  false 值，负数 budget 显式拒绝。
- 并行链路和多接入网段继续 fail closed，因为当前 Minesweeper failure model 无法为它们提供
  一一对应的 component identity。
- identity、seed/session 共享、forward/reverse GraphEdge、up/down counting 与 parser pipeline
  测试通过；直接运行 `SmtReachabilityTest` 生成 `smt_output_0027/0_symbolic_routes.txt`。
- 下一项仅为 Step 2 的 k-failure pruning；不进行 guard-to-Encoder 编译或 consistency condition。

## Stage 5.1 parser-driven canonical identity 端到端断言（2026-08-26 13:50 CST）

- `ToleranceFourRouterParsedPipelineTest` 删除手工 connected seed 和单向 BGP edge 构造，改为从
  同一组四台路由器配置经 Batfish parser、concrete dataplane 和 Batfish BGP topology 构建
  `BatfishParsedSnapshotPipelineInputBuilder` 输入，并将该输入直接交给 symbolic-route pipeline。
- 对拓扑中全部 5 条物理链路逐条执行非空洞的双向断言：两端 connected seed、正反向
  BGP session、正反向 Minesweeper forwarding edge 必须映射到同一个方向无关
  `LinkFailureKey`。断言直接比较强类型 key，不解析 guard name 或 `toString()`。
- parser 生成的 BGP topology 是双向的，因此全网 BGP symbolic candidates 为 10，取代了旧手工
  单向模型的 6；R4 对论文前缀仍精确产生 3 个候选，local-preference 和 selection guard
  断言保持通过。
- `ToleranceFourRouterParsedPipelineTest` 与 `//projects/minesweeper:minesweeper_tests_pmd` 通过；
  `git diff --check` 通过。本次未修改 `Graph`、`Encoder`、`EncoderSlice` 或 `PropertyChecker`。
- 该断言完成 parser-driven canonical identity 的集成验收；Tolerance Step 2 的剩余工作仍是
  k-failure pruning。

## Stage 5.2 MAIN RIB 协议汇总与 BGP 本地起源 next-hop 修正（2026-08-26 14:26 CST）

- 修正 pipeline 中 MAIN 与 BGP 相互独立的语义错误：BGP Loc-RIB 收敛后，将每个可路由的
  BGP selected candidate 及其 selection guard 安装到 protocol-neutral MAIN RIB，再由
  `BatfishMainRibRouteAdapter`/Batfish `Rib.comparePreference` 执行跨协议优先级选择。
- 与 Batfish `BgpRoutingProcess.redistributeRouteToLocalRib` 对齐：重分发生成的本地 BGP route
  继承 source route 的 next-hop，并标记 `nonRouting=true`，防止重新灌入 MAIN。删除
  `BatfishBgpRedistributionRule` 中人工指定的 next-hop IP；R1 本地起源 BGP route 现显示
  `NextHopIP=-`，不再错误使用 `192.0.12.1`。
- `0_symbolic_routes.txt` 改为两个明确分区：首先输出 `MAIN RIB (cross-protocol forwarding
  candidates)`，其下输出 `BGP LOC-RIB (protocol detail)`；删除每行重复的 RIB 列，并将
  Z3 guard 规整为单行文本。
- 四路由器 parser-driven 测试新增断言：R4 MAIN 含三个 BGP 条件候选，它们在
  MAIN 中的 selection guard 与论文三档 local-preference 条件逻辑等价；R1 本地 BGP
  `NextHopIP` 为 `-`。
- symbolic-route 定向测试、test PMD 及真实 `SmtReachabilityTest#testReachability` 通过，
  生成 `smts/smt_output_0029/0_symbolic_routes.txt`。主源码 PMD 仍只报告已记录的
  Graph/Encoder/EncoderSlice/PropertyChecker 等 34 条基线违规，本次文件无新命中。

### Symbolic guard 展示层简化（2026-08-26 14:29 CST）

- 内部 `SymbolicRoute` 和 `GuardedRibEntry` 继续保留原始 `RouteGuard` 对象，不修改传播、
  withdrawal、逻辑等价或可满足性判定所使用的 symbolic state。
- 仅在构建展示用 `SymbolicRibRecord` 时，分别对 availability guard 和 selection guard
  调用 `RouteGuard.simplify()`；Z3-backed guard 因此调用 Z3 `BoolExpr.simplify()`。JSON 与 txt
  共用该简化视图，txt 另将空白规整为单行。
- parser pipeline、test PMD 和 `SmtReachabilityTest#testReachability` 通过，生成
  `smts/smt_output_0031/0_symbolic_routes.txt`；`git diff --check` 通过。

### 原始 guard 与增强化简结果分离（2026-08-26 14:40 CST）

- 说明 R2/R3 旧展示未充分化简的原因：Z3 `BoolExpr.simplify()` 只执行局部语法化简，
  不会系统利用整个合取上下文消除循环/备选路径 selection condition 中的冗余项。
- 新增 `RouteGuard.simplifyForDisplay()`；Z3 实现使用 `simplify -> ctx-solver-simplify ->
  propagate-values -> simplify` tactic pipeline。该方法只由报告视图调用，不取代内部
  guard，也不参与 convergence、withdrawal 或优先级计算。
- `SmtReachabilityTest` 现在同时生成 `0_symbolic_routes_init.txt`（stable RIB 中的原始
  guard 文本）与 `0_symbolic_routes.txt`（逻辑等价的增强化简展示）。
- 实际输出为 `smts/smt_output_0032`；化简文件由 6840 bytes 降为 6380 bytes。例如
  R2 经 R4 的 guard 从 `(and r1_r4 (not (and r1_r2 r2_r4)) r2_r4)` 化简为
  `(and r1_r4 (not r1_r2) r2_r4)`。
- 四路由器端到端测试对 MAIN availability 和 BGP selection guard 逐项验证原始式与
  `simplifyForDisplay()` 结果逻辑等价，并验证原始文件保留 `let` 表达式、化简文件
  消除该中间结构；定向测试与 test PMD 通过。

## Stage 5.2 全局队列统一与 redistribution 边界记录（2026-08-26 16:14 CST）

- 删除早期单 ingress 组件队列 `SymbolicRouteWorkQueue`，并从
  `SymbolicRouteIngressProcessor` 删除内部 `process(Iterable)` 调度循环和
  `isQueueEmpty()`。Ingress processor 现在只提供 `prepare/install/processMessage` 原子操作。
- advertisement 和 withdrawal 的唯一生产调度器现为
  `SymbolicRouteConvergenceEngine` 中的全局 FIFO `Queue<SymbolicRouteWorkItem>`，避免局部队列
  与全局队列并存导致算法归属不清。
- 原 ingress FIFO 单元测试迁移为 convergence-engine 测试
  `testGlobalQueueProcessesInitialAdvertisementsInFifoOrder`，直接验证实际生产队列的顺序；
  ingress policy、transformation、equivalent replay 和输入边界测试改为调用原子 API。
- 在 `PROTOCOL_PIPELINE.md` 记录双 redistribution 路径：当前 fixed-snapshot 生产 pipeline
  使用 `BatfishBgpRedistribution` 构建初始 BGP seeds；`BatfishRoutingPolicyProcessor` +
  `BatfishRedistributionKey` + `BatfishRedistributionReconciler` 是已测试但尚未接入主路径的
  incremental lifecycle。在开放增量配置/策略更新前，必须统一两者的 conversion/policy
  语义，避免 next-hop、`nonRouting` 和 missing-policy 行为漂移。
- convergence、ingress、pipeline、parser-driven tolerance 定向测试和 test PMD 全部通过；
  主源码由 177 个减少为 176 个 Java 文件，`git diff --check` 通过。

## Stage 5.2 代码组织整理：唯一 owner 辅助类内嵌（2026-08-28 15:33 CST）

- 确立整理规则：独立的 public 模型、扩展点和生命周期类保持一文件一 public type；
  只有单一 owner 的 package-private helper/DTO 内嵌到 owner，避免同时出现过多小文件和
  不必要的巨型文件。
- 删除顶层 `SymbolicRouteWorkItem.java`，收敛为
  `SymbolicRouteConvergenceEngine.WorkItem`。该类改为 private nested type，只有全局 engine
  能创建和解释 advertisement/withdrawal 事件。
- 删除顶层 `SymbolicRouteIngressCandidate.java`，收敛为
  `SymbolicRouteIngressProcessor.PreparedCandidate`。简化名称的同时保留 package-private 可见性，
  使 convergence engine 仍可在 RIB 写入前检查 contribution-to-candidate identity。
- 新增 `CODE_ORGANIZATION.md`，记录命名规则、必须保留的公开类、逻辑分组、未来
  `guard/rib/engine/batfish/pipeline` 子包边界，以及新增文件的准入条件。子包物理迁移
  延后到独立机械性 commit，不与 route semantics 修改混合。
- 公开类保留 `SymbolicRoute` 前缀以表达 engine API 所有权，Batfish-backed 类保留
  `Batfish` 前缀以区分具体协议语义和协议无关核心；内部 helper 使用 owner 语境下的
  简称。
- symbolicroute 生产文件数由 50 减少为 48；engine、ingress、network factory、pipeline、
  parser-driven tolerance 定向测试和 test PMD 通过，`git diff --check` 通过。

## Stage 6.1 HoYAN Algorithm 2：IS-IS L1 符号传播（2026-08-29 16:29 CST）

- 新增 `BatfishIsisTopologyAdapter`，从 Batfish `IsisTopology`/`IsisEdge` 和规范化配置构建
  L1 directed sessions 与接口路由 seed；不解析配置字符串，不使用 `toString()` 作为身份。
- 新增 `BatfishIsisEdge` 保存 parser-derived edge、端点配置和接口；symbolic session、active
  接口 seed 与 forwarding/connected 语义共同引用 topology-derived `LinkFailureKey`。active
  接口前缀使用链路 aliveness guard，passive 接口前缀使用 `true`。
- 新增 `BatfishIsisProtocolAdapter`：按照 Batfish `VirtualRouter.propagateIsisRoutes` 在接收侧
  累加接口 cost、设置邻居 next-hop 和管理距离；使用 `IsisRib.routePreferenceComparator`
  进行 metric/level 优选；使用 provenance 拒绝重复路由器路径；固定快照内使用稳定的
  session/candidate message identity。
- 顶层 pipeline 在 connected/static 初始化后收敛独立 `ISIS_L1` guarded RIB，将其 selected
  candidates 及 selection guard 安装到 MAIN，然后继续已有 BGP pipeline。结果 API、JSON 和
  readable txt 增加 `ISIS_L1` plane 与 `IS-IS LEVEL-1 RIB` 分区。
- `BatfishIsisAlgorithm2Test` 使用五路由拓扑验证 parser-normalized adjacency、14 条 directed
  edge 的 canonical identity、20/30/40 三层 metric、两条 30-cost ECMP、逐层 failure
  fallback guard、active-interface origin guard、origin recursive withdrawal、MAIN 安装和输出。
- IS-IS 定向测试及完整既有 Minesweeper 测试通过。主源码 PMD 没有新增 symbolicroute
  命中，仍只因 Graph/Encoder/EncoderSlice/PropertyChecker 等已记录基线违规失败。
- Stage 6.1 明确不声称支持 L2、L1/L2 leaking、overload/attach/down、redistribution、broadcast
  pseudonode、iBGP-over-IS-IS、SR 或 k-failure pruning；后续边界记录于 `ISIS_TODO.md`。

## Stage 6.2 IS-IS L2 与 L1/L2 guarded transition（2026-08-29 17:28 CST）

- `BatfishIsisTopologyAdapter.Result` 扩展为 level-separated inputs：保留兼容的 L1 getter，
  新增 L2 edges/sessions/seeds；同一物理线路的 L1、L2 session 使用不同稳定 session ID，但
  共同引用同一个 topology-derived `LinkFailureKey`。
- `BatfishIsisProtocolAdapter` 改为 one-level-per-instance，L1/L2 均复用 Batfish 接收侧 cost、
  管理距离、next-hop 和 `IsisRib.routePreferenceComparator`，拒绝 LEVEL_1_2 混合 RIB。
- pipeline 先收敛 `ISIS_L1`，再在非 overload 的 L1/L2 router 上调用 Batfish
  `IsisProtocolHelper.convertRouteLevel1ToLevel2()`；转换后的稳定 contribution 继承原 L1
  `selectionGuard`，随后与原生 L2 seeds 一起收敛独立 `ISIS_L2` RIB。
- 实现 Batfish-compatible attached default：L1/L2 router 向 L1 宣告 attach default；L1-only
  邻居可将其装入 MAIN，L1/L2 起源设备的 MAIN 和整个 L2 RIB 均拒绝该 route。Batfish helper
  同时拒绝 attach/down route 的 L1→L2 upgrade。
- 输出 API、JSON/readable txt 增加 `ISIS_L2` plane、network、convergence result 和独立表格；
  L1/L2 selected candidates 分别通过 Batfish MAIN RIB comparator 参与跨协议选择。
- 新增 `BatfishIsisLevel2PipelineTest`：验证 L1-only→L1/L2→L2-only parser-normalized 拓扑、
  跨 level guard、L2 metric、attached 边界、MAIN 安装，以及 L2 三档 metric/ECMP。
- 对尚未实现的 overload、export policy/generated route、非 point-to-point circuit 显式
  fail closed，避免生成表面成功但协议语义不完整的 RIB。
- 当前 level transition 是 fixed-snapshot orchestration；如果调用者在返回结果后增量撤回
  L1 contribution，尚不会自动跨层 reconcile L2 contribution，必须重新运行完整 pipeline。
  固定配置 symbolic RIB 不受此限制，增量生命周期留到 Stage 6.3。

## Stage 6.3 L1/L2 持续动态生命周期（2026-08-29 17:53 CST）

- `SymbolicRouteConvergenceEngine` 新增同步 stable-state listener：只有全局 advertisement/
  withdrawal FIFO 完全清空后才触发，确保跨层 consumer 读取的是语义稳定的 Guarded RIB，
  而不是中间状态。
- 新增 `BatfishIsisLevelTransitionReconciler`，维护稳定的 L1 `SymbolicRouteKey` → L2
  contribution identity 映射及 active registry；每次 reconcile 对最终 L1 selected branches
  做语义 diff，而不是依赖对象相等或 route 字符串。
- L1 candidate 消失或失去可满足 selection guard 时，reconciler 调用 L2 engine withdrawal，
  由既有 propagation dependency tree 递归删除所有 L2 descendants；guard 逻辑变化使用同一
  contribution identity 更新；concrete route replacement 则撤回旧 candidate 后加入新 identity。
- pipeline 改为先收敛 native L2 state，再注册 reconciler 并收敛 L1；初始运行和返回后的
  `L1 engine.withdraw/converge/replace` 均会在返回前自动推动 L2 到稳定状态，不再需要重跑
  整个 pipeline。
- `BatfishSymbolicRoutePipelineResult` 暴露 level-transition reconciler，便于审计 active
  transition 数量和最近一次 L2 convergence 统计。
- `BatfishIsisLevel2PipelineTest` 新增动态生命周期验收：L1 origin withdrawal 自动删除远端
  L2 route；同 contribution guard 更新改变完整跨层 guard；route replacement 撤回旧 L2
  candidate 并以新 metric 重建传播结果。
- 能力边界：本阶段只完成 L1→L2 transition lifecycle。L1/L2 变化之后，已经一次性安装的
  MAIN/BGP 等下游 plane 仍未动态 reconcile；需要查看跨协议动态结果时仍应完整重跑 pipeline，
  后续由通用 protocol-to-MAIN reconciler 解决。

## Stage 6.4 protocol-to-MAIN 持续 reconciliation（2026-08-29 18:06 CST）

- 新增 `BatfishMainRibReconciler`，统一替换 pipeline 中一次性的 IS-IS/BGP MAIN 安装代码。
  reconciler 注册在 L1、L2 和 BGP engine 的 stable-state 边界，汇总各协议 selected branches，
  再通过 MAIN engine 的 advertisement/withdrawal API 驱动跨协议 guarded RIB 重新选择。
- source identity 使用 `(protocol plane, SymbolicRouteKey)`，MAIN contribution 使用内部稳定 ID；
  不使用 route `toString()`。guard 逻辑变化保留 contribution identity，concrete route 变化或
  source 消失分别执行 replacement 或 recursive withdrawal。
- connected/static 仍作为 MAIN 原生 seed，不由 reconciler 接管；IS-IS attached default 的
  L1/L2 router 拒绝规则仍在注册 source 时显式保留。
- 动态端到端测试现在同时验证 L1 origin withdrawal、guard update、route replacement 会在
  L2 和 MAIN 两层同步删除、更新或重建，并验证 replacement 后 MAIN metric 与完整路径 guard。
- 能力边界：协议 RIB→MAIN 已持续 reconcile；MAIN→BGP redistribution 仍是固定 snapshot 的
  `BatfishBgpRedistribution` 路径。因此初始完整 symbolic RIB 正确，但返回结果后的 MAIN 变化
  尚不会自动重新生成本地 BGP contributions，后续需与已实现的 redistribution reconciler 统一。
- 验收：`//projects/minesweeper:minesweeper_tests` 在 `--nocache_test_results` 下通过；Java format
  与 `git diff --check` 通过。主源码 PMD 仍只报告 `Graph`、`Encoder`、`EncoderSlice`、
  `PropertyChecker` 和旧 SMT symbolic-route 文件的仓库基线违规，本阶段未新增
  `org/batfish/minesweeper/symbolicroute` 违规，也未修改上述关键 SMT 文件。

## Stage 6.5 MAIN→BGP 持续 redistribution（2026-08-29 20:14 CST）

- 新增 `BatfishBgpRedistributionReconciler`，在 MAIN stable-state 边界扫描配置的
  connected/static redistribution 关系，并复用唯一的 `BatfishBgpRedistribution` Batfish
  conversion/policy 实现生成 typed `Bgpv4Route` policy result。
- 将组件级 `BatfishRedistributionReconciler` 泛型化，使生产 BGP pipeline 直接使用其稳定
  contribution、guard update、deny/withdraw 和 transformed-route replacement 生命周期；删除
  pipeline 原有的一次性 BGP seed 构造路径。
- 增加 guard 逻辑等价 no-op 与 reentrancy barrier，避免 BGP→MAIN→redistribution 的同步
  stable-state listener 环产生无效消息或递归不终止。
- 动态端到端测试撤回 MAIN connected contribution，验证本地 BGP、远端 BGP 和远端 MAIN
  后代全部消失；以同 identity 和新 guard 恢复后，验证新 guard 与 session guard 的合取贯穿
  远端 BGP 和 MAIN。组件测试另行验证逻辑等价 guard 不产生任何 message/withdrawal/RIB update。
- 当前边界：只支持既有 connected/static→BGP rules；IS-IS redistribution、运行中修改配置或
  policy，以及 recursive static resolver 自身的持续增量生命周期仍未实现。
- 验收：完整 `//projects/minesweeper:minesweeper_tests` 在禁用缓存后通过，Java format 与
  `git diff --check` 通过。PMD 只报告既有 `Graph`、`Encoder`、`EncoderSlice`、
  `PropertyChecker` 和旧 SMT symbolic-route 基线违规；本阶段未新增 symbolicroute 包违规，
  也未修改上述关键 SMT 文件。

## Stage 6.6 recursive static 持续生命周期（2026-08-29 20:26 CST）

- 新增 `BatfishStaticRouteReconciler`，替换 pipeline 对 `resolveToFixedPoint` 的一次性调用。
  每个 MAIN stable state 都会触发语义重算；只有 guard 逻辑变化才向生产 MAIN 发送 delta。
- 每轮从排除 reconciler 自有 recursive-static candidates 的 MAIN availability 快照建立 scratch
  MAIN RIB，再调用既有 Batfish-backed symbolic LPM/fixed-point resolver 求最小不动点，避免基础
  resolver 撤回后旧 recursive routes 相互解析并错误地自我维持。
- 保留 Batfish `Rib.longestPrefixMatch` 与 `StaticRouteHelper.shouldActivateNextHopIpRoute` 作为
  concrete oracle；scratch MAIN 重新执行跨协议 preference，不能用一次 concrete LPM 取代
  “更长前缀可用时遮蔽较短前缀”的 symbolic guard。
- 新增动态 LPM 测试：不可用于激活的更长前缀存在时遮蔽短前缀，撤回 blocker 后 activation
  guard 自动扩大。pipeline 端到端测试进一步验证 connected resolver 撤回/恢复会同步删除/
  重建 recursive static、本地 BGP、远端 BGP 和远端 MAIN，并生成新的完整合取 guard。
- 当前边界：recursive static 配置集合仍属于固定 snapshot，尚不支持运行中新增、删除或修改
  static configuration；IS-IS→BGP redistribution 与 live policy/config mutation 仍待后续阶段。
- 验收：完整 `//projects/minesweeper:minesweeper_tests` 在禁用缓存后通过；Java format 与
  `git diff --check` 通过。PMD 仍只报告 `Graph`、`Encoder`、`EncoderSlice`、`PropertyChecker`
  和旧 SMT symbolic-route 基线违规，本阶段未新增 symbolicroute 包违规，也未修改这些关键文件。

## Stage 7.0 通用 SR 架构与 Batfish parser 审计（2026-08-29 21:16 CST）

- 确认 SR 位于 guarded IGP/MAIN 之后，不作为参与 MAIN preference 的新路由协议 RIB；Batfish
  负责 vendor syntax→vendor-independent SR configuration，Minesweeper 负责 SID guard、依赖和
  policy resolution，traffic/TE execution 保持独立阶段。
- 全仓库审计确认当前版本不存在 Prefix/Node/Adjacency SID、SRGB/SRLB、segment list、binding
  SID、SR policy/candidate path/steering 的结构化 Java model 或 grammar production；通用 MPLS
  常量不能替代 SR。`traffic_demo` 的 SR 命令当前不会进入 normalized `Configuration`。
- 新增 `SR_ARCHITECTURE.md`，固定 vendor/IGP-independent ownership：设备级 root config、VRF
  隔离、MPLS/SRv6 tagged values、absolute/index 区分、typed endpoint/prefix、稳定 identity、
  underlay provider API、guard 来源和 recursive dependency 规则。demo 仅作为后续验收 fixture。
- 本阶段仅形成可审计架构决策，没有修改 parser、datamodel、协议 comparator 或 pipeline 代码。

## Stage 7.1a 通用 SID value、global block 与 binding identity（2026-08-29 21:54 CST）

- 在 Batfish vendor-independent datamodel 新增 `SrSidValue`，以 tagged union 严格区分 resolved
  `MPLS_LABEL`、SRGB-relative unresolved `MPLS_INDEX` 与 typed SRv6 `Ip6`；typed accessor 防止
  index 被当作 wire label，JSON schema 仍只暴露显式 union 字段。
- 新增 `SrLabelRange` 与 ordered multi-range `SrGlobalBlock`。resolver 按配置顺序跨 range
  解析 index，拒绝空 block、重叠、越界、20-bit 溢出及 reserved label allocation；value object
  本身仍允许表示协议定义的 reserved label，职责没有混入 block。
- 新增 IPv4/IPv6 `SrPrefix`、稳定 `SrSidBindingKey` 与 `SrSidBinding`，在 identity 中包含 node、
  VRF、type、algorithm 和 typed prefix/interface/policy reference；Prefix/Node、Adjacency、
  Binding 的必填字段互斥，非 prefix SID 不得选择 SPF algorithm。
- `SrSidValueTest`、`SrGlobalBlockTest`、`SrSidBindingTest` 全部通过，覆盖 JSON 非法组合、
  边界、range 顺序、跨 VRF/node/algorithm identity 和类型拒绝。完整 common tests 的 13 个
  失败均来自既有 `FlowDiff` 与 routing-policy JSON/SMT 基线；common PMD 也只报告既有
  community/prefix/routing-policy 违规，没有 `org.batfish.datamodel.sr` 违规。

## Stage 7.1b 设备/VRF SR 配置与 Batfish Configuration 集成（2026-08-30 11:42 CST）

- 新增 vendor-independent `SegmentRoutingConfig` 与 `SegmentRoutingVrfConfig`，显式记录设备启用
  的 SR-MPLS/SRv6 data plane、SRGB、SRLB 以及按 VRF 隔离的 SID bindings；拒绝空 data plane、
  map-key/VRF 不一致、binding/VRF 不一致、重复 binding identity 和跨设备 owner 混入。
- 将 SR root config 以可空 typed property 挂接到 Batfish `Configuration`，setter 在 attachment
  边界验证所有 SID binding 的 node identity 与 configuration hostname 一致；JSON clone 保留
  完整 SR 配置，后续 vendor conversion 不需要字符串 side channel。
- 新增独立 `SrLocalBlock` 表示 SRLB allocation pool。它只提供 label membership，不提供
  SRGB-relative index→label 解析；因此不会把 local adjacency/binding label allocation 错当成
  global Prefix-SID index 语义。SRGB 继续由 ordered `SrGlobalBlock.resolve` 负责。
- `SegmentRoutingConfigTest` 覆盖 Configuration JSON round-trip、双 VRF 隔离、duplicate/owner/
  map-key 拒绝、SR-MPLS capability 约束和 SRLB 边界。与 Stage 7.1a 测试一起禁用缓存运行通过。
- 当前边界：这是 parser 可写入的通用 normalized model；尚未增加任何 vendor grammar/conversion，
  也尚未构建 Minesweeper guarded SID database 或 SR policy resolution。

## Stage 7.2a Cisco IOS ISIS-SR parser integration（2026-08-31 14:28 CST）

- 扩展 Cisco IOS lexer/parser，结构化识别 ISIS process 下的 `segment-routing mpls`，以及
  interface 下的 `isis prefix-sid absolute <label>` 和 `isis prefix-sid index <index>`；没有使用
  配置文本扫描或 demo-specific hostname/interface 映射。
- Cisco vendor representation 分别保存 ISIS SR-MPLS capability 与接口 Prefix-SID value/type；
  conversion 仅在对应 VRF 的 ISIS process 启用 SR-MPLS 时生成 normalized SR 配置。
- conversion 从接口的真实 `ConcreteInterfaceAddress` 构造 typed IPv4 prefix binding，保留 node、
  VRF、algorithm 0 和 PREFIX identity；absolute 值进入 `MPLS_LABEL`，index 值进入
  `MPLS_INDEX`，不会提前把 index 当作 wire label。
- 新增 `ios-segment-routing` parser fixture 和端到端断言，验证配置经过 grammar、extractor、
  vendor conversion 后实际进入 `Configuration.segmentRouting`；新增测试和既有 IOS ISIS parser
  回归测试均通过。
- 当前边界：本阶段尚未解析显式 SRGB/SRLB，因此 index 保持 unresolved typed value；IPv6
  Prefix-SID、multi-topology/algorithm syntax、adjacency SID 和其他 vendor grammar 后续分别扩展。

## Stage 7.2b Cisco IOS SRGB/SRLB 与 SID resolution（2026-08-31 15:16 CST）

- 依据 Cisco IOS-XE 两代真实配置层级，同时解析全局 `segment-routing mpls` 子模式中的
  `global-block`/`local-block`，以及旧式 ISIS process 下的 `segment-routing global-block`；两条
  vendor syntax 路径统一转换为同一个 device-level typed SRGB/SRLB。
- 未显式配置 SRGB 时使用 Cisco 默认 `16000–23999`；显式 device SRGB 与 legacy per-ISIS SRGB
  冲突时拒绝 conversion，避免同一设备产生含糊的 Prefix-SID label 解释。Cisco 当前单 range
  限制只存在于 vendor parser，通用 `SrGlobalBlock` 仍保留 ordered multi-range 能力。
- 新增 `SrSidResolver`。absolute MPLS label 保持不变，`MPLS_INDEX` 必须结合目标设备 SRGB
  才解析为 wire label；缺失 SRGB、越界和将 SRv6 当 MPLS 解析均显式拒绝。原 binding identity
  与原始 index 不被 parser/conversion 改写。
- 现代 fixture 验证 SRGB `45000–55000` 下 index 2 解析为 label 45002，并验证 SRLB membership；
  legacy fixture 验证 ISIS SRGB `30000–39999` 下 index 3 解析为 label 30003。两条 parser-driven
  测试与 resolver 边界测试全部通过。
- 当前边界：尚未解析 connected-prefix-sid-map、IPv6 Prefix-SID、algorithm、manual adjacency SID
  和其他 vendor grammar；SRGB 已进入 normalized state，但尚未构造 Minesweeper guarded SID DB。

## Stage 7.3a guarded SID database snapshot（2026-08-31 15:31 CST）

- 新建独立 `symbolicsr` 层及 protocol-neutral `SymbolicUnderlayReachability`；首个
  `IsisUnderlayReachability` adapter 只读取已收敛的 guarded IS-IS L1/L2 RIB，不让 SR 参与
  MAIN preference、BGP 或 redistribution。
- Prefix/Node SID reachability 使用 node/VRF/algorithm 隔离的 exact prefix advertisement；同一
  prefix 的 L1/L2 selected branches 按 guard 析取。覆盖该地址的默认路由不能伪造 Prefix-SID
  advertisement，IPv6 与非 algorithm 0 当前 fail closed。
- 新增稳定 `GuardedSidKey(resolver node, resolver VRF, SrSidBindingKey)`、`GuardedSidEntry` 和
  immutable `GuardedSidDatabase`。数据库遍历任意设备/VRF 名称，不依赖 demo；无 satisfiable
  underlay guard 的 binding 不进入 active snapshot，重复 typed identity 显式拒绝。
- pipeline 在 IS-IS fixed point 后构造 SID DB 并通过 result 暴露。Algorithm 2 diamond 测试给 R1
  的 loopback 配置 index Prefix-SID，验证 R4 SID guard 与所有故障回退 selection guards 的析取
  逻辑等价，并确认数据库保留原始 `MPLS_INDEX` 而非固定 label。
- 完整 Minesweeper 测试禁用缓存后通过。当前数据库是本次 fixed snapshot 的正确结果；pipeline
  返回后若直接调用 IS-IS engine 做增量 withdrawal/replace，SID snapshot 尚不会自动 reconcile。
  Stage 7.3b 将增加 underlay stable-state listener 与 typed SID delta lifecycle。

## Stage 7.3b guarded SID incremental lifecycle（2026-08-31 15:45 CST）

- 新增 `GuardedSidReconciler` 并同时注册到 IS-IS L1/L2 engine stable-state boundary。pipeline
  result 的 `getGuardedSidDatabase()` 始终返回 reconciler 当前 snapshot，并额外暴露 reconciler
  供审计最近一次有语义变化的 delta。
- 新增 typed `GuardedSidDelta`/`GuardedSidUpdate`：新 identity 为 `ADDED`，消失为 `REMOVED`，
  同 identity 且仅 guard 逻辑变化为 `GUARD_CHANGED`，SID value/flags payload 改变为 `REPLACED`。
  guard 比较使用 `RouteGuard.isEquivalentTo`，不是对象或公式字符串相等。
- nested L1→L2 stable callbacks 可能产生随后到达的 no-op reconciliation；reconciler 仍返回本次
  empty delta，但 `getLastDelta()` 保留最近一次非空语义 delta，避免 recursive callback 覆盖真正
  的 removal/update 审计记录。
- Algorithm 2 pipeline 动态验收覆盖完整序列：撤回 R1 loopback origin 后五台设备的 dependent
  SID 全部 `REMOVED`；以同 contribution identity 恢复产生 `ADDED`；仅修改 origin guard 产生
  `GUARD_CHANGED`；固定 binding key 下把 SID index 7 改为 8 产生 `REPLACED`。
- 完整 Minesweeper 测试禁用缓存后通过。当前 reconciler 维护 Prefix/Node SID；Adjacency-SID
  parser、canonical link dependency 与 policy/segment-list 后代仍属于后续阶段。

## Stage 7.4 Cisco IOS manual Adj-SID 与 canonical link dependency（2026-08-31 16:18 CST）

- Cisco IOS interface grammar 结构化解析 `isis adjacency-sid [absolute|index] <value>
  [protected]`，vendor representation 与 conversion 生成 `ADJACENCY` typed binding；identity
  使用真实 node、VRF、interface，不使用配置文本、route 字符串或 demo 映射。省略模式按 Cisco
  语义视为 absolute，`PROTECTED` 只允许出现在 adjacency binding。
- 明确修正 Stage 7.1b 的早期边界：SRLB 不只是 membership pool。手工配置的 local Adj-SID
  `MPLS_INDEX` 是 SRLB-relative index，因此新增独立 `resolveLocalMpls`；它不能调用 Prefix/Node
  SID 使用的 SRGB resolver。parser fixture 验证 index 4 在 SRLB `15000–15999` 中解析为 label
  15004，同时 guarded database 仍保留原始 typed index。
- `SymbolicUnderlayReachability.adjacencyAvailability` 返回 typed
  `SymbolicAdjacencyAvailability(LinkFailureKey, RouteGuard)`。首个 IS-IS adapter 从 Batfish parser
  构造的 directed edge 与 symbolic session 对齐 node/VRF/interface，并拒绝同 identity 的冲突
  session 或冲突 dependency；不再用拼接字符串充当 endpoint key。
- guarded SID snapshot 为 Adj-SID 记录 canonical、方向无关的物理 `LinkFailureKey` 与同一个
  link-up guard。Prefix/Node SID withdrawal 不会错误删除独立 Adj-SID；binding payload、guard 或
  dependency key 的变化仍分别进入 typed reconciliation lifecycle。
- common SR tests、Cisco parser-driven normalized-model test 和 Minesweeper Algorithm 2 集成测试
  以及完整 Minesweeper tests 均禁用缓存通过。Minesweeper PMD 仍只报告未修改的 Graph、旧 SMT
  Encoder/EncoderSlice/PropertyChecker/SymbolicRoute/TransferSSA 等基线违规，没有 Stage 7.4 或
  `symbolicsr` 新违规。当前尚未实现从任意 ingress 到 Adj-SID owner 的 segment resolution；该
  路径 guard 必须在后续 segment-list 层与本阶段 link guard 相与，不能提前混入 SID database。

## Stage 7.5a ordered guarded segment resolution（2026-08-31 16:43 CST）

- Adj-SID availability 在 canonical、方向无关的物理 `LinkFailureKey` 之外保留 parser-derived
  directed neighbor endpoint。二者职责分离：failure counting 对双向链路只计一次，而 segment
  execution 仍能把当前位置从 owner interface 推进到正确的 receiver node/VRF/interface。
- Cisco IOS manual Adj-SID 明确标记 `LOCAL`；`PROTECTED` 保持独立行为 flag。resolver 对未知的
  non-local/global adjacency 语义 fail closed，不会把本地 label 错当成全域可执行的 Node-SID。
- 新增 `GuardedSegmentListResolver`，按输入顺序解析 typed `SrSidBindingKey`。每一步从“当前
  node/VRF”的 guarded SID snapshot 取 contribution，并对 availability guards 做逻辑合取；
  Prefix/Node SID 把当前 endpoint 推进到 binding owner，local Adj-SID 只允许在 owner 执行并推进
  到 directed neighbor。缺失 binding、不可满足 guard、错误位置或尚未支持的 Binding-SID 均返回
  unresolved，而不是产生部分成功结果。
- Algorithm 2 diamond 集成测试验证从 R4 执行 `[R1 Prefix-SID, R1→R2 Adj-SID]` 的 guard 等价于
  `reach(R4,R1) AND up(R1,R2)`，terminal node 为 R2；从 R4 直接执行 R1 local Adj-SID 被拒绝，
  从 R1 执行则成功；撤回 R1 Prefix-SID 后同一 ordered list 立即不可解析。
- 聚焦测试与完整 Minesweeper tests 禁用缓存通过；PMD 输出与 Stage 7.4 完全相同，只包含未修改
  的 Graph 和旧 SMT 基线文件，没有新增 `symbolicsr` 违规。
- 当前结果是 segment guard 与 endpoint resolution，还没有输出 ingress MPLS label stack。下一步
  必须分别使用具体 forwarding next hop 的 SRGB 解析 Prefix/Node index、使用 Adj-SID owner 的
  SRLB 解析 local index，并保留每跳 label-swap 语义；不能把一个全局固定 label 写回 SID
  database。

## Stage 7.5b deferred MPLS label plan（2026-08-31 17:06 CST）

- 新增 top-first `MplsLabelPlan` 与 `MplsLabelInstruction`，显式区分 `FIXED_LABEL`、
  `NEXT_HOP_SRGB` 和 `OWNER_SRLB` 三种解析 scope。plan 保留原始 typed SID、binding identity、
  segment guard 与 terminal endpoint，不修改 guarded SID database。
- Prefix/Node absolute label 可直接进入 fixed instruction；Prefix/Node index 在具体 symbolic
  next-hop branch 尚未选择时保持 deferred。`resolveForNextHop` 只接受启用 SR-MPLS 且具有 SRGB
  的 Batfish `Configuration`，使用该邻居的 parsed SRGB 解析，而不是 ingress、SID owner 或任意
  固定设备的 block。
- Local Adj-SID absolute/index 由 binding owner 的 SRLB 解析并记录 owner scope；缺失 SRLB、越界、
  SRv6 SID、local Prefix/Node SID、non-local Adj-SID 和 Binding-SID 均 fail closed。这里不让
  concrete dataplane 替代 symbolic guard，仅复用 Batfish normalized SR block 数据和精确 resolver。
- diamond 集成测试使用不同的下一跳 SRGB：同一 Prefix-SID index 7 对 R2 解析为 20007、对 R3
  解析为 30007；后续 local Adj-SID index 4 由 R1 SRLB 解析为 15004。另有独立边界测试覆盖
  absolute Prefix-SID、SRv6/local-prefix 拒绝和缺失 owner SRLB。
- 完整 Minesweeper tests 禁用缓存通过。PMD 仍只报告 Graph 与旧 SMT 基线文件，没有新增
  `MplsLabel*`/`symbolicsr` 违规。下一步需要让 underlay forwarding transition 输出 guarded
  next-hop 分支，再把 deferred instruction 分区解析为每个分支的具体 ingress label stack；在此
  之前不能宣称已有一个唯一 numeric stack。

## Stage 7.5c guarded next-hop numeric stacks（2026-08-31 17:32 CST）

- 将 protocol-neutral underlay API 扩展为输出 `SymbolicNextHopBranch`：typed next-hop node/VRF/
  interface、RIB `selectionGuard` 和 canonical `LinkFailureKey`。IS-IS adapter 通过 Batfish
  `IsisRoute.getNextHop()` 的 IP 与 parser-derived directed edge 对齐，不解析 route 字符串或报告
  文本；同一 target 的 L1/L2 contribution guard 按逻辑析取。
- 修正并测试两个方向概念：Adj-SID 从 edge sender interface 执行后到 receiver；receiver RIB 中的
  next-hop IP 则反向识别 advertisement sender。二者共享物理 failure key，但 directed endpoint
  不可互换。首轮测试正是因此得到零分支，修正后与真实拓扑一致。
- 新增 `MplsNumericStackResolver`，对 ordered plan 中每个 Prefix/Node instruction 枚举 guarded
  next-hop，并对多个 segment 做 guard conjunction/branch expansion；每个结果保留 top-first numeric
  labels、next-hop decisions 和依赖 guard。没有 SRGB、标签越界或 guard 不可满足的单独分支被
  fail closed，不影响其他合法分支。
- absolute Prefix/Node label 虽不需要 SRGB，仍必须保留 next-hop branch 与 failure dependency；
  Prefix/Node segment 的当前 node 已是 owner 时作为 no-op elide，允许产生合法 empty MPLS stack，
  而不是伪造本地转发标签。
- Algorithm 2 集成测试得到三个真实分支：R4 直连 R1 为 `[16007,15004]`、经 R2 为
  `[20007,15004]`、经 R3 为 `[30007,15004]`，分别持有 `r1_r4`、`r2_r4`、`r3_r4` canonical
  dependency；无 SRGB 的 R5 分支被拒绝。完整 Minesweeper tests 禁用缓存通过，PMD 仍无新增
  `symbolicsr` 违规。
- Stage 7 现已完成 SID/segment/MPLS branch 核心。剩余 Stage 7.6 policy model/parser、Stage 7.7
  guarded candidate selection 与生命周期、Stage 7.8 顶层输出及 parser-driven 验收；不包含后续
  symbolic traffic/load execution。

## Stage 7.6a vendor-independent SR policy model（2026-08-31 17:48 CST）

- 新增 typed IPv4/IPv6 `SrPolicyEndpoint` 与稳定 `SrPolicyKey(node, VRF, color, endpoint)`；color
  使用 unsigned 32-bit 范围。policy display name 不参与 protocol identity，避免改名或显示文本
  变化破坏 withdrawal/replacement 对齐。
- 新增 `SrSegmentListKey(node, VRF, name)`、按显式 unsigned order 排序的 `SrSegmentList` 和 tagged
  `SrSegment`。segment 必须恰好包含 typed binding reference 或 explicit SID；重复 order、跨 VRF
  binding reference 和无 namespace 的 explicit `MPLS_INDEX` 均拒绝。后者只能通过 binding key
  找到正确的 SRGB/SRLB scope。
- 新增 `SrCandidatePath` 与 `SrPolicy`。candidate 稳定名称是 contribution identity；preference 与
  positive weight 是 unsigned 32-bit selection payload，segment-list name 是本 VRF 强引用。policy
  拒绝空 candidate、重复 candidate identity；VRF config 拒绝重复 list/policy identity、重复 policy
  name 和 undefined segment-list reference。
- `SegmentRoutingVrfConfig` 向后兼容原二参数构造器，同时 JSON schema 增加 segment lists/policies；
  `SegmentRoutingConfig.validateOwner` 扩展到 SID、segment list 和 policy 三类 node ownership。
- 新增 `SrPolicyTest` 覆盖 Configuration JSON round-trip、乱序 segment canonical ordering、IPv4/
  IPv6 identity、union/order/范围、跨 VRF、重复 identity、undefined reference 与 owner 拒绝。
  policy/common focused tests、已有 Cisco SR parser 与 Minesweeper Algorithm 2 compatibility tests
  全部禁用缓存通过。common PMD 仍只报告 community/prefix/routing-policy 基线文件，没有新增
  `org.batfish.datamodel.sr` 违规。
- 当前仅完成 parser 可写入的通用配置模型。explicit absolute SID 可以无损保存，但若不能唯一映射
  到 guarded binding，后续 symbolic resolver 必须 fail closed；Stage 7.6b 将增加 Cisco IOS
  policy/segment-list vendor representation、grammar 与 conversion。

## Stage 7.6b Cisco IOS SR-TE parser adapter（2026-08-31 18:20 CST）

- Cisco grammar 新增 `segment-routing traffic-eng`、命名 `segment-list`、ordered explicit MPLS
  label、policy `(color, IPv4 endpoint)` 和 explicit candidate `(preference, weight, list ref)`；
  支持 IOS 中 endpoint 带或不带 `ipv4`、segment-list 带或不带 `name` 的两种形式。
- 新增独立 vendor representation：`CiscoSrSegmentList`、`CiscoSrCandidatePath`、
  `CiscoSrPolicy`。extractor 先保留 CLI 语义，`CiscoConfiguration` 再集中转换成公共 typed model，
  没有绕过 Batfish parser，也没有让 Minesweeper 解析配置文本。
- candidate identity 使用 `explicit:<segment-list-name>`，明确不包含可变 preference/weight；同一
  policy 内相同 identity 的两个 candidate 会使整个 policy fail closed，避免按 preference 伪造身份。
- conversion 对空 list、20-bit label/order 越界、缺 color/endpoint、无 candidate、preference/
  weight/color 越界、undefined list reference 和重复 policy identity 全部告警并拒绝对应 list/policy，
  不构造半成品。当前全局 IOS SR-TE policy 归入 default VRF，设备未启用 IS-IS SR 时仍能独立保留。
- parser-driven 测试覆盖两条 segment list、ordered label、candidate preference/weight、typed endpoint，
  以及 undefined reference 和重复 stable candidate identity 的 fail-closed 行为。输入最初只有
  `hostname + SR-TE` 时未被 Batfish format detector 识别为 IOS；测试补入标准接口配置后走完整
  自动识别/解析/转换入口并通过，说明此前失败不是 SR 转换异常。
- 当前 parser subset 只接受 explicit MPLS label list 和 explicit local candidate。dynamic/PCEP、
  adjacency syntax、binding SID、SRv6 以及其他 vendor grammar 未被静默解释，将在独立 adapter
  阶段扩展；下一步 Stage 7.7 是 guarded candidate selection 与增量生命周期。

## Stage 7.7 guarded SR policy resolution/lifecycle（2026-08-31 21:35 CST）

- `GuardedSegmentListResolver` 可直接消费公共 `SrSegmentList`。typed binding reference 按完整 key
  查找；explicit SID 只有在当前 resolver node/VRF 唯一对应一个 guarded binding 时才接受，同值
  多义、缺失、Binding-SID、非法 local adjacency 或不可满足 guard 全部 fail closed。
- 新增 `GuardedSrCandidate`，稳定 identity 为 `(SrPolicyKey, candidateName)`，明确排除 preference、
  weight、guard 和 forwarding payload。candidate availability 是所有合法 numeric MPLS branch guard
  的析取；selection 为自身 availability 与所有更高 preference availability 的否定合取。
- preference 分组三层测试覆盖 high、两个等优先级 middle 和 low：两个 middle 不互相抑制，但都受
  high 抑制；low 同时受 high 和两个 middle 抑制。candidate weight 仅保留为配置数据，本阶段不做
  traffic/load execution。
- 新增 `GuardedSrPolicyContribution`，每个选中 forwarding branch 保留 numeric label stack、terminal、
  typed next-hop、canonical `LinkFailureKey` 和全部 `GuardedSidKey` 依赖。branch identity 不使用 route/
  report string；同 identity 的 label/terminal/dependency payload 改变为 `REPLACED`，仅公式改变为
  `GUARD_CHANGED`。
- 新增 `GuardedSrPolicyDatabase`/`GuardedSrPolicyReconciler`/`GuardedSrPolicyDelta`。SID 依赖消失时，
  candidate 与其 child contributions 在同一 stable reconciliation 中产生 `REMOVED`，低优先级 guard
  随即扩大；binding payload 原子变化会产生 forwarding output replacement。
- 初版只监听非空 SID delta，审计发现 ECMP/next-hop branch 可变化而 aggregate SID guard 逻辑等价，
  会漏掉 output 更新。已增加每次 stable underlay reconciliation 通知；专项测试验证 SID delta 为空
  时 policy 仍产生旧 branch `REMOVED` 和新 branch `ADDED`。
- 新增测试覆盖 explicit SID 歧义拒绝、三层 preference、同 preference、guard update、SID dependency
  recursive withdrawal、低优先级恢复、payload replacement 和等价 aggregate guard 下的 next-hop
  replacement。完整 Minesweeper tests 禁用缓存通过；Minesweeper PMD 仍只报告 Graph/Encoder/EncoderSlice/
  PropertyChecker 及旧 SMT symbolic-route 文件的 34 条基线违规，没有新增 `symbolicsr` 违规。
- Stage 7.7 的准确边界是固定 SR 配置，并在每次 underlay stable boundary 上增量 reconcile；单份
  database 是 snapshot，但 reconciler 不是 fixed-snapshot resolver。下一步 Stage 7.8 将把数据库接入
  顶层 pipeline/result report，并用 Batfish parser 产生的 Cisco SR-TE 配置做端到端验收；不进入
  symbolic traffic execution。

## Stage 7.7 delta 契约审计（2026-08-31 22:46 CST）

- 明确 `GuardedSrPolicyDelta` 是两个 stable state 之间的原子 batch，而不是按 list 顺序执行的事件流。
  同 stable key、非 guard payload 改变为 `REPLACED`；identity/key 改变为同一 batch 内旧值 `REMOVED`
  与新值 `ADDED`，消费者不得任意配对无关 remove/add。
- 测试锁定两种边界：binding label payload 改变保持 key 并产生 `REPLACED`；next-hop identity 改变产生
  不同 key 的 `REMOVED+ADDED`，且 reconcile 后数据库只包含新 contribution。
- 能力边界统一为固定 SR 配置、逐 underlay stable boundary 增量 reconcile。普通 typed Prefix/Node/
  Adjacency SID binding 已支持；递归 Binding-SID segment/policy expansion 尚未支持并 fail closed。

## Stage 7.8 顶层 pipeline/output 与 parser-driven 验收（2026-09-01 10:12 CST）

- `BatfishSymbolicRoutePipeline` 在 IS-IS/SID stable state 后构造 `GuardedSrPolicyReconciler`；同一
  result 同时暴露 MAIN/BGP/IS-IS RIB、guarded SID database 和 guarded SR-policy database，没有把
  SR policy 错装进 MAIN RIB，也没有进入 symbolic traffic/load execution。
- 新增 `SymbolicSrPolicyRecord` 作为只读输出 DTO。它确定性展示 node/VRF、color/endpoint、policy、
  candidate preference/weight/segment-list、numeric label stack、typed next-hop、canonical link
  dependency、terminal 以及 availability/selection guard；report text 不参与任何 identity。
- 顶层可读报告新增 SR candidate/forwarding 表，另提供简化 JSON 和 raw JSON。默认输出只做 Z3
  display simplify；raw 输出保留 stable database 中的原公式。
- 新增 `networks/sr-symbolic-route/configs` 两节点 IOS 验收配置。测试从 Batfish parser、concrete
  dataplane/ISIS topology、parser-driven pipeline 一路运行到 guarded Prefix-SID、candidate selection
  和 forwarding contribution，断言 label `16002`、next hop `r2/default/GigabitEthernet0/0` 与统一
  canonical `LinkFailureKey(r1,r2)`。
- 验收暴露旧 parser 闭环缺口：grammar 已接受 `isis network point-to-point`，但 extractor/vendor
  conversion 未保存。以最小三点修改将该命令写入 Cisco interface representation 并转换到 Batfish
  `IsisInterfaceSettings.pointToPoint`；未放宽 Minesweeper 对非 point-to-point IS-IS 的安全拒绝。
- 能力边界不变：固定 SR 配置，在每次 stable underlay boundary 增量 reconcile；普通 typed SID
  binding 已支持，递归 Binding-SID 尚未支持。下一阶段仍不包含 traffic execution。
- 2026-09-01 10:12 CST 验证：完整 `//projects/minesweeper:minesweeper_tests` 禁用缓存通过；Cisco
  grammar/vendor representation 两个 PMD target 通过。Minesweeper PMD 仍失败于既有 Graph/Encoder/
  EncoderSlice/PropertyChecker 和旧 SMT symbolic-route 共 34 条基线违规，本次新增/修改类零违规。

## Stage 7.9 是否必要的决策记录（2026-09-01 10:40 CST）

- Stage 7.9 不作为当前 symbolic route/SR 算法闭环的强制前置条件。Stage 7.8 已完成从 parsed
  configuration、stable guarded IS-IS underlay、typed SID 到 selected guarded SR forwarding
  contribution 的正确性闭环。
- 当前实验若使用已支持的 explicit `index ... mpls label ...` segment-list，可直接使用 Stage 7.8；
  不因尚未覆盖更多配置语法而阻塞后续步骤。
- `index ... address ipv4 ...` Prefix/Node segment 是运行现有 `networks/traffic_demo` 时才必须补充的
  parser adapter；parsed adjacency segment、dynamic/PCEP candidate 和递归 Binding-SID expansion
  同样改为需求驱动的独立扩展。
- 普通 typed Prefix/Node/Adjacency SID binding 的内部解析语义已经实现。递归 Binding-SID 尚未支持，
  继续明确 fail closed，不能把“不支持”静默解释为部分成功。

## Stage 8.0 concrete 1-failure SR-TE demo 输入（2026-09-01 12:14 CST）

- 新增五节点 `X/A/S/B/D` parser-driven 配置快照。X 的 20-Gbps IP flow 正常经 cost 10 的 X-D，
  X-D 故障后经 cost 20 的 X-A-D；S 的 SR policy 使用同 preference 的 upper/lower candidates，初始
  weight 为 50/50。
- SR 路径使用已支持的 explicit MPLS-label segment-list，并由本地 Adj-SID 精确绑定 S-A-D 与 S-B-D，
  避免 Node-SID 在故障后由 IGP 绕行而改变预期 candidate failure 语义。
- 流量、canonical undirected links、每链路 95-Gbps 容量、0/1-link failure model 和逻辑整数变量
  `h` 保存在同一 demo 根目录 `networks/tolerance_sr_te_demo/traffic.json`；Batfish 仍只解析其
  `configs/*.cfg`，脚本和生成结果不得写入该目录。
- 预期解释性结果锁定为：仅 `d_x` 故障使 X flow 转移到 A-D，产生
  `load(A-D) = 20 + 0.8h < 95`，因此在整数百分比定义域内新增 TE 子规约 `h <= 93`。
- parser-driven 验收从五份 IOS 配置运行到 concrete dataplane、IS-IS topology 和现有 symbolic-route/
  SR pipeline，检查两个 50-weight candidates，并分别断言 upper guard 为 `a_s AND a_d`、lower guard
  为 `b_s AND b_d`。本阶段尚未实现 traffic execution 或 per-scenario subspec runner。
- 2026-09-01 12:22 CST 验证：初次验收发现同一 `preference` stanza 下只能配置一条 explicit
  candidate；改为两个同值 `preference 100` stanza 后，parser 保留两个不同 stable candidate identity。
  `ToleranceSrTeDemoConfigTest` 禁用缓存运行通过，证明配置不是仅通过文本/JSON 格式检查。
- 2026-09-01 12:23 CST 补充断言并再次通过：无故障 concrete MAIN RIB 中 X 到 D loopback 的唯一
  longest-prefix-match next hop 是 X-D 对端 `10.0.15.2`，锁定 20-Gbps IP flow 的初始主路径。
- 2026-09-01 12:29 CST 按实验输入组织要求将 `traffic.json` 与配置快照归入同一个 demo 根目录；
  网络 BUILD data target 同步覆盖该输入，但设备 parser 边界仍严格保持为 `configs/`。

## Stage 8.1 parser-driven 通用 snapshot 输入（2026-09-01 13:14 CST）

- 删除实际 pipeline 对 `r1-originate-P`、节点名、固定 VRF 和手写 route-map 的依赖。新增
  `BatfishBgpRedistributionRuleExtractor`，确定性枚举所有 parsed node/VRF 的 `BgpProcess`，直接复用
  Batfish 规范化的 `getRedistributionPolicy()`；policy 为 null 的 BGP process 不产生规则，缺失的
  policy 引用明确失败，不能静默漏路由。Cisco 会为未配置 redistribution 的 process 生成恒拒绝
  wrapper policy，因此这些 process 保留 evaluation boundary，但不会产生 BGP contribution。
- 自动规则 identity 使用 hostname、VRF 和 normalized policy 的长度前缀字段，不使用 route
  `toString()`；普通 route attributes 仍不进入 message identity。每个规则把同 VRF MAIN 的非 BGP
  candidate 交给 Batfish policy interpreter，BGP/IBGP candidate 明确排除以防反馈。
- parsed snapshot builder 同时修正多 VRF 输入：connected route 使用 interface 的真实 VRF；所有
  configured static route 从 `Vrf.getStaticRoutes()` 自动装载。next-hop-IP static 进入既有 recursive
  fixed point；active next-hop-interface static 绑定 canonical link guard；discard/next-VRF static 按
  Batfish `VirtualRouter.initStaticRibs` 作为 unconditional configured contribution。
- `SmtReachabilityTest` 保留无 traffic 与带 traffic 两个 writer；二者共用同一个配置驱动 symbolic
  pipeline 和真实 parsed IS-IS topology。traffic writer 另外要求同 snapshot 根目录存在
  `traffic.json`，并复制为同一次输出中的 `0_traffic.json`。
- 能力边界：这里的“任意上传配置”表示不依赖拓扑节点名、固定 origin 或手写 redistribution rule；
  协议能力仍遵守当前 pipeline 的显式边界（IPv4 numbered eBGP、当前已实现的 static/connected、
  IS-IS 与 SR 子集）。iBGP、unnumbered BGP 或未支持的 SR 语法仍应显式拒绝，不能宣称已支持。
- 2026-09-01 13:14 CST 验证：tolerance 四路由器 parser-driven BGP 回归和 SR-TE parser-driven
  回归通过；实际 `SmtReachabilityTest.testReachability` 通过，并在同一 `smt_output_0034` 中生成
  `0_symbolic_routes_init.txt`、`0_symbolic_routes.txt` 与 `0_traffic.json`。
- 2026-09-01 13:34 CST 完整 `//projects/minesweeper:minesweeper_tests` 禁用缓存通过。PMD 首轮仅在
  本次 builder 中发现一个迁移后未使用的 `ImmutableList` import，已删除；其余报告仍为既有
  Graph/Encoder/EncoderSlice/PropertyChecker 与旧 SMT symbolic-route 基线项。

## Stage 8.2 symbolic RIB typed NextHop 展示（2026-09-01 13:38 CST）

- `SymbolicRibRecord` 已经在内部和 JSON 中保存完整 typed next hop，但 readable/raw text renderer
  之前只展示派生的 `NextHopIP` 与 `NextHopInterface`，对 discard、next-VRF 以及后续 next-hop 类型
  不完整。本阶段在保留两个便于筛选的派生列同时，新增 `NextHop` 列并直接展示记录中的完整值。
- 新增 text header/value 与 JSON `nextHop` 回归断言；不改变 route identity、guard、RIB selection
  或协议传播语义。
- 2026-09-01 13:44 CST 完整 `//projects/minesweeper:minesweeper_tests` 禁用缓存通过；实际
  `SmtReachabilityTest.testReachability` 通过，最新 `smt_output_0039/0_symbolic_routes.txt` 已显示
  `NextHop`、`NextHopIP`、`NextHopInterface` 三列。

## Stage 8.3 Batfish 接口路由对齐与 MAIN 展示边界（2026-09-01 17:34 CST）

- 新增 `BatfishInterfaceRouteInitializer`，按 Batfish `VirtualRouter` 的接口初始化语义从 parsed
  configuration 生成 symbolic CONNECTED/LOCAL seeds：只处理 active interface；CONNECTED 默认
  生成；LOCAL 默认只为小于 `/32` 的接口地址生成 `/32`；完整遵守每地址 metadata 中的
  `generateConnectedRoute`、`generateLocalRoute`、admin 和 tag。
- CONNECTED message identity 保持既有 `connected:node:interface:address` 格式，避免无意义的身份
  迁移；LOCAL 使用独立 `local:` 前缀。二者引用同一 parser-derived canonical interface
  `LinkFailureKey`/guard，未匹配物理链路的接口仍按 Batfish 本地初始化语义使用 `true` guard。
- `SymbolicRibRecord` 增加 route metric、administrative cost 和 selection satisfiability。JSON 保留
  完整 candidate audit；人类可读 MAIN 表只展示 selection guard 可满足的 guarded forwarding
  selections，协议明细表仍保留未选候选，因而本机 CONNECTED 已胜出的 ISIS origin 不再冒充 MAIN
  forwarding route。
- 可读表加入 `Metric`/`AD`。原 `Path` 列改名为 `AdvertisementPath`：当前值是控制平面传播来源，
  不能在多 contribution 尚未分支保存前误称为 forwarding path。真正的 guarded physical
  forwarding branches 是下一阶段修正项。
- 新增组件测试覆盖 inactive interface、`/32` 默认行为、metadata 显式启用/抑制及 admin/tag；
  parser-driven SR-TE demo 断言 12 条 LOCAL seeds；四路由器验收断言 R4 的 3 条 LOCAL records。
- 2026-09-01 17:34 CST 验证：完整 `//projects/minesweeper:minesweeper_tests` 禁用缓存通过，共
  276 个测试；输出中的 Java 8 source/target 信息仍只是既有编译器警告。

## Stage 8.4 contribution 分支传播与 symbolic/concrete 集成证明（2026-09-01 18:08 CST）

- 修正 `GuardedRib` 聚合候选只保留一个 representative provenance 的下游语义错误。候选级
  availability 仍是所有 contributions 的析取，用于 priority/ECMP selection；新增 contribution-level
  entries，使每个分支分别保存自身 availability、selection guard、identity 和 provenance。
- `ConvergenceEngine` 的 advertisement registry 从每个 exporter/candidate 一条改为按 parent
  contribution 分支保存。export message identity 由协议 adapter 的稳定 base identity 与完整 parent
  contribution identity 组合，不使用 route `toString()`；每个 child 只依赖一个真实 parent，guard
  更新、替换和 recursive withdrawal 不再错误地绑定所有 parents 到一条聚合 child。
- 分支契约贯穿三个容易再次压扁路径的 stable-state 边界：协议 RIB 到 MAIN、MAIN 到 BGP
  redistribution、IS-IS L1 到 L2 transition。各 reconciler 的 source identity 均加入源 contribution
  identity；相同 concrete route 的不同物理传播来源保持独立生命周期。
- 人类可读 MAIN 表改为 contribution-level guarded forwarding branches；协议明细仍保留候选聚合
  audit。每条 MAIN branch 显示自己独立的 guard 与反向后的 `ForwardingPath`，不再显示 OR guard
  配任意 representative path。当前 path 解释适用于已支持的 numbered point-to-point ISIS/基础 eBGP
  pipeline；后续 traffic execution 应消费 typed/canonical edge dependencies，而不是解析展示字符串。
- 新增 diamond 测试：同一 seed 经 `A-B-D` 与 `A-C-D` 到达相同 candidate，D 保留两条独立 guards、
  provenance 和 child dependencies，同时候选 availability 等价于两者析取。
- parser-driven SR-TE demo 的验收端点与实验 query 对齐为 `S -> D`。全 failure domain 中 MAIN 保存
  `S-A-D`、`S-B-D` 和仅在多链路故障条件下可选的 `S-A-X-D`。当前 pipeline 尚未接收
  `ReachabilityQuestion.failures=k`，因此 k-failure pruning/报告投影必须作为下一项显式集成，不能
  静默把全域 symbolic RIB 当作 `k=0/1` 结果。
- 新增 all-links-up 集成断言：逐设备、逐默认 VRF 将 symbolic MAIN 中在全链路 up assignment 下
  selected 的分支解开 annotation，与 Batfish concrete MAIN 的 `AbstractRoute` 集合直接比较，全部
  相等；比较不经过 `dataplane.txt` 字符串。`RibPrinter`/concrete dataplane 输出逻辑保持零修改。
- 2026-09-01 18:08 CST 验证：完整 `//projects/minesweeper:minesweeper_tests` 禁用缓存通过，共
  277 个测试。用户工作区中的 `SmtReachabilityTest.java` 配置切换未修改、未暂存。

## Stage 8.5 SMT 测试按 snapshot traffic 能力分发（2026-09-01 18:20 CST）

- 修正 `SmtReachabilityTest.setup()` 无条件调用 traffic writer 的回归。新增单一 snapshot writer
  入口：配置根目录存在常规文件 `traffic.json` 时调用 `writeTrafficSymbolicRoutes`，复制同一次输入
  并运行 symbolic-route pipeline；不存在时直接调用 `writeSymbolicRoutes`，不要求或生成 traffic
  副本。`writeTrafficSymbolicRoutes` 自身仍保留缺少输入时 fail-fast 的严格契约。
- 保留当前 `tolerance-symbolic-route` 配置及 `r1 -> r4`、目的地址 `192.0.14.2/32` 的用户查询；
  未修改 `RibPrinter` 或 concrete `dataplane.txt` 输出逻辑。
- 2026-09-01 18:20 CST 先精确复现原失败：测试在 reachability 编码前因缺少
  `networks/tolerance-symbolic-route/traffic.json` 抛出 `IOException`。修复后同一条
  `SmtReachabilityTest.testReachability` 禁用缓存通过；`smt_output_0043` 同时包含 SMT 编码、
  raw/readable symbolic RIB，且按预期不包含 `0_traffic.json`。

## Stage 8.6 symbolic RIB 简洁 next-hop node 展示（2026-09-01 18:37 CST）

- 将 readable/raw text 表中的 `NextHop` 从 Batfish typed next-hop 对象字符串改为设备名，与
  concrete `dataplane.txt` 的该列语义对齐：本地起源、CONNECTED 和 LOCAL 路由显示 `null`；
  传播路由显示当前设备实际转发到的下一跳设备，例如 R2 直达 R1 的 BGP 分支显示 `r1`。
- next-hop node 不通过 IP 或接口名猜测。MAIN contribution 使用已保留的 `ForwardingPath` 第二个节点；
  协议 RIB 使用 `AdvertisementPath` 中当前节点的前驱。这样同一候选的不同 failure-conditioned
  forwarding branches 可以分别显示不同 next hop。
- 该修改仅作用于人类可读 renderer，并将列宽从 typed object 所需的 34 字符缩为 10 字符；
  `SymbolicRibRecord.nextHop`、JSON 中的 typed next hop、`NextHopIP` 和 `NextHopInterface` 均保留，
  控制平面语义及 concrete `RibPrinter` 没有修改。
- 2026-09-01 18:37 CST 验证：四路由器 parser-driven 测试通过，新增断言覆盖 R2->R1 分支和
  readable text 不再包含 `NextHopInterface{interfaceName=...}`；当前 r1->r4 SMT reachability 测试
  通过，实际 `smt_output_0045/0_symbolic_routes.txt` 显示 `null`、`r1`、`r2`、`r3`、`r4`。
- 2026-09-01 18:46 CST 完整 `//projects/minesweeper:minesweeper_tests` 禁用缓存通过，共 277 个
  测试。首轮唯一失败是旧断言仍要求 readable text 包含 typed next-hop；断言已按新契约修正为
  typed 值保留在 JSON、不得泄漏到 readable text，随后完整套件通过。

## Stage 8.7 简化/初始报告的 guard 展示边界（2026-09-01 18:53 CST）

- `0_symbolic_routes.txt` 作为面向结果审查的简化报告，只显示最终 `SelectionGuard`，不再重复展示
  `AvailabilityGuard`；该规则同时应用于 MAIN、BGP、IS-IS 与 SR policy 表。
- `0_symbolic_routes_init.txt` 继续同时显示未化简的 `AvailabilityGuard` 与 `SelectionGuard`，用于
  审计候选可用性与优先级抑制的区别。内部 guarded RIB、`SymbolicRibRecord` 和 JSON 均未删除
  availability 数据，因此这只是输出投影，不改变 Algorithm 1 语义。
- 新增端到端表头断言：simplified report 必须有 selection 且没有 availability，raw init report
  必须同时包含两者。2026-09-01 18:53 CST 四路由器 parser-driven 测试和当前 r1->r4 SMT
  reachability 测试通过；实际 `smt_output_0048` 的两份文件符合上述边界。
- 2026-09-01 18:54 CST 最终合并状态的完整 `//projects/minesweeper:minesweeper_tests` 禁用缓存
  通过，共 277 个测试。

## Stage 8.8 简化 SR policy forwarding-only 投影（2026-09-01 19:33 CST）

- 消除 simplified symbolic RIB 中同一个 SR candidate 同时显示 `CANDIDATE` 与
  `FORWARDING_BRANCH` 的重复。`0_symbolic_routes.txt` 的 SR 部分现在只展示已经解析成功、可供
  forwarding/traffic 层消费的 contributions；由于所有行均为 forwarding branch，简化表同时移除
  恒定的 `Kind` 列。
- `0_symbolic_routes_init.txt` 继续保留 candidate 与 forwarding branch 两类记录、`Kind`、
  availability 和 selection guards，用于审计 preference 选择、segment resolution 与依赖生命周期。
  guarded SR database、JSON API 和 candidate selection 语义均未改变。
- 新增输出契约测试：simplified report 不出现 kind value，raw init report 必须同时出现
  `CANDIDATE` 与 `FORWARDING_BRANCH`。2026-09-01 19:32 CST 当前 S->D SMT 测试通过，实际
  `smt_output_0050` 将 demo SR 表由 4 行压缩为 upper/lower 两条 forwarding branches；
  2026-09-01 19:33 CST 完整 Minesweeper 277 个测试通过。

## Stage 8.9 concrete dataplane forwarding tuple 去重（2026-09-02 11:57 CST）

- 修正 `RibPrinter` 将多个不同控制平面 route 投影为相同 forwarding 字段后重复打印的问题。
  去重仅发生在人类可读 `0_data_plane.txt`：以当前实际打印的完整行作为 forwarding tuple，只有
  Node、VRF、Network、Protocol、NextHopIP、NextHopInterface、NextHop、Metric、AD、Tag 全部相同
  才合并；Batfish concrete RIB、`RoutesAnswerer` 的 route multiset 与 symbolic RIB 均不修改。
- 该边界保留真正不同的 forwarding choices。新增 parser-driven demo 断言：B 对
  `10.0.12.0/30` 经 D 的两个不同 IS-IS origin 投影为一行；S 对 `10.0.15.0/30` 经 A 的重复投影
  为一行，但经 A 与经 B 的两个 next hops 必须各保留一行。
- 2026-09-02 11:57 CST 当前 S->D SMT reachability 测试通过；实际 `smt_output_0051` 的
  `0_data_plane.txt` 已无任何完全重复行，同时上述 A/B ECMP choices 均存在。完整
  `//projects/minesweeper:minesweeper_tests` 禁用缓存通过，共 277 个测试。

## Stage 8.10 traffic 目标投影与 forwarding identity 边界（2026-09-02 12:31 CST）

- 明确区分 route propagation provenance 与 traffic forwarding choice。当前 symbolic MAIN 报告可将
  同一本地 next hop、但具有不同 downstream contribution path 的证明显示为多行；这些行用于审计
  Algorithm 1 的传播与 withdrawal 依赖，不能直接解释为多条 ECMP traffic branches。
- 后续 symbolic traffic 的 forwarding identity 固定为本地动作
  `(node, vrf, matched-prefix, next-hop/egress-adjacency)`：相同本地动作的 contribution guards 做逻辑
  OR，仅不同本地 adjacency 参与 ECMP/负载拆分；在同一 failure assignment 下再逐跳解析下游动作。
  SR policy 中不同 explicit segment-list contribution 仍是独立 policy branch。该决策本阶段仅记录
  traffic 层消费契约，不改 guarded RIB 的候选/依赖模型。
- BGP demo 并未采用不同的候选合并规则；它之所以更简洁，是因为 BGP LOC-RIB 只传播单一业务前缀
  `10.0.0.0/24`。MAIN 中的 CONNECTED/LOCAL 基础前缀仍存在，同 next-hop 的不同 provenance 也仍可
  在原始报告中出现。
- 对带 `traffic.json` 的运行，`0_symbolic_routes.txt` 现在从 `flows[].destination` 读取目标集合，只
  展示与目标重叠的 MAIN/protocol routes 以及 endpoint 命中的 SR policy；报告头显式记录
  `Destination projection`。`0_symbolic_routes_init.txt` 保持全量原始 guards/provenance，
  `0_data_plane.txt` 保持完整 concrete dataplane，未修改其计算或输出范围。无 traffic 输入的网络仍
  输出完整简化 symbolic RIB。
- SR-TE demo 的 traffic、SR endpoint 与 reachability query 统一为 D 的直接 loopback
  `5.5.5.5/32`。删除 A/B/S/X 未被 adjacency-SID segment lists 使用的 Loopback0/prefix-SID，保留
  所有编号 transit interfaces、IS-IS adjacency 与 D 的目标 loopback；因此减少无关前缀而不改变
  underlay 或 SR policy 的路径语义。
- 2026-09-02 12:31 CST parser-driven demo 验收通过，包含 concrete/symbolic all-up RIB 一致性、
  上下 SR candidate guard 和目标投影断言；当前 S->D `5.5.5.5/32` SMT reachability 通过。实际
  `smt_output_0053` 中简化 symbolic 文件只含目标 `/32`，原始 symbolic 与 dataplane 仍含 transit
  `/30`。

## Stage 9.1 无损 Symbolic Control Plane 导出契约（2026-09-02 14:41 CST）

- 新增版本化 `SymbolicControlPlaneExport`，schema 为
  `batfish-minesweeper-symbolic-control-plane` version 1。它直接遍历 MAIN、BGP、IS-IS L1/L2 的
  `GuardedRib`，不解析 readable report，也不使用 route `toString()` 作为属性或身份。
- 每个 candidate 导出稳定的 `candidate-v1-<sha256>`、plane/router/VRF/prefix/protocol、完整
  Batfish concrete route JSON、source VRF、aggregate availability/selection guard，以及每个独立
  contribution。route type 使用 Batfish 类名作 discriminator；`RoutePayload.decode()` 会先验证类型，
  再恢复原 Batfish typed route。
- 每个 contribution 保留 message/sender/receiver identity、protocol session ID、独立 availability
  与 selection guards、完整 propagation provenance，以及从 Algorithm 1 recursive-withdrawal registry
  读取的 parent contribution identities。guard 同时保留内部 raw 公式、display-simplified 公式和
  satisfiable 标志。
- 修补此前只存在于 `SymbolicRouteMessage`、安装后丢失的 session metadata：`GuardedRib` 现在随
  contribution 生命周期保存/删除 session ID；candidate key、route payload、withdrawal identity 和
  preference 语义均未改变。
- `BatfishSymbolicRoutePipelineResult.toControlPlaneJson()` 暴露正式机器接口；一次
  `SmtReachabilityTest` 运行会在同一 `smt_output_*` 目录额外写出
  `0_symbolic_control_plane.json`。原始/简化 readable reports 保持原契约。
- 测试覆盖 schema JSON round-trip、BGP typed-route round-trip、R4 local-pref 50/100/200、稳定且互异
  的 candidate IDs、BGP session 与 parent dependency 不丢失、禁止 `AnnotatedRoute{...}` 字符串
  payload，以及 session metadata 的安装/撤回生命周期。2026-09-02 14:38 CST 定向测试通过。
- 2026-09-02 14:39 CST PMD 仍只报告 Graph/Encoder/EncoderSlice/PropertyChecker 和旧 SMT route
  类的 34 项既有基线违规；本 Stage 新增/修改的 symbolic-route 文件没有新增 PMD 违规。核心
  `Graph.java`、`Encoder.java`、`EncoderSlice.java`、`PropertyChecker.java` 均未修改。
- 2026-09-02 14:43 CST 完整套件首次运行 279 个测试，唯一失败是用户工作区中原先未跟踪的
  `TrafficDemoSingleLinkFailureTest`：其输入包含当前 Cisco parser 不接受的旧 SR extension syntax，
  在进入 symbolic pipeline 前即解析失败。排除该已知独立测试后，其余 278 个 Minesweeper 测试
  禁用缓存全部通过，本 Stage 没有引入协议或 SR 生命周期回归。
- 2026-09-02 14:44 CST 当前 `SmtReachabilityTest.testReachability` 禁用缓存通过；同一次运行生成的
  `smts/smt_output_0055/0_symbolic_control_plane.json` 已核验包含 schema/version、R4 BGP
  local-preference 200、结构化 AS-path/communities/next-hop、`r2:default->r4:default` session、parent
  contribution 和 exact/simplified guards。

## Stage 9.1.1 可重建 Guard AST 与变量语义表（2026-09-03 13:10 CST）

- 将机器导出 schema 升级为 version 2。每个 availability/selection guard 现在额外保存与求解器
  无关的 `BooleanGuardAst`，节点类型限定为 `TRUE`、`FALSE`、`VARIABLE`、`NOT`、`AND`、`OR`；
  AND/OR 会扁平化、稳定排序并去重，因此 JSON 不依赖 Z3 AST 的打印格式或当前 `Context`。
- `Z3RouteGuard` 在布尔运算期间同步维护等价 AST；`simplify()` 和展示化简只改变当前 Z3 表达式，
  不丢弃原始等价 AST。`Z3RouteGuardFactory.fromAst()` 可在新的 Z3 `Context` 中重新编译 AST。
  因此导出的 `ast` 是后续 Minesweeper/SR/traffic 消费者的正式输入，`raw` 和 `simplified` 字符串仅
  用于审计和阅读，不作为解析接口。
- 根级 `guardVariables` 给每个 AST 变量提供显式语义。parser-driven topology 产生的变量绑定到
  canonical、无方向的 `LinkFailureKey`，并明确 `polarity=UP`；没有已知 link binding 的变量标记为
  `UNINTERPRETED_BOOLEAN`，禁止通过变量名猜测链路或 up/down 含义。同一变量若被绑定到两个不同
  canonical links，pipeline 会立即拒绝输入。
- 新增 AST canonicalization、JSON round-trip、跨 Z3 Context 等价重建测试；四路由器端到端测试
  同时断言 `r1_r2` 对应 canonical link `(r1,r2)`、极性为 UP，并在全新 Context 中将 R4
  local-preference 200 的 selection AST 重建为与 `r1_r2 && r2_r4` 逻辑等价。
- 2026-09-03 13:06 CST 定向测试共 20 个全部通过；2026-09-03 13:07 CST 完整 Minesweeper 回归
  排除用户工作区中已知、未跟踪且 parser-failing 的 `TrafficDemoSingleLinkFailureTest` 后，共 281 个
  测试全部通过。2026-09-03 13:10 CST PMD 仍仅报告原有 34 条 Graph/旧 SMT 基线违规，本阶段
  symbolic-route 文件没有新增违规；`Graph.java`、`Encoder.java`、`EncoderSlice.java`、
  `PropertyChecker.java` 均未修改。

## Stage 9.2 独立 0/1-link failure 验证 Oracle（2026-09-03 15:20 CST）

- 本阶段只验证已稳定的 guarded routes 与 guarded SR forwarding branches，不实现 YU 的 symbolic
  traffic propagation、动态 weight normalization 或链路负载聚合，也不把逐故障枚举嵌入 symbolic
  convergence engine。
- 新增版本化 `0_symbolic_sr_policies.json`（schema
  `batfish-minesweeper-symbolic-sr-policies` version 1）。candidate 和 forwarding branch 的
  availability/selection guard 除原始可读字符串外，现保存精确的、与求解器无关的
  `BooleanGuardAst`；根级 `guardVariables` 使用与 symbolic control-plane export 相同的 canonical
  `LinkFailureKey` 和 `polarity=UP`，因此该 SR 文件可被独立、安全地重新读取。
- `SmtReachabilityTest.writeSymbolicRouteFiles()` 仅新增一次文件写入；已有 dataplane、SMT encoding、
  readable symbolic RIB 的生成逻辑没有修改。此修改位于用户已经有其他未提交修改的文件中，提交时
  必须只暂存新增 `0_symbolic_sr_policies.json` 的代码块。
- 新增独立脚本 `tools/validate_symbolic_route_failures.py`。脚本以完整 symbolic run 为 base，对每个
  all-up/单链路失败 assignment 求值 MAIN candidate 的 selection AST，再与对应故障配置重新运行
  Batfish 得到的 `0_data_plane.txt` 比较；同时投影 base 的 guarded SR forwarding branches，并与对应
  场景重新运行 pipeline 得到的 SR branches 比较。route 与 SR 文件若对同一变量给出不同 link
  identity 或极性，脚本立即失败，禁止从变量名猜测语义。
- MAIN 比较字段为 Node、VRF、Prefix、Protocol、NextHopIP、NextHopInterface、Metric、AD、Tag；
  `0_data_plane.txt` 中的 NextHop 设备名是由显示器从下一跳解析得到的冗余列，当前不作为独立身份字段。
  SR 比较覆盖 policy/candidate identity、preference、weight、segment list、label stack、guarded next-hop
  sequence、link dependencies 和 terminal endpoint。
- 典型运行方式（每个目录必须由当前 pipeline 重新生成，旧 schema/version 会被明确拒绝）：

  ```text
  python3 tools/validate_symbolic_route_failures.py \
    --base smts/smt_output_0055 \
    --scenario all-up=smts/smt_output_0055 \
    --scenario r1_r2=smts/smt_output_0055_r1_r2 --down r1_r2=r1_r2 \
    --scenario r1_r3=smts/smt_output_0055_r1_r3 --down r1_r3=r1_r3 \
    --scenario r1_r4=smts/smt_output_0055_r1_r4 --down r1_r4=r1_r4 \
    --scenario r2_r4=smts/smt_output_0055_r2_r4 --down r2_r4=r2_r4 \
    --scenario r3_r4=smts/smt_output_0055_r3_r4 --down r3_r4=r3_r4 \
    --report smts/smt_output_0055/0_failure_validation.json
  ```

- 2026-09-03 15:20 CST：Python AST/全 up/单链路失败投影测试 2 个全部通过；parser-driven SR
  pipeline 定向 Bazel 测试通过。现有 `smt_output_0055*` 是 Stage 9.1.1 之前生成的旧输出，缺少新的 SR
  JSON（base control-plane 也仍是 schema v1），不能伪称完成真实五场景验证；必须先分别重新运行五个
  concrete failure 配置，再执行上述独立脚本。
- 2026-09-03 15:38 CST：完整 Minesweeper 回归运行 281 个测试，280 个通过；唯一失败仍是用户工作区
  未跟踪的 `TrafficDemoSingleLinkFailureTest`，失败点是其 demo 配置中旧 SR extension syntax 无法被
  Cisco parser 接受，尚未进入本阶段代码。主源码 PMD 仍仅有原先 34 条 Graph/旧 SMT 基线违规，
  本阶段修改的 symbolic route/SR 文件没有新增 PMD 违规。

## Stage 9.2 执行记录：真实 0/1-link oracle（2026-09-04 17:39 CST）

- 用当前 pipeline 重新生成 all-up 与单链路失败目录。无 SR 的 control-plane 导出被 Jackson
  `NON_EMPTY` 省略空 `guardVariables`/`records`；验证脚本把缺省数组视为空列表，合成测试增至 3 个。
- 四路由器 BGP（`smt_output_0056` 为 base，`0058`–`0062` 为五条单链路失败）：6/6 MAIN RIB 与
  SR branches 匹配。该网络没有 SR policy，SR 对比是空对空。
- SR-TE demo（`smt_output_0063` 为 base，`0064`–`0069` 为 `a_d`/`a_s`/`a_x`/`b_d`/`b_s`/`d_x`）：
  7/7 MAIN RIB 与 SR forwarding branches 匹配。报告写入
  `smts/smt_output_0056/0_failure_validation.json` 与
  `smts/smt_output_0063/0_failure_validation.json`（`smts/` 仍 gitignore）。
- 为复现 SR-TE 失败场景，新增 parser-driven 快照 `networks/tolerance_sr_te_demo_1_*`，两端接口
  `shutdown`。四路由器失败快照 `networks/tolerance-symbolic-route_1_*` 一并纳入版本库。
- 本记录不宣称 YU Algorithm 1/2。oracle 只证明：把 base SRIB/SR 的 selection AST 赋成 0/1
  故障后，与把对应链路 shutdown 再跑 pipeline 得到的 concrete MAIN/SR 一致。
- 回退本执行记录与快照：`git revert` 本提交。

## Stage 10.0 流量层原型与 YU Algorithm 1/2 差距（2026-09-04 18:00 CST）

### 本阶段做了什么

- traffic 不进入 Algorithm 1 控制面收敛。`traffic.json` 仍只提供 demand、链路容量和权重参数
  `h`；pipeline 继续只输出 guarded MAIN/SR。
- 新增 `tools/traffic_execution.py` 两条引擎，共用 per-link 仿射负载 `const + coeff·h`：
  1. 手动枚举：故障目录的 `0_data_plane.txt` 逐跳 LPM/ECMP，加上该目录重算的 SR
     forwarding branches，按 `h`/`100-h` 归一化；
  2. 赋值后的 symbolic 执行：对 all-up SRIB/SR 的 `selectionGuard` AST 做同一故障赋值，再
     走同样的逐跳与加权拆分。
- `tolerance_sr_te_demo` 七个 0/1-link 场景两条引擎负载公式一致；`d_x` 下 `load(a_d)=20+0.8h`，
  容量 95 得到 `h <= 93`，与 `traffic.json` 的 `expectedSubspecWithinDomain` 一致。
- auto-netsubspec 增加独立轨道 `9_traffic_subspec.py`，读取 `0_traffic_loads.json` 写出
  `Psi(h)`。不接入现有 BGP SpecLens 步骤 1–6。

### YU Algorithm 1 在论文中做什么

YU §4.3 Algorithm 1 `simulate(f)` 对**一条流**做一次符号化执行，覆盖全部故障，而不是按故障
枚举：

1. 状态是矩阵 `M[l, S]`：流 `f` 在链路 `l` 上、且报文带 label stack `S` 时的 symbolic traffic
   fraction（STF），公式的自变量是链路/节点存活变量。
2. 构造进入源路由器 `R` 的伪入边 `l_R`，令 `M0[l_R, ∅] = 1`（100% 流量、无标签）。
3. 按跳迭代 `i = 1 … I`（`I` 由 TTL 决定）：对每个路由器 `R` 和每个 stack `S`，把进入 `R` 且
   stack 为 `S` 的入边 STF 求和得到 `ω`，再调用 Algorithm 2 的 `forward(R, f, S, ω)` 累加到
   `M_i`。
4. 收敛或达到 TTL 后返回 `M_I`。链路负载 STL 为 `τ_l = Σ_{f,S} V_f · M_f[l,S]`。
5. TLP 判定（§4.5）在**全体故障变量**上求解
   `(Σ x_i ≤ k) ∧ (τ_l(x) > v2 ∨ τ_l(x) < v1)`，一次检查任意 `k` 故障，不枚举 `C(n,k)`。

因此 Algorithm 1 的本质是：带 label-stack 维的符号化数据面固定点，输出的是故障变量上的函数。

### YU Algorithm 2 在论文中做什么

YU §4.4 Algorithm 2 是单路由器的 `forward`，也必须返回符号化矩阵：

1. `S = ∅` 则 `forwardIp`，否则 `forwardSr`。
2. **Route selection** `s_r`：dstip 不匹配则为 0；否则 `g_r ∧ ¬g_{r'}`（所有更优且匹配的
   `r'`）。这是布尔公式，不是赋完值再看表。
3. **ECMP** `c_r = s_r / Σ_{r'} s_{r'}`。分母是“当前有多少条被选中的等价规则”的**符号计数**，
   随故障变化；不是先列出 next-hop 再 `1/n`。
4. **SR 加权** `c_p = (g_p · w_p) / Σ_{p'} (g_{p'} · w_{p'})`。分子分母同时含路径 guard 和权重，
   仍是故障变量上的有理式。
5. **Route iteration** `VIGP_nip[l] = Σ_{r: nh_r=l} c_r^{nip}`：间接 next-hop 要再查 IGP，把
   流量摊到直连边上。
6. **`resolveNhIp`**：若 `(f, nip)` 命中 SR policy，则 `M[l,S] = ω · Σ_{p: stack(p)=S} VSR_p[l]`，
   其中 `VSR_p[l] = c_p · VIGP_{first(p)}[l]`——先按权重选 path，再对 path 的第一跳做 IGP
   解析，并**压入 label stack**。未命中 SR 则只更新 `M[l, ∅]`。
7. **`forwardSr`**：令 `S = [R1,…,Rj]`。若当前路由器就是栈顶 `R1`，弹出后递归
   `forward(R, f, rest, ω)`；否则按 `R1` 的地址做 `VIGP`，流量带着**同一个 stack** 走向第一跳。
   图 7 的例子：iBGP 间接 NH 到 F，命中 SR 后在 D 上把流量分成 `[E,F]` / `[C,F]` 两条栈，再
   用 IS-IS 解析 E/C。

Algorithm 2 的本质是：把 RIB 查找、ECMP、间接 NH、SR policy 和 label 转发全部写成对 `M[l,S]`
的符号化更新。

### 当前实现对着 1/2 还缺什么

控制面（Hoyan Algorithm 1 / 本仓库 Stage 1–9）已经提供 YU 当作输入的 guarded RIB 与 guarded
SR：MAIN 的 `selectionGuard` 对应单前缀上的 `s_r`。差距全部在 **traffic 层**：

| YU 构件 | 当前 `traffic_execution.py` | 差距 |
| --- | --- | --- |
| `M[l, S]` 矩阵 | 只有 `load[l] = const + coeff·h` | 无 label-stack 维，无故障变量上的 STF 公式 |
| Algorithm 1 跳迭代到 TTL | 按赋值 DFS 到目的地；SR 一次把 path 上所有链路加上负载 | 不是符号化固定点；不能表达环、TTL、中途改栈 |
| 一次执行覆盖全部故障 | 对每个 0/1 赋值分别跑 | 仍是 enumeration，复杂度随 `C(n,k)` 增长 |
| `s_r` 布尔公式 | 先 `evaluate(selectionGuard)` 再查表 | 赋值后语义对，不是可组合的符号公式 |
| `c_r = s_r / Σ s_{r'}` | 选出 next-hop 后 `1/n` | 无符号除法；不能把“ECMP 成员数随故障变”编进一个公式 |
| `c_p = g_p w_p / Σ g_{p'} w_{p'}` | 先看哪些 path 存活，再对 `h` 做仿射 | 在**给定赋值**下与论文一致；不是 `g` 与 `w` 的联合有理式 |
| `VIGP` / `VSR` | 无 | 间接 NH、第一跳 IGP 解析未实现 |
| `resolveNhIp` 命中 SR 后压栈 | SR 被建模成源节点的独立 `SR_POLICY` flow | 没有“IP 查到间接 NH → 套 SR policy → 带栈转发” |
| `forwardSr` 弹栈 / 向栈顶做 IGP | 用 selectionGuard 里的链路变量走出一条 Adj-SID 路径 | 只适用于 explicit Adj-SID 且 guard 恰好是路径边的合取；Node-SID / 中途 IGP 绕行会错 |
| MTBDD 与 `k`-failure equivalence（§5） | 无 | 无紧凑 STL 表示，也无有界故障域化简 |
| TLP SMT：`Σ x_i ≤ k ∧ τ_l ∉ [v1,v2]` | 枚举场景后对 `h` 求交仿射不等式 | 解释的是权重子规约，不是任意 `k` 下的负载违反搜索 |
| iBGP 间接 NH（图 7） | 未实现 | 当前 demo 是 IS-IS + headend SR policy |

### 当前实现**可以**声称的边界

- 对 `tolerance_sr_te_demo`、`k∈{0,1}`、explicit Adj-SID、两条同 preference 的 SR candidate、
  以及 `h`/`100-h` 权重，逐故障 concrete dataplane 与 SRIB 赋值后的逐跳负载公式一致。
- 由此导出的故障感知子规约 `h <= 93` 与 demo 设计意图一致。
- **不能**声称已实现 YU Algorithm 1、Algorithm 2、MTBDD、或任意 `k` 的 TLP 判定。

### 下一阶段若要对齐论文，最小闭环

1. 在 Java traffic 层实现 `M[l,S]` 与 Algorithm 2 的 `forwardIp` / `resolveNhIp` / `forwardSr`，
   STF 用可求值的 guard AST + 有理式（或 MTBDD），不要先枚举故障。
2. Algorithm 1 按跳迭代到固定点/TTL；用 Stage 9.2 的 concrete 场景作赋值投影基线。
3. 把 `c_p` 保留为 `(g_p·w_p)/Σ(g·w)`，`h` 作为权重符号而不是“先存活再仿射”的后处理。
4. TLP 检查走 `Σ x_i ≤ k ∧ τ_l ∉ [v1,v2]`；子规约再在该 STL 上松绑 `h`。

- 实现文件：`tools/traffic_execution.py`、`tools/tests/test_traffic_execution.py`；
  auto-netsubspec 侧 `9_traffic_subspec.py` 在独立仓库提交。
- 回退：`git revert` 本提交。

## Stage 10.1 symbolic traffic execution 骨架（2026-09-04 18:25 CST）

- 按 Minesweeper 原结构分两包，不按 `symbolicroute` 的 AI 风格拆生命周期类型。对照是：
  `Graph`/`GraphEdge` 负责从配置解析拓扑；`smt.Encoder`/`EncoderSlice` 只消费 `Graph`，不读文件。
- `org.batfish.minesweeper.symbolictraffic.parse`：**使用解析**。`TrafficGraph` /
  `TrafficGraphEdge` / `TrafficFlow` 是 traffic 层的 Graph。JSON（`fromTrafficJson`）和 Batfish
  snapshot（`fromBatfish` / `fromConfigurations`）入口已挂上，实现留空。内存构造给测试和后续
  Algorithm 1 用。
- `org.batfish.minesweeper.symbolictraffic.execution`：**不使用解析**。`SymbolicTrafficExecution`
  对应 Encoder（Algorithm 1 `simulate(f)`）；package-private `SymbolicTrafficForwarding` 对应
  EncoderSlice（Algorithm 2 `forward`）；`SymbolicTrafficMatrix` 是 `M[l,S]`；
  `SymbolicTrafficLoad` 是 `τ_l`；`TrafficLabelStack` 是栈列。算法体全部
  `UnsupportedOperationException`，等 Algorithm 1 指导后再写。
- 未修改 `Graph`/`Encoder`/`EncoderSlice`/`PropertyChecker`、`symbolicroute`、`symbolicsr`、
  BUILD（已有 `src/main/**/*.java` glob）。未实现 JSON 解析、未实现 YU 1/2。
- 测试：`TrafficGraphTest` 覆盖内存图索引与 JSON 入口未实现；`SymbolicTrafficExecutionTest` 覆盖
  空栈与 `simulate`/`forward` 未实现。不把 Python `traffic_execution.py` 当作本层实现。
- 回退：`git revert` 本提交。

## Stage 10.2 Algorithm 1 `simulate(f)`（2026-09-08 16:20 CST）

- 实现 YU Algorithm 1 的跳迭代，**不实现** Algorithm 2 `forward`。默认 `SymbolicTrafficForwarding`
  仍抛 `UnsupportedOperationException`；测试通过 package-private 构造注入替身 `forward` 来核对循环。
- `simulate(f)` 按 listing：构造伪入边 `l_R`（不改 `TrafficGraph`），`M0[l_R, ∅] = 1`；第 `i`
  轮新建 `M_i`，对每个路由器和 `M_{i-1}` 中出现的栈 `S`，令 `ω = Σ incoming M_{i-1}[l,S]`（源路由器
  计入 `l_R`），再 `M_i += forward(R, f, S, ω)`；返回 `M_I`（恰好 `I` 跳的 STF，不是 hop 求和）。
  `I` 默认 255（TTL），测试用更小的 `I`。
- `SymbolicTrafficFraction` 目前是常数格点（Algorithm 1 的 `0`/`1` 与加法）。`trafficLoads`/`τ_l`
  仍未实现。
- 测试：I=1 把入流量放到出边；I=2 返回第二跳而非第一跳；菱形汇聚处 `ω` 为入边之和；栈作为 `M`
  的列传到下一跳；sink 的 `forward` 为空矩阵；未注入时 `forward` 仍未实现。
- 未修改 `Graph`/`Encoder`/`PropertyChecker`、`symbolicroute`、`symbolicsr`、BUILD。
- 回退：`git revert` 本提交。

## Stage 10.3 Algorithm 2 encodings and `forward`（2026-09-08 16:40 CST）

- 按 YU §4.4 实现 route selection、route iteration 与 Algorithm 2，不改 `Graph`/`Encoder`。
- `RouteSelectionEncoding`：`s_r = 0`（dst 不匹配）否则 `g_r ∧ ∧_{r' ≺ r} ¬g_{r'}`（更长前缀更优，同前缀更低
  preference 更优）；`c_r = s_r / Σ s_{r'}`（分母为 0 则 0）。
- `RouteIterationEncoding`：`VIGP_nip[l] = Σ_{nh_r=l} c^{nip}_r`；`c_p = (g_p w_p)/Σ(g w)`；
  `VSR_p[l] = c_p · VIGP_{ip}[l]`。
- `SymbolicTrafficForwarding`：`S=∅` → `forwardIp`（直接 NH 写 `M[l,∅]+=ω c_r`，间接 NH 走
  `resolveNhIp`）；命中 SR policy 则按 path 栈写入 `ω · VSR`；否则 `M[l,∅]=ω · VIGP`。`forwardSr`：
  当前节点为栈顶则弹出后递归 `forward`，否则带着同一栈对栈顶地址做 `VIGP`。
- `SymbolicTrafficFraction` 支持常数、guard、加减乘除，可在赋值下求值。空 RIB 的 `forward` 返回空矩阵。
- 测试覆盖 `s_r`/`c_r`、LPM、`VIGP`/`VSR`、直接/间接 NH、SR 压栈、弹栈、向栈顶 IGP。Algorithm 1 替身测试保留。
- 回退：`git revert` 本提交。

## Stage 10.4 Algorithm 1/2 审查与完备测试（2026-09-08 17:15 CST）

- 审查结论（对照 YU listing，不改返回语义）：Algorithm 1 仍返回恰好 `I` 跳的 `M_I`，伪入边 `l_R` 只在
  `simulate` 局部构造，`ω` 跳过图里已有的 pseudo incoming，只在源路由器计入 `l_R`。栈集合取自
  `M_{i-1}` 的非零列。`trafficLoads`/`τ_l` 仍未实现，也不做论文散文里的不动点早停。
- Algorithm 2：`VIGP` 跳过不匹配 `nip` 的规则（与把它们的 `c_r` 当成 0 再累加等价，矩阵更稀疏）。
  空节点列表的 `SrPolicy.Path` 拒绝构造。`≺` 仍是更长前缀优先、同前缀更低 preference 优先。
  IGP 优选/备份互斥（`s_high=y`、`s_low=¬y`），不把 Figure 7 印刷式 `0.75y+0.25` 当作互斥 IGP 的金标准。
  `fromGuard` 对不含变量的 AST 做常数折叠（`true ∧ ¬true` → 0），使 LPM 落败规则的 `s_r=0` 成为常数
  0 并从矩阵中丢掉，且不调用 Z3 `Expr.isFalse()`。
- 测试补齐：`s_r` 三档 preference、等 preference 不 `≺`、三路 ECMP、分母为 0；`VIGP` 优选/备份、
  非匹配前缀不入向量、path guard 下调权；`forwardIp` LPM/两路 ECMP/优选失效/ω=0；`resolveNhIp`
  nip 不匹配 SR 走 VIGP、两 path 不同栈 0.75/0.25、同栈相加、缺 first-node 地址则跳过；
  `forwardSr` 弹栈后余栈非空时对下一标签做 VIGP。分数式覆盖 AND/NOT/OR 与赋值下除零。
- 新增 `SymbolicTrafficSimulateForwardingTest`：Algorithm 1 套真实 Algorithm 2（直线 I=1/2/3、
  优选 failover、ECMP 菱形第二跳、SR 压栈后再弹余栈）。Algorithm 1 替身测试保留，并覆盖默认 TTL=255
  与图中残留 pseudo incoming 不抬高 `ω`。
- 未修改 `Graph`/`Encoder`/`PropertyChecker`、`symbolicroute`、`symbolicsr`、BUILD，不改
  `tools/traffic_execution.py`。
- 回退：`git revert` 本提交。

## Stage 10.5 删除 Python 流量原型（2026-09-08 17:15 CST）

- `tools/traffic_execution.py` 不是 YU Algorithm 1/2：两条都是按故障赋值再逐跳/拆分的 walker，
  输出 `const + coeff·h`，没有 `M[l,S]`、符号 `c_r`/`VIGP`/`forwardSr`。Java
  `symbolictraffic.execution` 已实现 listing 中的 `simulate`/`forward`，不再依赖该脚本。
- 删除 `tools/traffic_execution.py` 与 `tools/tests/test_traffic_execution.py`。不改
  `Graph`/`Encoder`/`BUILD`。`trafficLoads`/`τ_l` 与 `0_traffic_loads.json` 仍待 Java 实现。
- auto-netsubspec 的 `9_traffic_subspec.py` 只读 JSON、不 import 本脚本；其注释里的生产者路径作废，
  在独立仓库另改。
- 回退：`git revert` 本提交。

## Stage 10.6 跳累计 STF、伪入边与 SR path 约束（2026-09-08 17:30 CST）

- Algorithm 1：`simulateHopI(f)` 保留 listing，返回恰好 `I` 跳的 `M_I`。`simulate(f)` 改为真实链路
  上的 `Σ_{i=1}^{I'} M_i`（不含 `l_R`），供后续 `τ_l` 使用。`I'` 在 in-flight 矩阵为 0 时结束；
  **不以** `M_i = M_{i-1}` 早停（环上非零不动点会少计 TTL 穿越）。`simulateHopI` 跑满 `I` 跳。
- 伪入边：图里已有的 pseudo incoming 仍不计入 `ω`；构造的 `l_R` **只在 hop 1** 注入源路由器，避免
  第二跳把源再灌一次 1。
- Algorithm 2：`g_p` 只进 `c_p`，Node-SID 第一跳仍乘 `VIGP`；Adj-SID 要求 source=当前路由器并走邻接，
  不把 path guard 当成转发 guard。Node-SID 等于 headend 时弹栈，空余栈的 IP 查找不再套同一 SR
  policy。`SrPolicy.Path`：segment 非空且非 null、weight>0、path id 不可重复；同 stack 仍允许（VSR
  相加）。缺 Node-SID loopback 地址则该 path 为 0。
- `trafficLoads` 仍未实现，javadoc 写明必须用累计 `simulate` 而不是 `M_I`。
- 测试：累计直线/菱形/SR；`l_R` 不重注入；listing 不早停；ECMP/加权 SR 质量守恒；path guard 与 IGP
  guard 分离；headend-only stack；Adj-SID source 约束。
- 未修改 `Graph`/`Encoder`/`PropertyChecker`、`symbolicroute`、`symbolicsr`、BUILD。
- 回退：`git revert` 本提交。

## Stage 10.7 typed SR stack 与 policy 匹配（2026-09-08 17:45 CST）

- 审计确认：`TrafficLabelStack` 只存 String，Adj-SID 只有第一跳能碰巧工作；首个 Adj 不 pop；空栈 IP
  会再次套 SR；`matches` 在 flow 的 color/name 为 null 时仍命中带 color/name 的 policy；`div(0)=0`
  已实现但未写进契约；direct NH 的链路可用只在 `g_r` 里，Adj 边原先只用 `c_p`；多 policy 取第一条；
  空 policy/null 构造与可变内部 list 未拦；Algorithm 1 对 ω=0 仍调 `forward`。
- `TrafficLabelStack` 改为保存 typed `SrPolicy.Segment`。Adj-SID 在 owner 上 pop，余栈带着
  adjacency identity 传到对端；后续 Adj 不再被当成 Node-SID。
- 弹空栈后的 IP 查找不再套 SR（`applySr=false`）。`matches`：policy 声明了 color/name 则 flow
  必须提供相同值。`div(0)` 在构造期与求值期都是 0。Adj 边再 AND segment guard 以及同边 direct
  RIB 的 `g_r`。同 specificity 的多 policy 命中抛歧义。空 policy / null 字段拒绝；path 与 RIB
  列表防御拷贝。Algorithm 1 跳过 syntactically zero 的 arrival。
- 未修改 `Graph`/`Encoder`/`PropertyChecker`、`symbolicroute`、`symbolicsr`、BUILD。
- 回退：`git revert` 本提交。

## Stage 10.8 Algorithm 1 `simulate(f)` 清单 A1–A6（2026-09-08 17:50 CST）

- 审计：A2 每跳独立 `M_i`、只读 `M_{i-1}`、按入边同栈求和、跳过图内 pseudo、`l_R` 仅 hop 1
  注入，已对齐。A3 `simulateHopI` 跑满 `I`、返回 `M_I`、不求和，已对齐。A5 累计只在
  in-flight 为零时早停，不用 `M_i=M_{i-1}` 或累计不变。A4 已排除 `l_R`/`M_0`。
- 缺口：null flow / 源不在图里原先静默得到零矩阵；环上累计可大于 1 未写进 javadoc、未测；
  第一跳空流量的 `_lastCompletedHops=1` 未约定；未写明只建模链路穿越、TTL 余量丢弃、空
  `forward` 即 drop 且不会再出现。
- 修复：`simulate`/`simulateHopI` 拒绝 null flow 与不在图中的 source；路由器集合只读快照；
  javadoc 写明累计格子是 hop-traversal、环上可 `>1`、TTL 到期不继续传播、无 terminal-state
  矩阵。`getLastCompletedHops`：listing 恒为 `I`；累计在第一跳为空时为 `1`。
- 测试：null/缺源；两次 `simulate` 不共享矩阵且不改图；A↔B 环 `I=4` 累计为 2；短 DAG 的
  `M_I=0`；sink 空 forward 不复活；第一跳空 RIB 的 hops=1。
- 未修改 `Graph`/`Encoder`/`PropertyChecker`、`symbolicroute`、`symbolicsr`、BUILD。
  `trafficLoads` 仍未实现。
- 回退：`git revert` 本提交。

## Stage 10.9 双引擎接入主 pipeline（2026-09-08 19:50 CST）

- 有 `traffic.json` 时主入口走完整链路：解析 `TrafficGraph` → 控制面 guarded RIB/SR → **两条并行
  流量引擎**，互不替代。
- YU 引擎：`GuardedTrafficForwarding` 把 MAIN/SR 编成 `ForwardingRule`/`SrPolicy`，Algorithm 1
  对每条 flow 做累计 `simulate`，`trafficLoads` 编码 `τ_l = Σ V_f M_f[l,S]`，写出
  `0_symbolic_traffic_loads.json`。显式 MPLS label 经 SID DB 还原为 typed Adj/Node-SID。
- Tolerance/原引擎：`ConcreteTrafficExecution` 在一份 Batfish dataplane 上做 LPM/ECMP 与
  headend SR 加权拆分，**不**构造 `M[l,S]`，写出 `0_traffic_loads.json`。Encoder SMT 仍按原
  pipeline 跑 reachability，但 ingress/dst 改为来自 traffic flows。
- `TrafficGraph.fromTrafficJson` 接受 `IP`/`SR_POLICY`/`SR`。未改 `Graph`/`Encoder`/
  `PropertyChecker` 实现体。
- 回退：`git revert` 本提交。

## Stage 10.10 目的地终止与 JSON 序列化卡死（2026-09-08 20:05 CST）

- `smt_tests` 60s 超时：Loopback/discard 原先被丢掉，D 上 ISIS 把流量送回，YU 跑满 TTL；写出
  `0_symbolic_traffic_loads.json` 时 `tau.toString()` 调用 Z3 `Expr.toString()`，公式树爆炸。
- `ForwardingRule.terminal`：本地/discard/对不上 traffic 边的接口路由仍参与 `≺`，但不写真实链路。
- `SymbolicTrafficFraction.toString` 改为 AST 文本，不再走 Z3。
- 未修改 `Graph`/`Encoder`/`PropertyChecker`、BUILD。
- 回退：`git revert` 本提交。

## Stage 10.11 τ JSON 按 DAG 写出，禁止展开共享公式（2026-09-08 20:15 CST）

- `smt_tests` 在 36s 以 `OutOfMemoryError` 失败：Stage 10.10 不再调 Z3 `Expr.toString()`，但
  `tau.toString()` 仍把 `PLUS`/`TIMES` 当树递归拼接。Algorithm 1 累计是共享 DAG（每跳
  `acc = acc + M_i`，备份 ISIS 在 guard 下会跑满 TTL），展开后字符串指数级，堆爆在
  `SymbolicTrafficFraction.toString`。
- 常量/单 guard 仍写标量；复合公式写 `{root, nodes}`，`toString()` 同样按节点 id 线性打印。
  40 次 `acc=acc+acc` 的字符串长度有上界。`fromGuard` 把 `x ∧ ¬x` 和 `true` 吸收折成 0/1，避免
  恒假 `s_r` 在 TTL 上堆出十万节点；DAG 超过 2048 个节点时 JSON 只保留计数。
- 未修改 `Graph`/`Encoder`/`PropertyChecker`、BUILD。
- 回退：`git revert` 本提交。

## Stage 10.12 Algorithm 1 文本报告与 SR policy txt（2026-09-08 20:50 CST）

- `0_symbolic_sr_policies.txt`：与 JSON 成对的 SR forwarding-branch 表。
- `0_traffic_graph.txt` 标明只是解析后的输入。Algorithm 1 写出
  `0_symbolic_traffic_execution.txt`：先 `M_f[l,S]`，再 `Σ_S M_f[l,S]`，再
  `τ_l = Σ_{f,S} V_f · M_f[l,S]`。`simulateAll()` 保留 per-flow 矩阵。TLP SMT 尚未接入。
- 未修改 `Graph`/`Encoder`/`PropertyChecker`、BUILD。
- 回退：`git revert` 本提交。

## Stage 10.13 初始 traffic.json 不含 symbolic 权重（2026-09-08 21:50 CST）

- `traffic.json` 只保留 demand、链路容量、flow 与 TLP 性质类型。删除 `weightVariable`
  （`h` / `100-h`）和 `expectedSubspecWithinDomain`。SR 权重用配置里的具体 50/50。
  解开哪个 weight、求 `Psi(h)` 属于 Verifying TLPs / 子规约，不进 Algorithm 1 输入。
- 未修改 `Graph`/`Encoder`/`PropertyChecker`、BUILD。
- 回退：`git revert` 本提交。

## Stage 10.14 Algorithm 1 输出对齐 YU Figure 5（k-failure KREDUCE）（2026-09-08 22:10 CST）

- 论文执行完是紧凑 STF：Figure 5 的 `1*x1 + 0.5*¬x1¬x2¬x3`，Figure 7c 的 `0.75y` 矩阵。先前
  `0_symbolic_traffic_execution.txt` 对 IP 流写出 `dag(75k nodes)`，并把 2-failure 环路质量
  累计满 TTL，与例子不符。AllUp 数值碰巧对，公式不是 YU 的输出。
- `traffic.json` 的 `failureModel.maxFailures` 读进 `TrafficGraph`。Algorithm 1 每跳对
  `M_i` 做 §5.2 `k`-failure 等价多项式（Möbius：`Σ_{|S|≤k} α_S Π (not x)`）。k=1 下 IP 的
  `M[d_x]=d_x`、`M[a_x]=M[a_d]=(not d_x)`，多故障环路项变为 0，迭代在交付后停止。
- 报告用 infix（与 Figure 5 同类），共享 hop-DAG 仍不展开。未实现 MTBDD。
- 未修改 `Graph`/`Encoder`/`PropertyChecker`、BUILD。
- 回退：`git revert` 本提交。

## Stage 10.15 回退到 smt_output_0064 输入/输出（2026-09-09 13:05 CST）

- 今天 0066/0068/0070 坏掉：`traffic.json` 去掉了 `failureModel`，Algorithm 1 不再做 k=1
  约简，IP 流又变成 `dag(75k nodes)`；测试也不再写 `0_traffic_graph.txt` /
  `0_traffic_loads.json` / `0_symbolic_sr_policies.txt`。
- 恢复 0064 的 `traffic.json`（含 `failureModel.maxFailures=1`）、图文本、concrete JSON、
  SR policy txt，以及共享 DAG 不展开 infix。
- 未修改 `Graph`/`Encoder`/`PropertyChecker`、BUILD。
- 回退：`git revert` 本提交。
