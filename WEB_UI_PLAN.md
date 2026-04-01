# Web UI Implementation Plan

本文档基于 [DESIGN.md](/Users/shanoriel/Projects/AutoReplication/DESIGN.md)、[ROADMAP.md](/Users/shanoriel/Projects/AutoReplication/ROADMAP.md)、[UX_Design.md](/Users/shanoriel/Projects/AutoReplication/UX_Design.md)，把下一阶段 Web UI 的实现工作拆成可执行计划。

目标不是继续扩展旧的“对象列表页”，而是重建一个以 `Task` 为主入口的控制台。

## 1. 产品目标

第一版 Web UI 需要支持四件事：

1. 用户一进来能判断 Gateway 和各 Runtime 是否健康。
2. 用户能创建一个新的 Task，并指定入口 Agent、参与 Agent、主要目标。
3. 用户能在 Task 视角下看到 roadmap、活跃 Agent、Dispatch 交互和近期活动。
4. 用户能 drill down 到具体 Agent / Dispatch / Session，并在 Session 层进行 steering。

明确不把下面这些作为首页主入口：

- 手工创建 Dispatch
- 手工创建 Session
- 全局 Agent 看板

## 2. 页面结构

### 2.1 顶部全局状态条

固定显示，不随 Task 切换消失。

显示内容：

- Gateway 健康状态
- 在线 Runtime 数量
- 工作中 Agent 数量
- 运行中 Task 数量
- 等待回复的 Dispatch 数量

### 2.2 Task 主入口条

显示内容：

- Task 下拉选择器
- `New Task` 按钮

这里不放全局 Agent 看板。

### 2.3 Task 详细工作台

三栏布局：

- 左 20%: stage timeline
- 中 50%: agent collaboration canvas
- 右 30%: task summary rail

## 3. Task 工作台分解

### 3.1 左栏: Stage Timeline

目的：

- 让用户第一眼知道 Task 现在推进到哪一步
- 让 roadmap 成为最高层执行视图

显示内容：

- 当前 Task 的 `stage_plan`
- 每个 stage 的标题、状态、更新时间
- lead/entry agent 最近一次对 roadmap 的修改摘要

交互：

- 点击 stage 可查看详情
- 后续支持“roadmap 修改历史”

### 3.2 中栏: Agent Collaboration Canvas

目的：

- 展示当前 Task 内活跃 Agent 的协作拓扑
- 展示哪些 Dispatch 正在等待、执行、阻塞

显示内容：

- 当前 Task 内有活动的 Agent 头像节点
- 节点状态灯：
  - 绿色呼吸: working
  - 蓝色常亮: idle but waiting
  - 红色常亮: fault
- 节点气泡：最近摘要或最近发言的截断文本
- Agent 之间的曲线连接
- 未完成 Dispatch 卡片，显示标题和已运行时长

只展示这些 Agent：

- 当前有 running session
- 当前有 pending / accepted / running dispatch
- 当前处于 fault

不展示完全空闲且与当前 Task 无活动关联的 Agent。

交互：

- 点击 Agent 头像，打开 Agent detail drawer
- 点击 Dispatch 卡片，打开 Dispatch detail drawer

### 3.3 右栏: Task Summary Rail

由两块组成。

第一块：Task Agent Strip

- 展示当前 Task 的所有参与 Agent
- 头像右下角状态点：
  - 绿色：online and active
  - 蓝色：online and idle
  - 红色：fault

第二块：Activity Feed

卡片化展示最近活动，不是纯文本日志。

卡片类型：

- Dispatch
  - `AAA -> BBB <Dispatch Title> Running/Failed/Replied`
- Planning
  - `AAA set <stage> as finished`
  - `AAA modified roadmap`
- Error
  - `BBB Error: <normalized error message>`

规则：

- 回复原 Dispatch 不单独开新卡片，而是更新原卡片状态到 `Replied`
- clarification-request 是新的 Dispatch，因此单独新增卡片

## 4. Drill-down 面板

### 4.1 Agent Detail

默认从当前 Task 视角打开。

显示内容：

- 当前 Task 下该 Agent 的 sessions
- 当前 Task 下相关 dispatches
- 当前状态、最近摘要、最近活动

提供一个范围切换：

- Current Task
- All Tasks

### 4.2 Dispatch Detail

显示内容：

- 基本信息：kind、from、to、status、created_at、resolved_at
- payload
- reply
- 关联 session
- parent / child clarification 关系

### 4.3 Session Detail

显示内容：

- 当前状态
- 最近消息
- 关键事件
- 当前工作目录 / preset / model

操作：

- 向该 session 注入 steering

## 5. 需要的后端数据投影

当前基础 CRUD 已经够支撑一部分 UI，但为了让页面不在前端堆太多拼装逻辑，建议新增几个 task-centric 投影接口。

### 5.1 `GET /api/overview`

返回顶部全局状态条需要的数据：

- gateway health
- runtime counts by status
- agent counts by status
- task counts by status
- dispatch counts by status

### 5.2 `GET /api/tasks/{task_id}/board`

返回 Task 工作台首屏需要的聚合数据：

- task base info
- task stage plan
- participant agents
- active agents
- task-scoped dispatches
- task-scoped sessions
- latest activity cards

这是 Task 工作台的主数据入口。

### 5.3 `GET /api/tasks/{task_id}/activity`

如果后续把活动流独立加载，可单独拆这个接口。

### 5.4 `POST /api/tasks`

现已支持以下建模：

- `title`
- `created_by`
- `entry_agent_id`
- `participant_agent_ids`
- `objective`
- `stage_plan`

第一版 UI 只需要把这个表单做出来。

### 5.5 `GET /api/sessions`

现已支持按这些字段过滤：

- `task_id`
- `agent_id`
- `dispatch_id`
- `status`

这能直接支撑 Agent detail 和 Session detail 的懒加载。

## 6. 前端实现顺序

### Phase A: 壳层与数据获取

1. 重写当前 `static/index.html` 的整体布局
2. 建立前端状态树：
   - overview
   - selectedTaskId
   - taskBoard
   - selectedAgentId
   - selectedDispatchId
   - selectedSessionId
3. 统一 fetch layer 和 polling 机制

### Phase B: 顶部与 Task 主入口

1. 全局状态条
2. Task selector
3. New Task modal

### Phase C: Task 工作台

1. Stage timeline
2. Collaboration canvas
3. Right-side summary rail

### Phase D: Detail Drawer

1. Agent detail
2. Dispatch detail
3. Session detail + steering input

### Phase E: 交互细化

1. 乐观刷新与高亮
2. 运行中 dispatch 时长计时
3. 错误态与空态
4. 小屏降级布局

## 7. 当前实现的明确偏差

下面这些在当前 UI 代码里是旧思路，重做时应删除：

- 用户手工创建 Dispatch 的表单
- 平铺式对象列表作为主视图
- 把 Session 当作首页主入口
- 用“所有 Agent 的总表”替代当前 Task 视角

## 8. 建议的下一步

按下面顺序推进：

1. 先补 `GET /api/overview`
2. 再补 `GET /api/tasks/{task_id}/board`
3. 然后重写 `static/index.html` 的结构和状态管理
4. 最后接入 Agent / Dispatch / Session detail drawer

这样可以保证 UI 第一版就是 task-centric，而不是在旧页面上修补。
