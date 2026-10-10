# Uncalibrated inputs — frozen G3/G4 record

用户确认目前没有额外作者参数或完整工作点数据。以下项保持 Unknown/null，不从 HBM3、SNAKE、Voxel 或旧 pilot 补值。
这是进入正式 Stratum 性能/热比较前的数据清单；不是为了拟合负结果而开放的新扫描维度。

| 未校准项 | 已知信息 /缺口 | 当前处理与受影响结果 |
|---|---|---|
| ACT current domain | 已知 16 channels ×16 banks；未知 tRRD/tFAW 作用范围、bank/subarray membership | 不计算可达 ACT aggregate rate；不把各 bank 并行能力免费相加 |
| Column/peripheral domain | 未公开完整 tCCD、共享 column bus、port mapping | bank-cycle 必要上界保留，实际 throughput 未识别 |
| 完整命令 timing | 分 tier tRCD、tRAS、tRP 已知；tCL、refresh 和其他状态转换未知 | 不实现伪 Mono3D command model；HBM3 独立使用上游时序 |
| 地址及 subarray 组织 | 容量/MAT/row 已知；bit-level bank/tier/subarray mapping 未验证 | equal-row tier 分割只标 Derived；不宣称真实布局 |
| DRAM 命令能量 | 0.429 pJ/bit aggregate；ACT/PRE/RD/WR/refresh/background 未拆分 | 只核查参考 anchor，禁止重复叠加或对访问轨迹当作动态系数 |
| Logic 功率组成 | MAC 0.604 pJ；总体 42.67 W；activity/scope 不完全一致 | 组成核查 +6.51%，5% Gate 未通过；SRAM/NoC/controller/PHY/leakage 不强行分配残差 |
| Logic 面积细分 | rounded hierarchy 可以闭合；部分 group 合并 | 独立 controller/NoC/vector 面积未知，不计免费新增硬件 |
| SRAM 执行 | 总容量已知；port、访问事件及每次访问能量未知 | 无法声称完整 MAC 利用率/数据消费模型已校准 |
| 内部 HB I/O | 数十 TB/s 内部 device bound；完整 pad count/rate/pitch/power/route 未识别 | HB equation 不输出 physical-pass；external 0.8192 TB/s 不代替内部链路 |
| 热源物理归属 | array、HV CUA decoder、LV bonded-Logic peripheral 位置定性已知；功率拆分未知 | 不将 aggregate DRAM power 全放 DRAM 节点 |
| Packaging /cooling | 没有对齐的完整层厚、材料、HB 界面热阻、热通路和冷却边界 | 不移植旧 cooling；T1_layer/T2 与 HiTS 闭环 deferred |
| 温度反馈 | refresh、leakage、DVFS 曲线未提供 | 不启用虚构反馈曲线 |
| 论文 reference 差异 | 30.34 vs 34.34 TB/s；131.072 vs128 TFLOP/s；104 vs101.86 W | 各出处单独保留，不能任意选一项来完成闭合 |

填补一项必须记录来源、统计范围、单位、活动条件、物理位置，以及匹配的完整工作点。
之后才能解除 [Hardware Contract](../configs/platforms/stratum_micro2025.json) 的 prediction guard。
标准 HBM3 的测试成功只支持集成接口，不会自动解除任何上述缺口。
