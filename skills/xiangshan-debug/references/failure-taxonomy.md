# 错误签名与定位方向

本文件细化日志签名和候选模块，不定义分类流程或通过标准；二者以 [SKILL.md](../SKILL.md) 为准。

| 粗分类 | 常见子型或签名 | 应保留的首要证据 | 优先检查方向 |
| --- | --- | --- | --- |
| `stuck` | `No instruction of core <id> commits for <cycles> cycles, maybe get stuck` | core、无提交周期阈值、最后提交 PC/指令、commit trace、阻塞状态 | 提交链路、ROB 头部、redirect/flush、取指与执行推进、访存或一致性响应 |
| `mismatch` | GPR/CSR `different at pc` | PC、指令、寄存器/CSR 期望值与实际值、commit 序列 | producer、旁路、写回、rename/commit、异常提交 |
| `mismatch` | load/store 或内存值差异 | 地址、宽度、mask、数据、异常、请求 ID | LSQ、TLB、cache、写回合并、内存一致性 |
| `mismatch` | 控制流或提交顺序差异 | 预测/实际目标、history、redirect、flush | 分支预测、取指、恢复状态、异常返回 |
| `assertion` | `Assertion failed`、协议不变量；按 assert message 归一化模板进一步分组 | 原始断言文本、归一化模板、RTL 层级、cycle、相关状态 | `valid/ready/fire`、计数器、状态机、响应匹配 |
| `liveness` | watchdog、deadlock、livelock、资源泄漏 | 最后进展点、entry/request ID、timer、backpressure | 分配释放、仲裁、队列、状态推进、下游阻塞 |
| `bad_trap` | `HIT BAD TRAP`、`ABORT` | trap code、PC、退出路径、此前首错 | 负载主动退出、异常处理、Difftest、级联失败 |
| `fatal` | fatal error、segfault、core dumped | 宿主栈、signal、最后模拟器输出、退出码 | 模拟器/依赖崩溃、生成物不一致、设计触发路径 |

`stuck` 与宽泛的 `liveness` 分开：`stuck` 特指 DUT 在模拟器设定的连续周期阈值内没有提交新指令；`liveness` 用于明确的 watchdog、deadlock、livelock 或资源泄漏签名。命中 `stuck` 标准签名后，为辅助诊断而执行的 REF 单步可能继续触发 mismatch 和 `ABORT`，这些是伴随信号，不能覆盖 `stuck` 主类型。若标准签名之前已有独立功能错误，仍需按原始日志顺序人工核对首错。

## assertion message 分组

对每个 assertion 保存完整 message，并去掉日志前缀、换行差异和外层运行位置字段后进行比较。数字归一化只把十进制/十六进制数字、地址、ID、计数值和行号等实例字段替换为 `<NUM>`；模块名、条件、操作、状态和协议语义必须保留。

- 归一化后的非数字文本不同，或者数字 token 的位置/上下文改变导致语义不同：视为不同错误类型，分别建立类别目录，分别调试和回归。
- 归一化后文本相同，且只存在少量数字实例值差异：视为同一错误类型，合并 checkpoint，并在 `bug-analysis.md` 中列出所有原始 message 和归一化模板。
- 无法判断数字变化是否只是实例字段时，不合并；保守地拆分并在 `issues.md` 记录待确认依据。

以下现象先作为环境或证据问题处理，不直接并入六类功能错误：

| 现象 | 判别重点 |
| --- | --- |
| 构建或链接失败 | 生成、C++ 编译、链接中最早失败的阶段和命令 |
| 生成物不一致 | FIR/RTL、model、对象和 emu 的源码、配置与 mtime |
| instruction/cycle limit | 正常停止，而非此前功能错误的结果 |
| 外部 timeout | guest 是否仍推进，以及宿主是否只是仿真过慢 |
| 缺失或空目录 | CI 是否运行、上传是否成功、归档是否过期或无权限 |
| seed/后端差异 | 固定 seed 后能否复现，生成物是否真正等价 |

同一粗分类只有在首错签名、模块和触发路径接近时才合并；assertion 还必须满足上述 message 归一化规则。GPR 名称通常只是最终症状，应沿产生错误值的指令回溯；证据不足时把结论写成待验证假设。
