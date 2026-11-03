# 切片正确性实验目录

基于 `init_auto_symbolic_netsubspec` 复制 Stage 1–5、consistency、utils、tests 以及三个小型回归样例。原目录与 batfish 原始输出不修改。0083 输入独立保存在 fixtures/smt_output_0083。

## 运行

在工作区根目录，需 Python 3 和 PATH 中的 Z3 CLI（不依赖 z3 Python 包）：

```sh
python3 slice_validation/1_smt_slicer.py slice_validation/fixtures/smt_output_0083 --k 2
python3 slice_validation/2_consistency_checker.py slice_validation/fixtures/smt_output_0083 --k 2
python3 slice_validation/validate_slices.py --work-dir slice_validation/fixtures/smt_output_0083
cd slice_validation
python3 -m unittest discover -s tests -p 'test_validation_baseline.py'
python3 -m unittest discover -s tests -p 'test_symbolic_smt_slicer.py'
python3 -m unittest discover -s tests -p 'test_consistency_seed_modules.py'
```

## 新增基准与保守切片

`validate_slices.py` 保留原始配置、目的地址、故障限制及路由/转发约束，仅移出 reachable 相关性质机器。原始查询是寻找不可达反例，不能直接用来检查正常路由场景。

以本机路由与转发符号为根，在“断言—符号”无向超图上计算完整闭包，输出 closed_设备.smt2。保留竞争候选、邻居反馈与所有连通依赖，不引入自由边界。常量断言始终保留。它是正确性优先的参照实现，不替换原 Stage 1 的高压缩局部切片。

闭包之外约束与闭包符号不相交；逐场景检查遗漏部分可满足，建立闭包切片的全网扩展依据。不能将这类证明套用到原来的截断边界切片上。

0083 有七条物理链路，k=2 时枚举 29 个完整故障赋值。每个场景检查：

1. 完整网络行为基准是否 SAT，避免空模型造成蕴含检查假通过。
2. 闭包之外组件是否 SAT；完整网络是否可能违反旧设备切片约束（期望 UNSAT）。
3. 每个设备有有效 BEST 时，是否存在未被任何分支 guard 覆盖的状态（期望 UNSAT）。无路由场景不要求存在有效路由分支。
4. 对每条适用分支，完整网络加 guard 是否可实现；加预期行为是否相容。
5. 完整网络加 guard 加“预期行为的否定”是否 SAT。UNSAT 才说明该故障场景下所有完整网络解均满足描述，不再把一次 SAT 当作 guard 的全域正确性证明。

预期行为由 Stage 2 seed 的命名约束段读取；基准网络直接使用未经过 SeedBuilder 释放/删除约束的原始编码。基准以完整模型为裁判，可发现局部 seed 与全网行为冲突，但并非独立的协议实现，也不能证明 Minesweeper 自身语义完全正确。

结果保存在 results/0083/report.json，包括原文件 SHA256、各场景、分支、覆盖检查与切片大小。发现行为反例时输出可直接运行的 SMT2。UNKNOWN、超时、解析错误不能记 PASS。

## 保证范围

固定配置、单个输入目的地址、MAIN/BGP、最多 k 条物理链路故障。未证明任意配置变更、OSPF/ISIS、ECMP 全语义、SR Policy、流量容量、任意网络规模或端到端 reachable 切片的等价性。闭包切片在强耦合网络可能接近全量；进一步缩小应添加经完整模型证明的边界摘要。

原 Stage 2 的 PASS 仍是存在性检查；新基准作为额外严格验收门，不改变该 PASS 的原有定义。更改切片、binder 或 seed 后需重新生成 fixture 产物并重跑基准。

## 实际发现（2026-11-03）

历史 seeds 的29场景/290次分支适用性检查、116次覆盖检查及116次切片检查通过，无行为反例，结果保存于 results/0083_historical。它不能当作当前 JSON 验收。

当前输入重新生成时 Stage 1 失败：ISIS_L2 路由、a→s 接口映射缺失、协议 history 无法绑定。Stage 2 缺少切片时 FAIL；scope 失败且分支为空时仍打印“All eligible branches are consistent”的错误已修复。

实验版 Stage 2 记录 SMT 和 symbolic_route.json 的 SHA256。严格基准要求 Stage 2 PASS 且指纹匹配；历史检查必须显式加 --allow-historical-seeds。禁止通过过滤 ISIS 分支或删除冲突断言使检查假通过。

当前输入生成保守闭包切片：

```sh
python3 slice_validation/validate_slices.py --work-dir slice_validation/fixtures/smt_output_0083 --closed-only
```

该模式明确标记 branch_validation=NOT_RUN。当前 ISIS/MAIN 分支绑定与原始 SMT 的协议覆盖冲突尚未修复，需要取得同次运行的匹配输入，或实现并验证 ISIS 边界与 history 语义；不能宣称当前流程已经全部通过。

## 协议选择修复后的验收

生成端已增加 `buildSelected(..., SmtProtocolSelection.fromRuntime())` 入口。使用
`SMT_PROTOCOLS=bgp`、`SMT_SYMBOLIC=false`、`SMT_NETWORK=tolerance_sr_te_demo_bgp_x_b`、
`SMT_INGRESS=x`、`SMT_FINAL=d`、`SMT_DST=5.5.5.5/32`、`SMT_FAILURES=2`，通过
`//projects/allinone:smt_tests` 的 SmtReachabilityTest 在 generated/smt_output_0001
重新导出了匹配的 SMT 与 JSON。没有修改历史0083。此结果取代上一节对新输入尚未验收的状态。

新 JSON 协议分布：BGP 19、CONNECTED 15、LOCAL 14，无 ISIS 候选。
Stage 1：4设备通过；Stage 2：10/10分支SAT。
严格完整模型基准：29故障场景、290分支适用性检查、116有效路由覆盖检查、116切片检查全部通过，行为反例0。
详情 results/bgp_only_0001/report.json。它证明本固定配置和故障范围内的结果，不扩展为任意配置或SR流量性质的证明。

复验新输入：

```sh
python3 slice_validation/validate_slices.py --work-dir slice_validation/generated/smt_output_0001 --output slice_validation/results/bgp_only_0001
```

## 双向观察层验收

后续实现以本仓库 `tools/netsubspec/slice_validation/` 为主，见
[BIDIRECTIONAL_VALIDATION.md](BIDIRECTIONAL_VALIDATION.md)。独立 JSON 观察适配不复用
RouteBinder，检查路由存在性与完整 CONTROL/DATA 出口集合，覆盖无路由与本地交付。
最新结果：29个场景，116组设备观察向量双向通过，其中2组无路由；290次分支
适用性检查未发现虚假可行分支。未绑定边界的局部切片有85组允许全网无法实现的
偏差，记录为 ABSTRACTION_ONLY，不能把局部裸切片单独视为全网等价模型。
新增5项观察层测试，加上原有32项相关测试均通过。
报告为 results/bgp_only_bidirectional/report.json。

## 以 seed 为目标的正向/反向检查

当前 seed 验收入口为 `check_seed_contracts.py`，见
[SEED_ASSUME_GUARANTEE.md](SEED_ASSUME_GUARANTEE.md)。按设备局部模型、共同域、邻居假设、本机保证
明确拆分查询。正向判定允许性，反向提供更强的边界条件保证，二者分开报告。
当前114组guard内场景均正向SAT/反向UNSAT，176组guard外不适用。
结果见 results/seed_contracts/report.json。先前完整网络观察基准保留为辅助审计，不替代该seed检查。


默认验收已调整为逐份完整seed：`check_seed_contracts.py` 不再默认按场景分类或跳过seed。
结果见 results/constructed_seeds/report.json：10份原始seed SAT、正向SAT、反向UNSAT、环境SAT。
逐场景统计仅在显式传入 `--per-scenario` 时启用。目标是验证构造的seed，而非单独验证guard。
