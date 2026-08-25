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
