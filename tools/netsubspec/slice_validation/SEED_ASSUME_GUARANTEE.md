# Symbolic seed 正向/反向检查

参考本地 auto-netsubspec checkout 的 `3_assume_guarantee_tester.py`：
`generate_forward_file` 固定邻居、本机路由和正常转发状态，预期 SAT；
`generate_reverse_file` 固定邻居而不固定本机路由，否定本机 combined constraint，预期 UNSAT。
仓库来源 https://github.com/yongzheng2024/auto-netsubspec，仅作结构参考。
未照搬其中修改邻居控制转发值等具体数据适配规则。

本实现直接读取原始设备切片，不采用 SeedBuilder 删除/释放约束后的 seed 基础部分。
Seed 只用于读取已有命名段落，将条件划分如下：

* D：选中分支 guard、故障预算、链路状态桥接、完整故障赋值。
* A：Selected peer predecessor route、Remaining peer candidate routes、Selected-peer link state。
* G：Current selected route、Selected import route、Device control-forwarding state。
* L：原始设备切片，包含固定配置和本机网络语义。

默认逐份完整seed检查，保留其符号化条件，不枚举故障场景，也不按guard内外跳过seed。
先直接求解实际构造的seed文件（constructed_seed），然后从未删改的设备切片重建正向和反向。
每份seed执行：

1. 环境非空：SAT(L ∧ D ∧ A)。防止反向空域假通过。
2. 正向：SAT(L ∧ D ∧ A ∧ G)。seed描述的整体约束允许成立（存在性，不单凭SAT声称每个场景均可实现）。
3. 反向：UNSAT(L ∧ D ∧ A ∧ ¬G)。没有预先固定任何G中的本机结果。

正向结果定义 seed admissibility；反向是更强的条件保证。
如果正向SAT、反向SAT，说明seed允许，但存在不满足G的其他行为，单独报告
ADMISSIBLE_WITH_ALTERNATIVE_BEHAVIOR，不能把它误报为seed不允许。
反向应否必须通过，取决于G是否定义该边界下完整的合法状态集合；未来ECMP需按集合建模。
未知/超时、缺失或未知段落、输入指纹不匹配不能假通过。
失败时保存正向和反向SMT文件供复现。缺失/不支持的协议不会通过删除冲突修复。

在 batfish 根目录运行：

```sh
python3 tools/netsubspec/slice_validation/check_seed_contracts.py \
  --work-dir tools/netsubspec/slice_validation/generated/smt_output_0001 \
  --output tools/netsubspec/slice_validation/results/constructed_seeds --k 2
python3 -m unittest discover -s tools/netsubspec/slice_validation/tests -p 'test_seed_contracts.py'
```

本次默认结果：10份实际seed均SAT；10份重建正向SAT；10份反向UNSAT；10份环境SAT。
报告为 results/constructed_seeds/report.json；每份seed保存 environment.smt2、forward.smt2、
reverse.smt2，报告记录seed原文件SHA256。不按guard分类计数，不跳过任何seed。

`--per-scenario` 是可选审计模式，另行枚举guard内场景；此前114组通过、176组不适用
的报告是辅助审计，不能代替逐seed验收。故障预算必须与构造seed的Stage 2一致。
本检查以设备边界契约为前提，不宣称任意边界状态可全网实现，不要求裸切片全网等价。
无路由观察检查由独立observable基准负责；本入口检查已有的完整路由seed。
