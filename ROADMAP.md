# AutoReplication Roadmap

## 0. 目标

本 Roadmap 以最新的 [`DESIGN.md`](/Users/shanoriel/Projects/AutoReplication/DESIGN.md) 为准。

系统的总体架构不变：

- 一个 `Gateway` 作为全局控制面与统一状态源
- 多个 `Runtime` 作为各机器上的本地执行代理
- 每个 `Runtime` 管理本机一个或多个 `Agent`

但落地策略要收敛到一个更小的起点：

- 不先追求完整的多机自治研究系统
- 不先追求复杂的 DAG、自动规划、完整调度器
- 先跑通“少量 Agent + 简单工单协议 + 可恢复 loop”的 MVP

MVP 的判断标准不是功能看起来多，而是下面这个闭环是否稳定：

`创建工单 -> 派发给目标 Agent -> Runtime 拉取并执行 -> 回传结果 -> 上层继续下一步`

---

## 1. Roadmap 原则

### 1.1 先做最小闭环，不做大而全

第一目标不是“支持所有 Agent 类型”，而是只支持最少几个角色、最少几类跨 Agent 对象，把系统真正跑起来。

### 1.2 先保证状态机，再做智能调度

优先把以下对象做稳定：

- runtime 注册与 heartbeat
- agent 注册与归属
- task 生命周期
- dispatch 生命周期
- session 启动与结束
- 事件与消息审计

### 1.3 先 pull-based，再考虑 push-based

MVP 里 Runtime 通过轮询 Gateway 获取工作，不引入 websocket、消息队列或复杂推送基础设施。

### 1.4 先支持简单工单协议，不做过度抽象

MVP 只支持两类跨 Agent 协议对象：

- `work-order`
- `clarification-request`

并增加一个约束：

- 每个 dispatch 都必须有正式回复

### 1.5 先把恢复性做进系统

每个阶段都要求：

- 进程重启后状态可恢复
- Runtime 断连后可识别
- dispatch 不会静默丢失
- 长任务能被重新接管或重派发

---

## 2. MVP 北极星

MVP 只要求跑通一个非常小的双 Agent loop：

- `Research`
- `Experiment`

部署形态允许先从单机开始：

- `Gateway` 运行在本机
- 一个本地 `Runtime` 连接到 `Gateway`
- 该 `Runtime` 先只管理 2 个 Agent

然后再扩展到双机：

- Mac mini 上运行 `Gateway` + `Research Runtime`
- 实验机器上运行 `Experiment Runtime`

MVP 的用户故事：

1. 用户创建一个 task，例如“验证某个仓库能否在目标环境中跑通 smoke test”，并指定入口 agent 与参与 agents
2. `Research` 创建一个 `work-order` 发给 `Experiment`
3. `Experiment Runtime` 拉到该工单，启动一个 session 执行
4. 如果信息不足，返回 `clarification-request`
5. 如果完成，则对该 `work-order` 给出正式回复
6. `Research` 看到回复后决定结束或继续发下一个工单

这一步故意不要求完整论文复现。先用更小、更快的任务验证系统 loop。

---

## 3. Phase 1: Gateway 成为明确的控制面

### 3.1 目标

把当前内嵌式原型整理成“明确的 Gateway”，即使 Runtime 还暂时只跑在本机，也不再让架构语义混乱。

### 3.2 范围

- 明确 `Gateway` 只负责 API、DB、UI、状态机
- 从设计上移除“Gateway 自己就是执行器”的默认假设
- 保留现有本机会话能力，但把它放到 Runtime 抽象之下

### 3.3 必须完成

1. 明确核心对象与状态字段
- `runtimes`
- `agents`
- `tasks`
- `dispatches`
- `sessions`
- `messages`
- `events`

2. 补齐最小 API 边界
- Runtime 注册 / heartbeat
- Agent 注册 / 列表
- Task 创建 / 查看 / 更新
- Dispatch 查询 / 状态更新
- Session 创建 / 查看 / 消息注入 / 状态查询

3. 明确 Gateway 与 Runtime 的数据归属
- Gateway 持有注册表、dispatch 契约、session_inputs 暂存、状态摘要
- Runtime 持有 session 运行体、transcript、事件流
- UI 读 Gateway 薄层数据；Session Detail drill-down 时 Gateway 通过 heartbeat hook 从 Runtime 按需拉取 transcript
- 详见 DESIGN.md「设计决策：Gateway 与 Runtime 的数据归属与通信模型」

4. 明确 Web 面板的主视角
- 顶部展示全局状态
- 主区域以 `Task` 为最高层级
- `Agent / Dispatch / Session` 都作为 Task 的下层观察对象出现

### 3.4 验收标准

- 可以通过 Gateway API 创建 task，并让系统内 agent 协作产生 dispatch
- 可以在 Gateway 中看到 runtime、agent、session、dispatch 的结构化状态
- 重启 Gateway 后，已有状态仍可恢复

---

## 4. Phase 2: 单 Runtime 单机双 Agent MVP loop

### 4.1 目标

先在一台机器上跑通最小的跨 Agent 闭环，避免一上来被多机部署问题干扰。

### 4.2 部署形态

- 1 个 `Gateway`
- 1 个 `Runtime`
- 2 个 `Agent`: `Research`、`Experiment`

### 4.3 MVP 协议

这一阶段只实现：

- `work-order`
- `clarification-request`

并要求它们至少具备：

- `id`
- `task_id`
- `kind`
- `from_agent_id`
- `to_agent_id`
- `parent_dispatch_id`
- `payload_json`
- `status`
- `created_at`
- `updated_at`

### 4.4 Runtime loop

Runtime 每隔固定时间执行：

1. `heartbeat`
2. 拉取分配给本机 agent 的 pending dispatch
3. 对每个可执行 dispatch 创建 session
4. 监听 session 结束或中断
5. 将结果或 clarification 回写为 event、message、dispatch 回复与状态

### 4.5 这一阶段故意不做

- 多 Runtime 协同
- 自动重试策略
- Supervisor
- 除 task-centric 工作台以外的复杂 UI 编排
- 多工单并发调度

### 4.6 验收标准

- 一个 `Research` agent 能创建 `work-order`
- 一个 `Experiment` agent 能收到并执行该工单
- 能对该 `work-order` 形成正式回复
- Gateway UI / API 能完整看见整条链路
- Gateway UI 已经具备 task-centric 的基本工作台形态
- 失败时不会静默丢状态

---

## 5. Phase 3: Dispatch 恢复性与任务接管

### 5.1 目标

在 MVP loop 跑通后，优先补“系统可靠性”，而不是扩角色。

### 5.2 必须完成

1. dispatch 状态机收紧
- `pending`
- `accepted`
- `running`
- `blocked`
- `completed`
- `failed`
- `cancelled`

2. session 与 dispatch 建立明确关联
- 一个 session 由哪个 dispatch 触发
- 一个 dispatch 当前由哪个 session 处理

3. Runtime 失联检测
- heartbeat 超时后标记 runtime stale
- Gateway 能看见受影响的 dispatch / session

4. 工单接管策略
- session 异常退出后 dispatch 不丢失
- 可手动 requeue
- 可重新派发到同机或其他 runtime

### 5.3 验收标准

- Runtime 意外停止后，Gateway 能明确显示哪些工单处于不确定状态
- 手动恢复后可以继续推进，而不是从数据库里“猜”

---

## 6. Phase 4: 双机闭环

### 6.1 目标

把单机 MVP loop 扩展为真正的双机系统，但仍然只保留少量 Agent。

### 6.2 部署形态

- Mac mini: `Gateway` + `Research Runtime`
- 实验机器: `Experiment Runtime`

### 6.3 必须完成

- Runtime 独立进程化与独立启动
- 远程连接 Gateway
- 基于 machine / runtime / agent 的定向派发
- 基于同一 git 仓库的工作目录约束

### 6.4 验收标准

- `Research` 能把 `work-order` 派发到另一台机器上的 `Experiment`
- `Experiment` 完成后能对该 `work-order` 回写正式回复
- 用户可以从 Gateway 统一观察两个 Runtime 的状态

---

## 7. Phase 5: 面向真实复现任务的工单拆分

### 7.1 目标

把系统从“简单 smoke test 工单”推进到“可分阶段执行的真实实验任务”。

### 7.2 范围

围绕一个具体论文复现目标，把任务拆成多个可落地的 `work-order`，例如：

1. 环境与依赖验证
2. 数据获取与校验
3. 代码接入与最小运行
4. smoke test
5. 正式训练 / 评测
6. 结果整理与证据回传

### 7.3 验收标准

- 至少一个真实实验目标可以被拆成多个工单逐步执行
- 上层 Agent 可以根据下层回复决定下一步派发
- 失败与阻塞点能通过 `clarification-request` 回到上层

---

## 8. Phase 6: Supervisor 与人工介入

### 8.1 目标

在主 loop 稳定后，再增加“越界时唤醒更高层处理者”的能力。

### 8.2 范围

- 外部 watchdog 检测异常
- 通过 Gateway API 触发 Supervisor session
- 人工在 UI 中查看、暂停、继续、纠偏

### 8.3 验收标准

- 出现超时、卡死、异常失败时，系统能够触发可审计的人工或 Supervisor 介入流程

---

## 9. 当前最优先的实施顺序

下面是我建议立刻执行的顺序，严格围绕 MVP loop：

1. 重构数据模型
- 先把 `tasks`、`dispatches`、`runtimes`、`agents` 补齐
- 为 `sessions` 增加 `task_id`、`dispatch_id`、`runtime_id`、`agent_id`

2. 收口 Gateway API
- 先保证所有状态变更都通过 Gateway
- 不让 Runtime 直接改本地私有状态机

3. 做出独立的 Runtime poll loop
- 先不做多机
- 先在本机用 API 驱动起来

4. 跑通双 Agent 单机闭环
- `Research -> work-order -> Experiment -> reply`
- 暂时不强求 clarification 分支一开始就完美

5. 补 `clarification-request`
- 让“信息不足”成为系统内建分支，而不是自由文本失控

6. 做恢复能力
- heartbeat 超时
- dispatch requeue
- session 异常退出后的状态回收

7. 再推进双机
- 单机不稳定前，不要急着上双机

---

## 10. 明确不做的事

在 MVP 阶段，以下内容都不应抢优先级：

- 通用 DAG 调度器
- 任意数量 agent 的自动编排
- 复杂权限系统
- 过度美化 UI
- 高级报告自动生成
- websocket 推送体系
- 通用插件平台

这些能力未来可能需要，但现在都会干扰“少量 Agent、简单任务的闭环”。

---

## 11. MVP 完成定义

满足下面这些条件时，可以认为 MVP 完成：

1. Gateway 与 Runtime 角色边界清晰
2. 单机双 Agent loop 稳定跑通
3. dispatch 协议最少支持 `work-order`、`clarification-request`，并要求 dispatch 有正式回复
4. Runtime 能通过 heartbeat 和 poll loop 稳定执行工作
5. session、dispatch、event、message 都可审计
6. Runtime 或 session 失败后，系统可以恢复或人工接管
7. 在此基础上，再扩展到双机不会推翻现有模型

如果这 7 条还没满足，就不要进入更复杂的自动研究工作流。
