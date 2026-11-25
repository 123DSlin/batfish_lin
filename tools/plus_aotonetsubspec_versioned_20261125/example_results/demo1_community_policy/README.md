# Demo1 Community 策略回归

T 发往 `5.5.5.5/32` 的流量可经 C 或 I 交付。T3 和 T4 各检查零故障和所有单链路故障。导出索引把 `65050:10` 和 `65050:99` 分别编码为 `#x1` 和 `#x2`。

| 用例 | 子规约的结果 | Plus 输出 |
| --- | --- | --- |
| T3 修改 I 的通告标签 | I 的标签只能是 `65050:10`。改为 `65050:99` 后，I 仍通告前缀，T 在入站处拒绝它，T–C 断开时产生不可达反例。 | [字段级](t3_policy_change/4_final_subspecs/field_level_subspecs.txt) · [行级](t3_policy_change/4_final_subspecs/line_level_subspecs.txt) · [报告](t3_policy_change/report.json) |
| T4 修改 T 的 QUARANTINE 匹配值 | 匹配值必须改为 `65050:10`。I 继续发送 `65050:99`，T 改为接受该候选，T–C 断开时经 I 转发。 | [字段级](t4_candidate_recovery/4_final_subspecs/field_level_subspecs.txt) · [行级](t4_candidate_recovery/4_final_subspecs/line_level_subspecs.txt) · [报告](t4_candidate_recovery/report.json) |

T4 的输入是拒绝 I 的基线，T 的原始 Symbolic Route 在目标前缀的 MAIN RIB 中只列出 C。Plus 从这份编码释放 T 的匹配值，用原有的 BGP 通告、入站策略和选路方程重新求解。每个用例都验证 16 个配置与故障组合在原始 Minesweeper 和 Plus 中存在合法状态，并证明原始编码的合法状态都满足切片拼接方程。

从 Plus 目录运行以下命令可复跑 T4。

```bash
python3 -B tools/run.py example_results/demo1_community_policy/t4_candidate_recovery/input \
  --property-preserving --k 1 \
  --target Config_t_CommunityList_QUARANTINE__Line1__65050_99__community \
  --output /tmp/plus-community-t4
```

用同一输入把故障预算改为 `--k 2` 即可复跑 T6。T–C 和 T–I 同时断开时，状态公式为 SAT，T 的 RIB 没有到目标前缀的路由，`reachable_t=false`。这个状态是不可达反例，两个标签都被排除，字段级和行级结果均为 `false`。

T5 的 SMT 单元测试固定同一配置和同一故障，使性质为真和为假的两个状态分别可满足，再检查求解器排除该配置。真实 BGP 多稳态仍待验收。
