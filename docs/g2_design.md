# G2：Multi-Phase Shared-Placement Gate

问题：同一组权重用于 Prefill/Decode 时，一份静态数据布局是否仍能消除非局部连接优势？
保留第一轮负结果和模型，不开发 Fabric RTL，不扩大 Fabric 参数扫描。
只采用第一轮双方可用的 `chunk8k_tracker_bound`；它依然是理想 Row 协调上界。

## 固定工作与共同容量

两个阶段共用同一 4096×4096 FP16 权重矩阵（32 MiB），每个 Bank Group 给定相同的 4 MiB resident capacity。
Prefill 必须完成一个 Batch-32 GEMM；Decode 分别必须完成 1/32/128 个 Batch-1 GEMV。
每个混合均构成反复执行的完整周期，不允许丢弃 Decode、修改固定工作比例或只统计容易的阶段。

LP 变量是积分工作 `y[s,i,j,k]`（TFLOP）、阶段时间 `t[s]`（s）、Bank 常驻份额 `p[s,j]`。
阶段总工作 W[s] 已知，按 Bank 完成约束为 `sum_ik y[s,i,j,k] = W[s] p[s,j]`。
`sum_j p[s,j]=1`，`p[s,j] resident_weight_bytes <= bank_capacity_bytes`。
Shared 设置两个阶段的 p 完全相同；各方案分别重新优化 p、工作分配和 DVFS time shares。
一份权重只计一次容量，不允许各阶段预存不同副本。输入/输出广播和归约仍采用第一轮的理想化假设。

最小化 `sum_s t[s] + sum_transition d`，完成周期吞吐率为它的倒数。
用已知 W 而非可选的吞吐比例，使阶段工作与布局关系保持线性，避免 rate×layout 的双线性问题。
Compute、Bank、请求队列及链路限制由第一轮 rate 约束乘阶段时间转换为积分约束。
G2 service 系数与第一轮保持一致，Single Kernel Oracle 回归检查二者数值一致。

## 三种布局条件

1. Independent Oracle：每阶段免费独立选布局，保留理想性能上界。它不是可实现的共同常驻布局。
2. Shared：周期内和周期之间使用同一份静态布局，不搬迁。
3. Migration：可选择不同阶段布局；搬运使用所有架构都具备的同一普通 DMA mesh。

Migration 的 transport fraction `z[a,b]` 满足每个 Bank 的流出减流入等于旧 p 减新 p。
搬运字节为 `resident_weight_bytes sum_ab z[a,b]`，最小必需搬运量为权重大小乘 `L1(p_old-p_new)/2`。
Prefill→Decode 和 Decode→下一周期 Prefill 两个转换都计费。
传输按 XY 路由，计入 directed link 有限带宽、Bank 双端读写、请求队列占用及 Logic wire/DRAM energy。
迁移阶段不与计算免费重叠；读写流量和能量均按真实搬运字节计算，但系数未校准，不能称为实测迁移成本。
普通 DMA 支持属于各方案相同的基础预算；paid service Fabric 的新增面积和静态功率依旧单独收费。
不收固定启动/仲裁开销，是迁移的乐观下界；流式容量路径没有周期级队列和 scratch-buffer 调度证明。

Migration 在最优周期时间固定后，再最小化搬运时间与份额，避免退化 LP 把无需搬运的闲置时间放入 migration slots。
该第二个 LP 不改变最优周期时间。保留实际 LP solve 数量。

## 热条件与时间尺度

T0 无热限制，T1 单一全局 R，T2 全空间 H，各自重新优化全部方案。
Uniform/gradient cooling 沿用第一轮两个固定场景。没有新增硬件参数组合。

Phase steady：每阶段满足 `H E[s] <= (DeltaTmax-H P0) t[s]`，描述长阶段稳态筛选。
Cycle average：`H sum_s E[s] <= (DeltaTmax-H P0) sum_s t[s]`，描述整个周期的平均温度必要条件。
两者不可以在短阶段下直接当作实际峰值。阶段时间很短时，单阶段稳态可能过度限制；
平均温度约束也可能允许小幅周期超调。

使用明确列出的未校准体积热容，为原来的 48 节点 A 添加对角 M。
独立 modal propagation 计算 `M dtheta/dt + A theta = P` 的周期闭合温度。
对每阶段常功率轨迹，指数传播是精确的线性模型解；通过二阶导数插值误差界限制采样点之间的温度峰值，
并检查周期闭合与平均能量平衡。它是独立的 RC 检查，不是 HiTS native transient qualification。
HiTS 仍负责 H 的单位热源求解和原方程 acceptance，独立对照 SciPy direct。

若冻结调度的峰值超限，将全部阶段时间按 α 延长，动态功率除以 α，保留工作、字节及动态能量。
这在流式执行/阶段平均功率可实现性假设下构造一条温度合规调度；不声称已最优化瞬态 Mapping。

## 周期收益上界与停止条件

瞬态温度始终合规，则周期平均温度必合规，所以 Candidate cycle-average LP 时间是必要下界。
经峰值检查的 Local 调度提供最优 Local 周期时间的上界。

`possible_periodic_speedup <= Local_admissible_time / Candidate_average_LP_time`

取 Phase steady 与 Cycle average 各自重优化后可用的较快 Local 合规调度，提高负结果的约束力。
这只是当前 linear RC/fluid/constant phase power 模型内的条件上界；没有实际芯片参数的证明。
Independent Oracle 不用于声称可实现的 Local 周期上界，Shared 和 Migration 分别作公平对照。

继续门槛：共享容量/布局、真实字节计费、同等优化机会与 paid 连接成本之后，
净收益仍超过 5%，且 T2/T1 的相对增益超过 1%。
只通过乐观 LP 门槛仍不足以进入硬件；若周期收益上界都小于 5%，该配置可停止。
若所有理想候选在 Shared 条件下都未通过，停止当前 Fabric 分支，不追加重构机制。
HB 带宽与垂直耦合依赖性需要在出现有效收益后再检验，本轮不把一般多阶段问题宣称为 HB 特有。

## 运行

```bash
python -m unittest discover -s tests -v
python -m thermal_exploration.run_g2 --output outputs/g2-scipy
PYTHONPATH="$HITS_SRC${PYTHONPATH:+:$PYTHONPATH}" \
  python -m thermal_exploration.run_g2 --thermal-backend hits --output outputs/g2-hits
```

完整套件 648 个设计点，含 864 个 LP（Migration 增加一个定最优时间的 tie-break LP）。
输出目录必须不存在；保留全部阶段 work/layout、迁移双向字节、power 和周期温度界，不删除负结果。
