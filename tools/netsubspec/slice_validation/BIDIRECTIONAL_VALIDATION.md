# BGP 双向行为验收

当前实现针对固定配置、单个目的地址、direct numbered eBGP，以及完整故障赋值比较行为。
观察量为本机 OVERALL_BEST.permitted、每个 CONTROL-FORWARDING 与 DATA-FORWARDING
接口布尔值。它不声称比较所有路由内部属性、协议实现或所有 ECMP 表示。

`observable.py` 直接读取原始 JSON 的 MAIN candidates 和 selectionGuard AST，不导入
RouteBinder，也不从 seed 的 Current selected route/Device control-forwarding 段提取答案。
先匹配目的前缀、求值 guard、按最长匹配保留活动候选，再从活动 contribution 的
previousRouter 和 eBGP 邻接表推导完整接口集合。未知 guard、缺失来源、平行会话、
无法映射的故障变量、非 BGP/CONNECTED/LOCAL 路由均报错，不能静默跳过。

对每个场景 f 与设备 r，生成完整观察向量 E(r,f)：

* 无路由：permitted=false，所有出口=false。
* 本地交付：permitted=true，不因本地接收而设置出口。
* BGP：permitted=true，准确设置全部选中接口，其余接口=false。

完整网络 M 保留配置、目的和故障约束，仅移出 reachable 性质机器。

1. 非空基准：SAT(M ∧ f)，防止空域使蕴含检查假通过。
2. 正向排除额外行为：UNSAT(M ∧ f ∧ ¬E)。背景中不能事先断言 E。
3. 反向可实现性：SAT(M ∧ f ∧ E)。在本范围中 JSON 给出一个完整接口集合向量，
   因而结合第2项可比较这一观察层上的行为。若未来模型允许多个非确定选择，必须
   显式枚举/投影行为集合，不能把其中一个分支强制当作唯一结果。
4. 分支可行域比较：分别求解 f∧bridge∧guard 与 M∧f∧bridge∧guard。
   前者SAT而后者UNSAT是虚假可行分支，不能跳过后记PASS。
5. 原有 seed 的属性相容性、否定预期行为检查、有效路由 guard 覆盖仍保留。
6. 局部抽象审计：若局部切片允许 ¬E，再查询完整 M 是否也允许 ¬E。
   全网不允许时标记 ABSTRACTION_ONLY；它说明边界自由度过大，不是两个工具真实冲突。
   该项没有为任意边界赋值提供全网扩展证明，也没有声称旧局部切片等价。

运行（在 batfish 仓库根目录）：

```sh
python3 tools/netsubspec/slice_validation/validate_slices.py \
  --work-dir tools/netsubspec/slice_validation/generated/smt_output_0001 \
  --output tools/netsubspec/slice_validation/results/bgp_only_bidirectional
python3 -m unittest discover -s tools/netsubspec/slice_validation/tests -p 'test_observable.py'
```

UNKNOWN/超时不能PASS。独立观察层出现真实差异时保存可运行的SMT2。
“独立”指适配与观察推导不复用binder，仍然共享两侧原始输出；不能排除源端共同错误。
IS-IS、SR Policy、递归下一跳及平行BGP会话需要扩展观察契约后才能进入此验收范围。
