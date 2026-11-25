# Demo1 仅允许到 C

验证 X 发往 `5.5.5.5/32` 的流量。故障预算为至多两条物理链路，prepend 次数域为 `0–3`。X 必须到 C。I 仍发布同一个目的前缀，到 I 不满足本案例的性质。

- [设备配置](configs/)保存六台设备的配置快照。
- [性质定义](problem.json)记录允许的终点、故障预算及 Batfish 导出参数。
- [输入编码](input/)保留该性质对应的 SMT 和 Symbolic Route 导出。
- [全量字段级子规约](all_configs/4_final_subspecs/field_level_subspecs.txt)覆盖 42 个字段，[全量行级子规约](all_configs/4_final_subspecs/line_level_subspecs.txt)覆盖 16 条配置行。
- [全量求解报告](all_configs/report.json)记录验证状态、允许的取值和失败见证。
- [Prepend 专项输出](4_final_subspecs/)保留早期结果。

[打开两组案例的比较索引](../README.md)
