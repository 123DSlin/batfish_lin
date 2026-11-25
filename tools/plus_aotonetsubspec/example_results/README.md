# Demo1 的两组 Plus 结果

两组结果使用相同的设备配置、目的前缀 `5.5.5.5/32`、最多两条物理链路故障，以及 prepend 次数域 `0–3`。两组求解使用各自导出的可达性性质。

| 案例目录 | 通过条件 | 配置与性质 | 字段级子规约 | 行级子规约 |
|---|---|---|---|---|
| [demo1_q1](demo1_q1/README.md) | X 到 C 或 I 均通过 | [配置](demo1_q1/configs/) · [性质](demo1_q1/problem.json) | [42 个字段](demo1_q1/all_configs/4_final_subspecs/field_level_subspecs.txt) | [16 条配置行](demo1_q1/all_configs/4_final_subspecs/line_level_subspecs.txt) |
| [demo1_c_only](demo1_c_only/README.md) | X 必须到 C | [配置](demo1_c_only/configs/) · [性质](demo1_c_only/problem.json) | [42 个字段](demo1_c_only/all_configs/4_final_subspecs/field_level_subspecs.txt) | [16 条配置行](demo1_c_only/all_configs/4_final_subspecs/line_level_subspecs.txt) |

比较 T 的 `FROM_ISP` 策略第 20 条中的 prepend。

- **Q1** 的字段级开关输出为 `empty`，表示开或关均允许。行级结果为 `0 ≤ cost ≤ 3`，其中上下界来自本次求解域。
- **仅允许到 C** 的字段级开关要求 `enable=true`。行级结果为 `enable=true ∧ 1 ≤ cost ≤ 3`。失败见证可在报告中查看。

两个案例使用相同的目录结构。`configs/` 保存设备配置，`problem.json` 记录性质，`input/` 保留输入编码。`all_configs/4_final_subspecs/` 存放全量结果及按 C、I、T、X 划分的设备目录。`all_configs/report.json` 逐项记录取值域、允许的赋值及失败见证。案例根目录的 `4_final_subspecs/` 保存最早的 prepend 专项结果。

全量覆盖以 Minesweeper 导出的 `Config_*` 字段为准。字段级只改本字段，行级允许同一行的字段联合修改。IPv4 前缀和 MED 在报告列出的候选域内求解。`set metric` 的开关在原始编码中只有固定值，求解范围为原值 `true`。

[T3/T4 Community 回归结果](demo1_community_policy/README.md)使用 T 作为入口，分别验证策略拒绝和候选恢复，并保留各自生成的字段级和行级子规约。
