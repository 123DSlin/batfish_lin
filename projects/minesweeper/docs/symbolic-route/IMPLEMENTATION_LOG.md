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
