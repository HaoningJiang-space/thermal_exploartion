# Thermal-constrained Memory Service Organization

本轮采用 **Mode B — Architecture Exploration**。严格的 Stratum 复现仍未就绪，
但这不禁止明确标注、成本闭合、同等优化的条件性架构研究。Compute–Memory Fabric 分支保持关闭。

## 冻结的实验

主配置是 [Stratum-inspired contract](../configs/exploration/hb_npu_v1.json)：
121 mm² Logic、256 Banks、32 GiB、36 MiB SRAM、16 本地计算区域、固定内部 HB 连接预算。
32 MiB 权重驻留最快的 4 GiB timing tier；这里不代表全部 32 GiB 的持续访问能力。

每 Channel 的独立服务路径为 1/2/4/8，芯片共 K=16/32/64/128 单元，
每单元分别服务 16/8/4/2 Banks。ACT domain 和本地 Column data path 一起分区，
共同的 Column command bus 不增加。该假设表达已知的局部并行化思想，不能视为新机制。

两种面积对照：

* **Shared area（主实验）**：固定 noncompute、SRAM 与 HB 预留面积；Peripheral 增加后，
  剩余面积配置整数个 PE-equivalent Compute/RF blocks，16 Tile 数量不变。
  所有组织使用相同计算工艺、能效和面积密度。Peripheral 与 Compute 的静态、动态成本均收费。
* **Fixed compute（归因对照）**：固定 128 TFLOP/s，Peripheral 占用剩余面积，超出 121 mm² 的设计拒绝。

Compute/RF 面积从 Stratum 的分层、舍入面积比例推导；线性复制和 SRAM 端口充足是明确的放松假设。
这不是综合后的处理器。Compute block area 0.75–1.25 倍、Logic 其他动态能耗 0–0.08 pJ/FLOP
纳入预先规定的敏感性对照，不能把理想阵列利用率解释为已实现的硬件收益。

GEMV 和 GEMM 均为 4096×4096 FP16 权重，Batch 分别为 1 和 32。
Mixed 固定完成一次 Prefill 和 32 次 Decode，两个阶段共用一个权重布局，完成量不可删减。
所有 Local LP 重新优化静态布局与相同 DVFS 点；没有远端 Fabric 搜索。
T0 / T1_layer / T2 使用同一功率模型。Mixed 的每阶段稳态温度约束是明确的保守执行假设，
不是短阶段的瞬态温度预测。

## 命令与功率证据

复用固定 Ramulator snapshot 的状态机、FRFCFS 和 Refresh，专门生成一个**假设的内部宽端口模型**。
它既不是标准 HBM3 外部接口，也不是完整的 Stratum Mono3D 复现。
32 GiB 地址容量、Banks 与 Row 大小固定；快 Tier 时序向 0.5 ns CK 向上取整。
未公开的 ACT domain、tRRD/tFAW、Column bus、接口延迟明确采用工程假设。
必须重新生成完整 timing constraints，不能只改参数向量留下旧约束。

每个物理请求保留独立 ID：进入 Controller → Column command → DRAM 返回 → HB 交付 → 消费。
重复地址的两个 Read 分别追踪。Pin 住的 Controller 不合并 Read；未实现 Write 合并的验证。
所有命令在独立状态实例中重放；这验证同一定义的软件执行，而非器件真实性。

Long streaming 为 1 GiB；稳定窗口丢弃前两个 Refresh 周期和最后一个完整周期，
至少包含五个完整 Refresh 周期。短 GEMV 与低 HB trace 单独标注，不能称作跨 Refresh 稳态测量。
低 HB LP 使用 `min(long internal service, HB budget)`，预留 512 KiB/Tile 返回缓冲用于平滑 Burst；
这是一项解析假设，短 trace 保留作接口检查。

3.432 pJ/B 是来源清楚的**总能量量级假设**，不是独立校准。
默认 20% 为 full-row ACT/PRE，80% 为数据路径；后者的 60% 位于 Logic memory peripheral。
额外路径切换能量收费。Refresh 与最坏额外行重开按时间收费，避免温度降速后这些成本无故消失。
ACT/PRE 系数仍不可识别；没有从单点总功率拟合多个命令能量，也没有将 HBM 电流改名为 Stratum。

默认顶部等效热阻 0.3 K/W，有限对照为 0.1 / 0.5 K/W，全部设计共用冷却。
HiTS 检查线性方程残差并与 Direct 比较；4×4 空间节点是筛选模型，非已校准封装。

## 判别与停止

全部四个组织、拒绝点和预先规定的单项敏感性结果保存。
1% 内的最优点标为接近等效，不因微小调度差异宣称硬件最优性反转。
分别报告 T0→T1_layer 和 T1_layer→T2：总体热预算改变 K，并不自动说明空间热产生新架构。

仅一个 row-retention 约束进行理想放松，其他接口、时序、面积和全部能量保持。
理想收益不足 10%，或付费收益不足 5%，不推进对应 RTL。
FGDRAM/SALP-inspired partition 是已知机制代理，DreamRAM 是成本/组织 DSE 对照工作；
本轮尚未复现它们的完整电路，不能声称击败 best-known FGDRAM/DreamRAM。
只有对合理参数稳健、来自 HB 和空间热交互且不能由已有设计解释的剩余损失，才可能进入新架构设计。

## 运行

```bash
python -m thermal_exploration.run_organization \
  --ramulator-root external/ramulator2-g4 --thermal-backend scipy \
  --output outputs/organization-new
```

需先按 [G4 集成](grounded_validation.md) 构建固定的 Ramulator Python/native 工具。
HiTS 只改变求解后端，使用 `--thermal-backend hits` 并设置其独立 PYTHONPATH。
输出目录必须全新。

## 依据

[Stratum §6, Tables 1/3, Figure 15](https://arxiv.org/html/2510.05245v1)；
[FGDRAM，MICRO 2017](https://research.nvidia.com/publication/2017-10_fine-grained-dram-energy-efficient-dram-extreme-bandwidth-systems)；
[DreamRAM](https://arxiv.org/html/2512.12106v1)；
[固定 Ramulator HBM3 定义](https://github.com/CMU-SAFARI/ramulator2/blob/c6c7a5de0cef35935d6fad7369e6271406798865/python/ramulator/dram/HBM3.py)；
[HotSpot 官方冷却与 TIM 模板](https://github.com/uvahotspot/HotSpot/blob/master/template.config)。

尚未独立验证的能量、ACT domain 与几何属于假设，不因来源于同一论文的算术一致性而升级证据等级。
