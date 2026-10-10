# Stage 1–4 — Hybrid-Bonded 3D Accelerator Architecture Exploration

本轮完成现有模型的资格核查、完整模型结构化Decode分析、条件性硬件决策和事件热评价。
**Research Go保留；当前没有足够证据批准一个新HB硬件候选，Stage 3不推进RTL。**
这里的“完成”指冻结实验与决策闭环，不代表器件校准完成、数值LLM推理正确或已获得新的论文架构。

## 1. Simulator Qualification

[H2归档](../h2-2026-10-10/findings.md)保留21个完成案例与1个在2,000,000tick内未完成的barrier负对照。
优化Column64为8.64325μs、124.23TFLOP/s；固定128TFLOP/s计算资源下剩余吞吐改善上界约3.04%。
独立逐flit FIFO顺序与queued/inflight credit重放通过；这不证明最终矩阵数值正确。

[同合同H2–H3交叉](../qualification-2026-10-10/findings.md)对Row/Column/2D分别得到+7.718%、+1.972%、−1.408%延迟误差，均满足冻结的10%目标。
三例工作量、DRAM字节、NoC byte-hops、最终输出归属和总私有容量一致。
原4KiB网络模型的+72.37%/+2.66%/+41.78%误差仍保留；256B包和独立传播事件修正了主要失真，未拟合硬件峰值或经验系数。
完整模型采用同预算的有限流式kernel，但不是逐命令/逐flit模拟；三例通过不提供完整Attention/MoE预测资格。

另实际运行了一个[ATLAS官方AE子案例](../qualification-2026-10-10/record.json)：同16channel/1024pin/500Mbps合同下，interleave bit0/7分别101.834/78.766μs。
bit0重复执行日志digest一致；bit7延迟减少22.65%。保留构建失败与成功记录，只有编译兼容修改。
这不是完整ATLAS AE、芯片测量或Stratum复现；公开子案例没有独立数值golden，不能虚构论文误差。
ATLAS与本机内部HB/DRAM合同不同，所以不比较绝对延迟。地址分布影响供数的趋势可作为外部参考，不能声称两个模拟器全硬件对齐。

详细执行器另运行Batch1、1024×16384：Row/Column有效权重带宽7.447/7.469TB/s。
独立FIFO重放均通过。它揭示cached路径的16×512GB/s SRAM写端口约8.192TB/s上限，不应将该结果误标为DRAM仅能提供7.47TB/s。
已知ingress FIFO的成本与独立供数路径是明确架构假设，未借此cached检查宣称经过芯片验证。

## 2. 完整模型与公平合同

源执行冻结在`dd9d434`；已有输入复用的构造式trace变换冻结在`ade8307`；最终热评价冻结在`2b83626`。
同121mm²、32GiB DRAM、36MiB SRAM、128TFLOP/s、32TB/s HB、4×4 Mesh/32GB/s每方向链路。
区域/Tier容量各256MiB，冻结所有常驻权重和全部层KV，不免费使用4GiB Fast Tier池或迁移权重。
B2/B3的已知FIFO/steering在同36MiB内重分配，另计0.8mm²、0.08W与0.1pJ/B成本；不增加MAC峰值。

Llama-3.1-8B采用32层、4096/14336、32Q/8KV heads和三投影SiLU-gated MLP。
Qwen1.5-MoE采用24层、2048、60 routed/top4、1408 expert width及5632 shared width；后者等价四个小共享专家宽度，不能误算成四个5632宽MLP。
全链包括RMS统计归约、QKV/RoPE、KV更新、在线softmax的(m,l,o)非线性合并、O投影、Residual、Gated FFN/路由和共享专家、LM head及下一步依赖。
模型权重和数值输出未实际执行：这是结构化完整层级执行，不是测量得到的Serving Token率或准确性验证。

|场景|Batch / 初始Context|含128步KV增长的总常驻GiB|最强已有T0模型tokens/s|该基线|
|---|---:|---:|---:|---|
|Llama基础|1 / 2048|15.2857|1544.09|B3|
|Llama长Context|1 / 32768|19.0357|1213.66|B3|
|Llama批量|4 / 8192|19.0826|4129.25|B3|
|Qwen小批量|1 / 2048|27.1264|4144.42|B3|
|Qwen长Context|2 / 8192|29.7749|4304.74|B2|
|Qwen批量|8 / 2048|29.9155|8551.96|B2|

全部六个场景容量满足32GiB。**Qwen B2/C8192再Decode128步超出发布的8192位置范围**：严格合同拒绝；本轮明确启用context-extension假设，不声称推理质量有效。
每个完成案例128步，共60个执行对照/7680个模型步；独立模型公式核对每步有用MAC FLOP，事件与容量账目闭合。
完整输入、原始结果、复用后的结果和全部反事实均保留，未只报告最佳点。

Qwen路由来自[HDA-MoE公开Qwen2数据](https://github.com/PKU-SEC-Lab/HDA-MoE-TCAD26/tree/56ea3725b2c621d4aea248f16345c34f5e06b8ed)：原64expert/top8/28层，投影到前24层，删除60–63号，再选前四个合法专家。
使用256记录训练前缀估计布局热度，随后1024条独立记录覆盖128×8 Token；不循环重复，不按测试集选择布局。
**这是跨模型投影控制，不是Qwen1.5实测Routing。** Uniform控制使用独立seed；其active expert复用量不同，不能把与公共路由的速度差当成同工作量架构speedup。

B0为cached local，B1为经典配对FFN/头分组KV，B2为已知有限FIFO/register fusion，B3为训练前缀驱动的静态3D placement与TP/EP控制。
这是列出具体机制的基线，**不等于完整复现SET/SoMa/ATLAS/DeepStack/HDA-MoE算法**。
保留operator/layer barriers及expert count-cohort串行化；未证明全局最优跨算子调度。该限制影响剩余Oracle空间的解释。
MoE已经广播的normalized输入在router后仍驻留，额外dispatch被构造式已有输入复用删除；所有DDR/MAC/路由和其他有限资源工作保留。
源partial生命期、引用计数、collective别名收费、32KiB整包返回引出的伪Buffer信号均有修正记录，旧失败不当成新硬件动机。

## 3. Architecture Characterization 与 Discovery

[Figure A](architecture_bottlenecks.png)展示全部B0–B3和最强已有方案的互斥macro关键阶段。
“memory/storage”同时包含DRAM、HB交付、SRAM拷贝/操作数和有限供数反压，**不能解释为纯DRAM stall百分比**。
kernel内存、算术、SRAM端口可以重叠，不将活动时间简单相加。该分解属于chosen DAG，不是全局最短调度的通信下界。
[Figure B](movement_and_map.png)展示六个场景的Batch/Context位置及DRAM/SRAM/NoC流量；未在未运行的区域插值。
[实际资源需求](physical_resource_demand.png)以whole-run work/peak capacity显示有用MAC、HB交付和SRAM端口需求；不能替代瞬时占用或Row-hit测量。完整模型没有逐命令ACT/PRE/Bank busy计数，此项不伪造。
[状态生命期](state_lifetimes.png)与[state-windows.csv](state-windows.csv)记录chosen DAG中保留至消费者的窗口，不声称是不可消除的最短生命期。

|B3单项反事实|六场景改善范围|解释|
|---|---:|---|
|Ideal Memory|15.99%–244.82%|同时移除DRAM与HB供数等待；保留有用字节/FLOP，不是实现成本已支付的DRAM改进|
|Infinite NoC|4.09%–13.16%|Llama Batch4最明显；链路/排队空间尚需区分已知collective重叠与硬件限制|
|Ideal Buffer|0%|修正独立1KiB返回后，无需新层次消除该供数粒度信号|
|Ideal Collective|2.46%–7.00%|chosen collective同步策略空间，未证明不能通过既有流水化消除|
|Direct producer streaming|0.325%–2.377%|新增中间结果直通硬件的当前动机弱|

这些是同B3的单项对照，不应相加，也不是相对六场景所有布局的精确性能上界。
Qwen B2/C8192和B8/C2048实际由B2胜过B3；不预设3D-aware标签总是更快。

**Stage 3决定：当前不提出新硬件候选。**
较强供数信号首先涉及已有cached输入边界及已知FIFO；大Memory Oracle还免费移除HB服务时间，不能直接据此批准新存储组织。
NoC/collective信号支持继续研究依赖与流水化，但当前模型保守barrier尚未被全局优化，没有证据证明传统执行结构无法消除。
DRAM Row packing、Tier功耗及精确命令域仍是假设；本轮不把经典Tensor Parallelism、FIFO、head grouping、输入复用包装成新的HB架构。
继续保留Fabric、Peripheral与Row-cycle三个历史Hardware No-Go；本结论只关闭/暂缓所检验的具体硬件，不否定整个HB方向。

## 4. Thermal & Physical Evaluation

最终数值与收敛结果见[thermal-all-points.csv](thermal-all-points.csv)、[convergence.json](convergence.json)，热合同见[thermal-contract.json](thermal-contract.json)。
[Figure C](isolation_and_thermal.png)分开T0、T1_layer steady、T2 spatial steady和T2 periodic；不把steady与transient差异全部归因为水平空间耦合。
[空间温度图](spatial_temperature.png)来自真实结构化事件的区域活动，不是短token阶段直接达到稳态温度。

采用0.302pJ/FLOP、3.432pJ/B aggregate memory、0.15pJ/B SRAM、0.5pJ/byte-hop NoC及显式background。
3.432pJ/B已含HB/peripheral，不能再完整加一次接口能量；它不是独立命令级ACT/PRE/RD/WR校准。
Memory heat默认48%位于Logic、52%位于等效DRAM，另做30%/70%分配控制；Tier深度与局部peripheral footprint未验证。
五个预冻结情景是energy scale0.8/1/1.2及package top resistance0.2/0.3/0.6K/W；135个点全部保留。
热反馈采用固定active执行速率，在可排空的bin checkpoint之后加入idle间隔以满足85°C。它是条件性duty-cycle构造，不是拟合DVFS曲线或最优热调度。
每bin动态能量闭合；所有报告的持续点通过周期温度上界检查，background能量随idle时间计入。
冷启动峰温字段对应整个128步burst，不能称为单个token瞬态。
未知温度相关refresh/leakage曲线关闭；4×4/8×8网格与128/256能量bin对照属于数值收敛，不验证真实封装或peripheral热点。

|默认最强已有基线|默认持续模型tokens/s|Energy/Token mJ|周期峰温°C|同基线弱冷却tokens/s|
|---|---:|---:|---:|---:|
|Llama B1/C2048 B3|1544.09|65.968|63.07|1311.00|
|Llama B1/C32768 B3|1213.66|87.049|64.51|985.96|
|Llama B4/C8192 B3|4129.25|25.660|64.70|3334.10|
|Qwen B1/C2048 B3|4144.42|22.485|59.84|3904.42|
|Qwen B2/C8192 B2|4304.74|20.993|58.79|4199.77|
|Qwen B8/C2048 B2|8551.96|9.454|55.29|8551.96|

表中弱冷却保持默认最强基线，非宣称其仍是该冷却条件下最优。全部基线分别评价：Llama B1/C2048弱冷却下B2达到1315.63，略高于B3。
135个点中9个需要idle pacing，其余126个无需人为降吞吐；默认六场景最强已有方案均有热余量。
本轮面积账目为84.95mm² cached、85.75mm²已知FIFO路径，均不超过121mm²；保留固定128TFLOP/s，不用空余面积免费扩MAC。
功率预算与冷却必要上界相容：0.3K/W顶部边界的60K温升必要散热上限200W，0.6K/W为100W；完整background与dynamic均计入。
T1_layer→T2 steady最大峰温差约1.89K；不能据此推出新的拓扑必须改变。
所有paced周期点Logic≤84.999951°C、DRAM≤84.450348°C，包含≤0.002K的峰值插值上界核查。

预冻结Qwen B8/C2048的TP16/TP4两种布局中，128→256 bins的峰温差分别0.0206/0.0513K；4×4→8×8网格差分别−0.1049/−0.0831K。均满足所检验场景的1K目标，吞吐排序不变。
Logic memory heat share从48%改为30%/70%时，该两点峰温移动不超过0.141K，均无需pacing。
这是两个预选默认冷却点的收敛/热源层归属控制，不能外推为所有85°C附近点或真实局部Peripheral footprint已验证。
HiTS原方程最大相对残差约4.74×10⁻¹²，独立模态残差≤1.75×10⁻¹⁵；135点平均能量平衡温差误差≤8.67×10⁻¹³K。
这些是数值证据，封装材料、等效DRAM层、未知温度反馈仍是明确假设。

## 5. 复现与证据边界

```bash
python -m unittest discover -s tests -v
python -m thermal_exploration.tensor_crossover --h2 results/h2-2026-10-10/all-points.json --output outputs/crossover
python -m thermal_exploration.run_layers --output outputs/layers --allow-context-extension
python scripts/derive_input_reuse.py --source outputs/layers --output outputs/layers-reuse
OPENBLAS_NUM_THREADS=1 python -m thermal_exploration.run_layers_h5 --layers outputs/layers-reuse --output outputs/layer-thermal --thermal-backend scipy
python scripts/export_stage_results.py --layers outputs/layers-reuse --original outputs/layers --thermal outputs/layer-thermal --output outputs/stages-archive
```

精确历史复现分别使用记录的执行/变换/热评价commit；当前main可复现同机制，不将最新HEAD冒充历史源版本。
默认SciPy路径可独立运行；原始正式热求解采用HiTS固定`c7f94d533cb663c2f098880e5ab333da9d83ff17`并检查原方程残差。
数值正确性、上游软件执行、有限案例交叉与器件/完整推理预测属于不同证据，不能用测试数量替代物理验证。
压缩原始事件、独立Decode检查及SHA-256逐文件清单已发布在[Stage 1–4 Release](https://github.com/HaoningJiang-space/thermal_exploartion/releases/tag/stages-execution-2026-10-10)。
公开模型参数来自[Meta模型卡](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct)、[Qwen官方说明](https://qwenlm.github.io/blog/qwen-moe/)及固定配置快照；未下载或发布权重。

下一项最有价值的证据是：对通信较明显的Llama Batch4，以及动态MoE的实际目标路由，加入强的跨operator collective重叠，再返回详细模型核查剩余损失。
本轮不提前指定新的Streaming NPU或NoC，不继续扩大外围电路DSE。
