# Hybrid-Bonded 3D Accelerator Architecture Exploration

研究对象是HB改变Memory、Compute、Communication物理成本后，资源边界与执行组织是否合理。
模型和LLM是证据工具；所有计算位于Logic，DRAM在上方。无PIM、Power Delivery或多机扩展。

本合同的正式执行、失败修正、全模型容量、60个执行点、135个热评价点与Stage 3决策已归档于
[Stage 1–4结果](../results/stages-2026-10-10/findings.md)。
H4保持条件性：本轮没有证明需要新硬件，因此交付有依据的暂缓决策，不凭Oracle制造架构候选。

|Stage|冻结任务|完成证据|停止条件|
|---|---|---|---|
|1 Qualification|H2完整有限资源案例、H2–H3同合同交叉、ATLAS官方Artifact子案例|工作量/字节/容量/输出归属一致，误差与失真机制公开|资格不通过的模型只能报告条件性筛选|
|2 Characterization|Llama-3.1-8B与Qwen1.5-MoE-A2.7B，BF16，六场景128步|全模型容量、完整Layer依赖、强基线及单资源反事实|容量不满足保留不可行，不免费offload/量化|
|3 Discovery|定位最强既有方法之后的物理资源边界|最多一个候选或有依据的Hardware No-Go|Oracle不等于可实现新硬件，经典切分/融合不重命名|
|4 Evaluation|同121mm²/32GiB/36MiB/85°C及冷却的事件能量/空间周期热|持续全模型Token率、延迟、能耗、峰温与敏感性|未校准项明确；不以数值残差证明物理真实性|

六场景：Llama B1/C2048、B1/C32768、B4/C8192；Qwen B1/C2048、B2/C8192、B8/C2048。
容量按第128次Decode之后的KV增长检查。Qwen原始max_position_embeddings为8192；8192+128场景须标明超出发布配置边界，不能无声扩大。
Llama采用三投影SiLU-gated MLP；Qwen采用60 routed/top4及等价4个小专家宽度的shared MLP，不能继续使用80/top2代理。

B0局部cached Tiled；B1经典Tensor Parallelism/Megatron配对/头分组Split-KV；B2 kernel内请求预取、有限双缓冲/register fusion；B3静态3D-aware placement/TP–EP控制。
跨operator的全局SET/SoMa式prefetch和collective重叠尚未完整实现，保守barrier是公开模型边界，不可据此证明新硬件必需。
**机制代理不等于完整复现SET/SoMa/ATLAS/HDA-MoE**。必须列出已实现与未实现机制，不将Oracle当B3。
公开路由必须匹配模型/专家数/top-k；跨模型路由仅能作为有标签的迁移敏感性。

## 外部证据合同

- [ATLAS](https://github.com/pku-gsun/ATLAS-MICRO-2026)：固定b2787399408e32d327c820daee96d4e6610f551a；官方AE的DRAM interleave子案例，保留上游参数与输出，不混成Stratum。
- [DeepStack](https://github.com/tile-ai/DeepStack)：main固定17e21bf54115e11b9e7c6edc0b2d1723d25d022b；AE与main的来源分开，公开Qwen3/DeepSeek路由不能直接充当Qwen1.5。
- [Qwen模型配置](https://huggingface.co/Qwen/Qwen1.5-MoE-A2.7B/blob/main/config.json)：结构与shared expert统计口径以配置/实现为准。
- Llama配置取自DeepStack公开保存的Meta配置快照，记录文件digest，并与Meta公开模型卡核对。

旧H1/G1/G2/D1/D2归档保留，不改变历史门槛与数字。H2归档已经通过独立FIFO重放；合成H3/H5继续作为机制记录，不作为完整模型验证替代品。

## Qualification修正记录

旧4KiB网络模型把传播延迟串行收费；256B包与独立flight事件后，Row/Column/2D交叉误差分别约+7.72%/+1.97%/−1.41%，均进入10%目标。
旧32KiB整包返回引出的Buffer收益是事务抽象造成的；1024B独立返回和64KiB按字节credit后，该信号消失。
原结果不删除。完整层级模型仍是Mode B条件性预测，不能凭三例交叉声称芯片/完整LLM验证。

MoE旧代码的源结果生命期过长，并将已有源partial又作为新collective buffer收费；同一生产者多个buffer slice还需引用计数。
修正为per-token源slice在自身collective后释放、root持有至combine，别名不重复收费；失败轨迹保留，不将调度死锁当物理架构瓶颈。
完整模型的Attention采用head-grouped KV、真实(m,l,o)非线性状态合并；Qwen有router score归约和TP宽度相关的local partial weighting费用。
这些是执行语义与已知基线，不是新架构。
