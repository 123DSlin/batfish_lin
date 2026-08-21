# Symbolic Route Review Guide

Use this checklist when reviewing every symbolic-route change.

## 中文审查清单

### 公共架构

- 核心代码是否仍然不依赖 BGP/OSPF 专有属性？
- guard 的具体表示是否完全隐藏在 `RouteGuard` 后？
- guarded concrete route 是否与 Minesweeper 的 SMT route record 保持分离？
- 集合是否做了防御性复制，并只暴露不可变视图？
- route/message identity 是否足以稳定支持依赖追踪和撤回？

### Hoyan 语义

- RIB 存在条件是否与动态计算的选择/导出条件明确区分？
- 较低优先级路由的导出条件是否排除了所有严格更优路由的存在条件？
- 链路和节点存活条件是否在正确的传播边界加入？
- 较优路由晚到时，系统能否缩小已经传播的 guard？
- 删除和 guard 变化能否级联传播，而非仅支持新增消息？
- equal-preference 路由是否保留了 traffic execution 所需的不同 next hop 信息？

### 协议复用与测试

- adapter 是否尽量调用 Batfish 的 policy、session 和 route preference 逻辑？
- 若必须重新实现协议行为，是否有与 Batfish 结果对比的 differential test？
- BGP 假设是否被隔离，避免进入 OSPF 或公共代码？
- 是否测试不同消息到达顺序，并将符号结果在具体故障赋值下与 Batfish 对比？
- 新回归是否与原有基线失败明确区分？

### 审计记录

- 日志是否列出全部变更文件和不明显的设计决定？
- 限制是否被明确记录，而不是只隐藏在 TODO 中？
- 是否记录实现提交、审计提交、远端状态和回退命令？

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
