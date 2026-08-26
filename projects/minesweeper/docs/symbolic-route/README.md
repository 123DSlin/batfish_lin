# Symbolic Route Integration

This directory records the design and implementation history of the YU/Hoyan-style symbolic route
simulator being integrated into Minesweeper.

## 中文说明

本目录记录 YU/Hoyan 风格的 symbolic route（符号路由）模拟器如何集成到 Minesweeper，
同时保留每个开发阶段的设计依据、测试结果、Git 提交和回退方法。英文部分用于保持术语
和代码接口的一致性，中文部分用于帮助理解设计与审计实现。

### 核心语义

符号路由不是把路由协议的所有属性都改成符号变量，而是将两类信息组合起来：

1. Batfish 已经计算或表示的具体路由属性，例如前缀、管理距离、metric、BGP local
   preference 和 AS path；
2. 描述该路由在什么拓扑或故障条件下存在的符号 guard（布尔条件）。

`R(r_i)` 表示路由 `r_i` 在 RIB 中存在的条件。若 `r_1 ... r_(i-1)` 都严格优于
`r_i`，则 `r_i` 能够被选择并向外传播的条件为：

```text
E(r_i) = R(r_i) AND NOT R(r_1) AND ... AND NOT R(r_(i-1))
```

路由经过链路 `l` 传播时，还必须满足链路存活：

```text
I(message, receiver) = E(message, sender) AND alive(l)
```

因此，RIB 中的存在条件和动态计算的选择/导出条件必须分开。较高优先级路由晚到时，
较低优先级路由已经传播出去的 guard 可能缩小，甚至需要撤回并级联更新下游节点。

### 架构原则

- 核心模型不依赖 BGP 或 OSPF 的专有字段，协议差异由 adapter（适配器）处理。
- guard 的具体实现隐藏在 `RouteGuard` 接口后，后续可以接入 Z3、BDD 或其他表示。
- 尽量复用 Batfish 已有的具体协议、路由策略、session 和路由优先级语义。
- guarded concrete route 与 Minesweeper 已有的 SMT `SymbolicRouteBase` 分开；后者将在
  tolerance 编码和一致性校验阶段与前者连接。
- 更新模型必须支持新增、删除以及 guard 变化，不能只做单调增加的传播。

### 当前进度

Stage 1–3 已完成协议无关数据模型、Z3 guard algebra、guarded RIB、FIFO 收敛、传播依赖和
recursive withdrawal。Stage 4 已接入 connected/static 和当前验收范围内的 IPv4 eBGP Batfish
协议语义，并提供一次运行得到全网 router/VRF Symbolic RIB 的 typed pipeline。OSPF、IS-IS、
iBGP、SR、`k`-failure pruning 和 tolerance 后续 SMT 绑定尚未实现。详细记录见
[`IMPLEMENTATION_LOG.md`](IMPLEMENTATION_LOG.md)，代码审查要点见
[`REVIEW_GUIDE.md`](REVIEW_GUIDE.md)。

The records serve two purposes:

1. explain the intended semantics and architecture before protocol implementations are added; and
2. provide an audit trail linking each implementation stage to files, tests, limitations, and Git
   commits.

## Intended semantics

The simulator follows Hoyan's guarded route propagation model, which YU consumes as guarded RIBs.
A route has concrete protocol attributes and a symbolic topology condition describing when it is
present. Route preference is computed from the concrete attributes and is independent of the guard.

For a RIB route `r_i`, with strictly higher-priority routes `r_1 ... r_(i-1)`, its export condition
is:

```text
E(r_i) = R(r_i) AND NOT R(r_1) AND ... AND NOT R(r_(i-1))
```

Propagation over link `l` adds the link-aliveness condition:

```text
I(message, receiver) = E(message, sender) AND alive(l)
```

The implementation must support guard reductions and withdrawals when a higher-priority route
arrives after a lower-priority route has already propagated.

## Architecture boundaries

The core is protocol-neutral:

```text
symbolic route model
        +
guard algebra
        +
guarded RIB and propagation engine
        |
        +-- BGP adapter
        +-- OSPF adapter
        +-- connected/static adapters
        +-- redistribution
```

Core model classes must not directly depend on:

- BGP- or OSPF-specific route classes;
- Z3 `BoolExpr`;
- Minesweeper's SMT `SymbolicRouteBase` hierarchy.

Protocol adapters will reuse Batfish concrete route, policy, session, and preference semantics.
Minesweeper's SMT route records remain a separate representation used later for tolerance seed
encodings and consistency checks.

## Audit files

- [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md): append-only stage-by-stage implementation log.
- [REVIEW_GUIDE.md](REVIEW_GUIDE.md): invariants and questions to use during code review.
- [PAPER_ALIGNMENT.md](PAPER_ALIGNMENT.md): HoYAN/YU/tolerance guarded-RIB semantic audit.
- [PROTOCOL_PIPELINE.md](PROTOCOL_PIPELINE.md): currently executable protocol pipeline and scope.

Run the tolerance R1-to-R4 reachability question and generate its readable Symbolic RIB with
`./tools/generate_tolerance_symbolic_rib.sh`. `SmtReachabilityTest` creates the next available
`smts/smt_output_XXXX` directory. The same run writes the exact stable-RIB guard expressions to
`0_symbolic_routes_init.txt` and the logically equivalent, stronger Z3 display simplification to
`0_symbolic_routes.txt`.

## Git workflow

The working branch is `feature/yu-symbolic-route`, based on `tolerance-development` at
`1708bbda7c`.

Business-code changes are prepared and validated for review before they are committed. Audit
documents are maintained by the assistant in a separate commit and pushed to GitHub automatically.
Each stage records the implementation and audit commit hashes, verification results, known
limitations, and rollback commands.
