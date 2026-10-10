# P1 对照与分类审计修正

审计针对 9a5b379，并检查 G2 的 0eebee8。没有把对照缺陷描述为原 LP 数值计算错误。

1. 保留旧 T1_scalar，新增 T1_layer。两层模型用同一空间 H 的 block mean，保留 Logic/DRAM 来源与温度限制；无需增加 HiTS 方程求解。
2. 空间交互、Local spatial penalty 改用 T1_layer。旧标量交互单独保存，不再将其全部解释为水平空间热耦合。
3. 固定布局信号、理想连接上界和付费架构候选分开。Pilot 必须具有 fixed/free 全套控制；只在 free、付费、净收益及匹配收益 >5%、T0/T1_layer 净收益 <=1%、空间交互 >1% 时通过。G2 要有独立 oracle、shared、migration 控制，只允许 shared/migration 的付费候选通过同样门槛。
4. `architecture_candidate` 是模型筛选标签，仍要求执行与物理验证；不是硬件成果或新颖性判断。未付费 ideal 和 fixed 布局永远不能通过。
5. 原始 G1/G2 归档保留。重跑相同配置，新增热对照；不增加 Fabric 参数或挑选正结果。比较共同的 T0/T1_scalar/T2 吞吐、G2 周期上界，检查修正是否改变原停止结论。

Free Placement 是单 Kernel 可分流模型的放松上界。G2 加入同一权重常驻布局及双向迁移费用，仍不覆盖多权重生命周期、输入广播、partial-sum reduction、同步或实际 Controller 限制。
DRAM 近似缺少 tRRD/tFAW、周期级 ACT/PRE/Row conflict scheduler。Mesh 已对链路、请求占用、面积及功耗收费，但没有完整关键路径时序。
HiTS 原方程残差、互易性及 direct 一致性验证数值求解，不验证封装材料、功率或硬件成本。此次不修改 HiTS。

Compute–Memory Fabric 分支正式关闭。修正对照旨在明确既有证据边界，不能据此恢复该分支。
