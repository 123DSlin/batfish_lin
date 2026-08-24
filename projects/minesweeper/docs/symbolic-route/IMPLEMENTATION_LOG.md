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
