# 完整 MoE：先修因果合同，不以模拟器一致代替物理资格

**完整架构 G3/G4 未建立，Hardware No-Go 保持。** 本轮完成了完整 Expert、真实竞争和两个完整 MoE 样例的前端接入与代码审计；发现并修复普通 FIFO 合同下的队首绕过，另确认 MAC registered-reuse 抽象缺少有限 Matrix RF 证据。没有运行 TP/EP 排序资格矩阵或新 NoC/MAC、P4-C、Thermal/微流道 DSE。

修复执行源固定为 `0d5b89b95cdb28c7823514d38f20ea3168395512`，基础为 `09c99f2`。仅使用本仓库原始 Qwen1.5 捕获；解压 SHA256 为 `24aba0d1337106563e6b05f4f54ea6d5861838a930a376d99ae5feac9bcdb9e6`。真实 hidden2048、routed1408、shared5632、原始 Expert/Token IDs、概率以及全部 frozen resident layout 保留。小张量数值测试不作为性能实验。

## 1. 已证实的错误：slot 守恒不等于 FIFO 合法

早期完整前端只保存每个 input-port/VC 的占用计数，最多8 slots；未保存到达顺序。全局 node-ID 仲裁允许年轻 flit 在较老 multicast head 尚有 pending 分支时先启动自己的consumer。

在 `b241875` 的真实 Experts10/34 竞争 Native 记录中，独立历史检查发现 **24,314 次队首绕过**，另有15,626次同FIFO同tick服务多个head的事件。两类计数有重叠，不能相加。两专家各22 tokens，TP4共同占tiles8–11。

一个反例：tile0/input-port1/VC0，flit7953在tick9到达，本地SRAM接收consumer7954在tick9启动，下游link consumer7955到tick1025才启动；flit7984在tick13到达，却在tick13启动本地接收consumer7985。两个flit均依赖已到达的数据，credit始终不超过8，但年轻flit绕过了仍有pending分支的老flit。修复后consumer7985在tick1026启动；这也是配对记录的首次时间分歧。

这是针对**所选普通有序FIFO合同**的错误。若硬件有乱序选择、独立复制/分支存储，可以定义别的合同；当前实现没有为其结构和成本提供证据，不能默认免费获得该能力。H2参考采用真实FIFO，因而不能将该计数模型视为同合同接入。

修复后的Python和C++实现都在实际arrival时排队；consumer只能使用队首。multicast所有pending branches启动后才弹出head，每FIFO每tick最多服务一个head，in-flight reservation也计入8-slot容量。独立观察者从arrival与consumer历史重新检查队首和服务次数，不调用执行器的判断函数。加入了容量合法但绕过队首、以及同tick两个head的负向测试。

完整 **B32/TP4/Column** 的配对 Native 最终时间修复前后都是 **68.71525 μs**，但402,711个node的start/finish改变；解压program的SHA256完全相同，排除工作/DAG变化。因此，本轮没有证明该错误造成多大端到端性能夸大，也没有据此宣称原NoC Oracle被恢复。它证明的是：**最终延迟相同与完整前端一致仍可掩盖网络语义错误。** 该配对使用 `b241875` 与 `0d5b89b`，不混用更早Shared gate/零ops/尾包合同不同的prototype。完整独立历史核对见 [fifo-paired.json](fifo-paired.json)。

## 2. 尚未闭合的物理合同：32KiB byte block 不是 M/K microtile

现完整程序沿用 `expert_microtiles.py` 中的规律：每32KiB weight block读取 `min(weight_bytes,1024×token_count)` 个SRAM operand bytes，按峰值FLOPs、read和FIFO速率决定MAC周期。该ledger没有实际M/K坐标，没有Matrix RF容量/端口，也没有partial-sum寄存器分配或存活期。

已有组件参考则以实际M/K块执行，逐K块读取/写回FP32 partial sums。两种dataflow可有不同访问量；相同总FLOPs和SRAM端口宽度不能证明它们是同一物理机器的合法等价执行。

从第一性原理看，B32 Shared在一个tile具有352个Gate输出和352个Up输出，每个结果FP32。当前DAG直到整个局部kernel完成才进行结果SRAM写回，因此在此前必须保留：

\[
2\times352\times32\times4=90,112\ \mathrm{B/tile}.
\]

这仅是输出状态要求，不包含输入、权重和额外控制RF。仓库提供了Matrix RF面积比例，却没有可以检查该保留方式的容量/端口合同；row-swap RF是另一项资源，不能自动拿来免费存放这些状态。我们既未证明90,112B不可能实现，也未证明已付费硬件支持它。

以组件的32-row/128-K策略处理同一Shared tile，访问量为：

| 操作 | 完整byte-block抽象 | 组件M/K策略 |
|---|---:|---:|
| 输入operand读 | 2,883,584 B | 2,883,584 B |
| MAC中间partial读 | 未显式支付 | 1,351,680 B |
| MAC partial写，包括final | 仅末尾90,112 B写回 | 1,441,792 B |

**右列是指定组件dataflow的代价，不是所有dataflow的普适下界。** 足够容量、带宽和生命周期均明确的RF可能减少这些访问；目前缺的是其证据。Row-down和Column-down的K块数不同，这个缺口可能影响相对排序，不能由两个共享byte-block builder的执行器一致来排除。

`physical-contract-audit.json`逐真实矩阵导出坐标需求、组件策略访问量与保留字节。资格输出明确区分 `frontend_absolute_pass` 与 `architecture_g3_g4_qualified=false`。批量training/holdout架构资格启动器在此合同未闭合时拒绝运行，不用更多抽象点制造“通过”统计。

## 3. 实际完成的回归范围

三个完整Expert场景：s0/l0/B32/TP4/Column，Cold12（1 token）、Reused10（22 tokens）、Competition10/34（各22 tokens，共同tiles8–11）。竞争使用已有fine_prefetch；另两个保持fine_fixed，不混合归因。

两个完整条件MoE FFN：s0/l0/B32/TP4/Column及B8/TP16/Row，含真实Shared5632、Dispatch、Fused Combine、Row-ready128与Shared scalar gate。输入是已知当前Top-4/probabilities，不包含此前Routed Router/Top-k阶段。

Shared scalar gate的resident权重、实际token operand读、16-way score reduction、Sigmoid与scale broadcast均支付；Shared partial weighting必须等待scale。TP16的88元素hidden shard尾包按32B物理传输/存储付费，valid-byte mask阻止padding进入MAC。独立uint16 bit-pattern测试覆盖真实1408形状的odd-token尾包。

每场景执行C++ Native、C++ Fluid、Python Fluid、Python在线Native四路，后者向独立进程中的pinned Ramulator实时发请求并获得当前admission/return，不读取归档到达记录。六类node/request/port/lease/router/service trace逐行比较；另外核对每node实际服务、有限leases、FIFO、单Vector context、MAC占用以及Native command/state/tier-deadline。

**在线Native与C++ Native共享DRAM模型；全部执行共享抽象语义builder和未闭合的RF规律。** 其一致性只验证这些合同下的独立执行前端，不是完整硬件精度，更不是silicon验证。Fluid误差单独保留。逐点数据见 [execution-audit.json](execution-audit.json)，实际RD/MAC重叠见 [competition.json](competition.json)。

| 修复后的真实场景 | C++ Native（μs） | Python Fluid（μs） | Fluid误差 |
|---|---:|---:|---:|
| Cold12，B32/TP4/Column | 13.83025 | 13.51400 | −2.2867% |
| Reused10，同配置 | 23.25350 | 23.14125 | −0.4827% |
| Competition10/34，同配置 | 38.74500 | 38.74500 | 0% |
| 完整MoE，B32/TP4/Column | 68.71525 | 66.05425 | −3.8725% |
| 完整MoE，B8/TP16/Row | 17.56650 | 16.21275 | −7.7064% |

Python在线Native与各自C++ Native一致；两个backend各六类trace×五个case共60类逐行比较一致。这个零误差**不是独立物理精度**。不同case不作为一组TP/EP、Row/Column性能比较。
Competition中Expert34的16,896条RD命令有640条（3.7879%）发生于Expert10的MAC服务窗口，四个tile各160条；这是实际命令重叠，不是用accepted→returned区间近似DRAM忙碌。它也不证明当前MAC的RF留存假设正确。

完整数值验证使用原始routing/probabilities和缩小FP32/BF16矩阵；真实形状通过工作量、分片、routing slot、地址与transport masks检查。不是完整checkpoint BF16推理认证。固定FP32 K累加顺序以隔离BLAS GEMV/GEMM导致的BF16舍入边界，rtol2e-4/atol2e-6保持不变。

146项完整回归测试及1项新增原始证据打包测试通过。原P4-A宏执行B8/B32的精确回归保持72436/260146 ticks；新前端结果不静默替换原宏结果。组件报告M1408/K2048/B1比值已对齐为Native1.048972、Python1.041829，相对误差不变。

## 4. 保留失败，不继续用抽象排序推进硬件

`f0ee803` 首轮Reused/Competition在BF16数值检查失败；归因于未冻结FP32 contraction顺序，原始记录保留。`a3faa5d` 的数值修复后Expert记录仍缺FIFO队首合同，退役。

`158638b` 的8点完整MoE prototype有6点完成，B8/TP16/Column Fluid误差为−12.1911%，超过10%目标；两个TP16 Row样例在Native前因176B/odd-token尾包不对齐失败。它们与后续paid-tail/零ops/FIFO合同不同，全部单独保留，未混入修复后统计。`b241875`在线Native的前端完全一致也未排除FIFO错误；该版本和专门的完整MoE FIFO控制均标为退役。

下一项必要工作是把局部kernel映射到**实际M/K块、原生transaction byte范围、partial状态位置和有限RF/端口**；选择已付费的RF保留或SRAM materialization策略，再与独立详细参考采用同一物理合同。不得通过RF面积猜容量，不得通过更多contexts、免费端口或整体时延倍率补齐。

随后才恢复原冻结s0/l0的8点及s32/l7、s127/l23的16点G3/G4矩阵；这些仍不是新Prompt盲测。现在不运行link/flight Oracle，不进入P4-C或硬件设计。

全部修复和退役原始记录发布于 [本轮release](https://github.com/HaoningJiang-space/thermal_exploartion/releases/tag/p4-moe-causality-audit-2026-10-12)，资产与逐entry原始/打包SHA256见 [artifact-manifest.json](artifact-manifest.json)。复现方式见 [reproduce.md](reproduce.md)，合同见 [p4_complete_moe_contract.md](../../docs/p4_complete_moe_contract.md)。
