# AutoReplication UX Design

## 0. 文档目的

本文档用于沉淀 AutoReplication 当前阶段的产品交互设计思路。

它不讨论底层协议实现细节，而是回答下面这些问题：

- 用户在控制面里最关心什么
- 顶层对象应该如何呈现
- 用户如何创建任务、观察任务、介入任务
- `Task / Agent / Dispatch / Session` 分别在 UX 中扮演什么角色

本文档是当前阶段的初步 UX 设计草案，后续允许继续迭代，但实现前应尽量先以本设计为准。

---

## 1. 设计原则

### 1.1 以 Task 为最高层级

除了顶部的全局状态面板之外，主界面的大部分内容都应该围绕 `Task` 展开，而不是围绕单个 `Agent` 或单个 `Session` 展开。

原因很简单：

- 用户真正关心的是“这个研究任务进展到哪了”
- `Agent` 是任务中的执行参与者
- `Dispatch` 是 Agent 间正式协作的沟通对象
- `Session` 是更底层的执行与操作证据层

所以 UX 上的主层级应该是：

`Task -> Agent / Dispatch / Session`

而不是：

`Agent -> Session -> 其他东西`

### 1.2 用户不直接操作 Dispatch

`Dispatch` 在系统中的定位是 Agent 间正式沟通语言。

它更接近：

- 一封正式邮件
- 一次结构化工作请求
- 一次需要被回复的 agent-to-agent 协作对象

因此：

- 用户不应该直接创建 `Dispatch`
- 用户应该创建 `Task`
- 然后由系统中的主 Agent 或参与 Agent 在任务执行过程中产生 `Dispatch`

用户可以查看 `Dispatch`，追踪它，点击它看详情，但不应该把“手工创建 dispatch”当作主交互入口。

### 1.3 用户创建的是研究任务，不是单次执行

用户进入系统时，想做的事情不是“新建一个 Session”。

用户真正想做的是：

- 创建一个新的研究任务
- 指定这个任务先由哪个 Agent 接收用户输入
- 指定哪些 Agent 被纳入这个任务
- 指定任务总体目标

`Session` 只是这个任务在底层被某个 Agent 具体执行时产生的运行实例。

### 1.4 Session 是手术刀，不是驾驶舱

用户确实需要在执行过程中进行 steering。

但这个 steering 的定位应当是：

- 精细介入
- 面向某个具体 Agent 的某个具体 Session
- 让用户能够“在最底层动手术”

这意味着：

- `Session` 的入口应当存在
- 但不应成为主界面默认中心
- 主界面优先服务“看全局与看任务”
- Session 视图更多是 drill-down 之后的精细控制面

### 1.5 优先让用户“一眼看懂”

界面第一职责不是让用户点很多按钮，而是让用户快速理解：

- 系统活不活着
- 任务卡没卡住
- 哪个 Agent 在干活
- 哪个 Dispatch 在等待回复
- 当前任务推进到了哪个阶段

所以视觉和布局都应服务“全局理解”，而不是服务“多功能堆叠”。

---

## 2. 核心对象的 UX 定位

### 2.1 Gateway

`Gateway` 是全局控制面的健康与可信状态源。

用户对它的主要问题是：

- Gateway 是否健康
- 是否还在正常收集全局状态

因此 Gateway 在 UX 中主要表现为顶部全局状态中的一个核心健康指标。

### 2.2 Runtime

`Runtime` 代表每台机器上的本地执行控制器。

用户关心的是：

- 哪些机器在线
- 哪些 Runtime 正在工作
- 哪些 Runtime 有异常

因此 Runtime 在 UX 中属于基础设施可观测层，不是主要工作对象，但必须随时可见。

### 2.3 Agent

`Agent` 是任务参与者。

它具有以下属性：

- 唯一名字，不能重名
- 固定所属机器
- 固定 preset
- 固定 workspace / memory / soul agent / skills

用户关心的是：

- 这个任务里有哪些 Agent 在参与
- 每个 Agent 当前是 `Running / Idle / Fault`
- 这个 Agent 最近在做什么
- 这个 Agent 在当前 Task 下有哪些 Session 和 Dispatch

因此 Agent 在 UX 中既是：

- 任务中的角色节点
- 也是用户 drill-down 查看详情的重要入口

### 2.4 Task

`Task` 是 UX 里的第一层对象，也是主导航对象。

一个 Task 至少应包含：

- 任务标题
- 主要目标
- 第一个接收用户输入的 Agent
- 被纳入该任务的 Agent 列表
- 当前 roadmap / stage plan
- 当前进展总结

Task 是用户打开系统后最主要的观察与操作对象。

### 2.5 Dispatch

当前阶段将 Dispatch 收敛为两种：

- `work-order`
- `clarification-request`

并遵循一个原则：

- 每个 Dispatch 都有义务被回复

在 UX 上，Dispatch 是：

- Agent 间交互关系的显式证据
- 中间画布中的连线中心对象
- 右侧活动概要中的核心活动卡片

它不是用户主创建对象，但它是用户理解任务流转最重要的证据之一。

### 2.6 Session

Session 是 Agent 执行任务时的具体运行实例。

一个 Agent 可以有多个 Session。
每个 Session 一定隶属于某个 Task。

用户在 UX 上对 Session 的需求是：

- 当用户只想看任务整体时，不必先看到 Session
- 当用户需要精细介入时，必须能进入 Session 层
- 当用户从 Task 面板点击 Agent 进入详情时，默认只看当前 Task 下的 Session
- 用户可以切换到“所有任务视角”查看该 Agent 的所有 Session

---

## 3. 用户的核心需求

### 3.1 用户要创建一个新的研究任务

用户需要：

- 新建一个 `Task`
- 设置这个 Task 的目标
- 指定哪个 Agent 是第一接收用户输入的 Agent
- 指定哪些 Agent 参与该项目

这一步是控制面的主要创建入口。

### 3.2 用户要观察系统是否健康

用户需要一眼看到：

- Gateway 是否健康
- 各机器上的 Runtime 是否在线
- 当前总共有多少 Task 正在运行
- 当前总共有多少 Agent 正在工作
- 当前总共有多少 Dispatch 在等待回复

### 3.3 用户要观察某个 Task 的推进情况

用户需要一眼看到：

- 当前 Task 的 roadmap / stages
- 当前推进到了哪一步
- 哪些阶段已经完成
- 哪些阶段正在进行
- 当前 Task 内各个 Agent 的状态
- 当前 Task 内的最新进展总结

### 3.4 用户要理解 Agent 间的交互情况

用户需要在当前 Task 下看到：

- 哪些 Agent 目前正在工作
- 哪些 Agent 之间存在未完成的 Dispatch
- Dispatch 的方向、标题、持续时间、状态
- 最新发生的 clarification / work-order 关系

### 3.5 用户要在底层做手术刀式介入

用户需要能够：

- 点击某个 Agent
- 看到该 Agent 在当前 Task 下的 Session
- 进入某个 Session
- 查看该 Session 的消息、事件、运行细节
- 向该 Session 注入 steering

---

## 4. 顶层页面信息架构

## 4.1 页面总结构

建议页面总结构如下：

1. 顶部：全局状态面板
2. 下方主区域：以 `Task` 为最高层级的任务工作台

整体形式可以概括为：

`标题 | 全局状态面板`

`Task 下拉选框 | 新建 Task`

`<Task 详细面板>`

### 4.2 顶部全局状态面板

顶部全局状态面板需要回答：

- Gateway 是否健康
- 各 Runtime 是否在线
- 多少个 Task 正在运行
- 多少个 Agent 正在工作
- 多少个 Dispatch 正在等待回复

建议顶部是固定存在的 summary 区，不随 Task 切换消失。

### 4.3 Task 层主入口

顶部以下的主区域应有一个明确的 `Task` 主选择入口：

- 一个 Task 下拉选框，快速切换当前任务
- 一个“新建 Task”按钮(点击后产生弹窗让用户新建Task)

其中：

- 下拉选框用于切换任务上下文
- 新建 Task 用于创建新的研究项目

暂时不在 Task 主入口层单独放一个全局 Agent 看板（他未来是用于让用户管理增删Agent，短期先我们手动来）。

因此，当前 Task 下的 Agent 应统一在 Task 详细面板中呈现：

- 中间协作画布展示活跃 Agent
- 右栏 Agent 状态面板展示该 Task 的相关 Agent
- 以及最近活动栏目里面的Agent头像也可以点击进入响应的页面
- 用户从这些位置进入 Agent 详情（一个弹出的大窗口，覆盖在原始的网页上）

---

## 5. Task 详细面板设计

Task 详细面板是主界面的核心，应分为三栏：

- 左侧 20%
- 中间 50%
- 右侧 30%

## 5.1 左侧 20%: Task Stage Timeline

左侧应展示当前 Task 的 roadmap / plan / stages。

表现形式：

- 一个纵向时间线
- 每个 stage 纵向排列
- 用清晰的视觉状态表示：
  - 已完成
  - 进行中
  - 未开始
  - 阻塞 / 异常

这部分的设计目标是：

- 让用户一眼看到当前任务推进到了哪一步
- 让用户知道已经完成了什么、接下来是什么

这里的 stage plan 是 Task 的最高层 roadmap，由负责该 Task 的主 Agent 维护和更新。

因此在活动概要里也应该支持：

- `AAA modified Road Map`
- `AAA set <stage> as finished`

## 5.2 中间 50%: Agent Collaboration Canvas

中间区域应是一块任务协作画布。

画布元素：

- 每个 Agent 一个圆形头像
- 头像上方或旁边有一个小气泡
- 气泡内容显示该 Agent 最近在做什么
  - 可以直接截取其最新消息或总结的前若干字符

### Agent 状态光环

建议使用头像周围的光环表现状态：

- 绿色呼吸灯：正在工作
- 蓝色常亮：待机 / idle
- 红色常亮：故障

### Agent 之间的连接

Agent 之间使用平滑曲线连接。

如果存在尚未完成的 Dispatch，则在曲线中间展示一个 Dispatch 信息块，至少包含：

- Dispatch 标题
- 已执行时间

并且 Dispatch 卡片可点击查看详情。

### 画布展示范围限制

画布不应该展示所有 Agent。

只展示：

- 当前正在工作中的 Agent
- 当前存在等待中 Dispatch 的 Agent
注： 有故障的 Agent，如果他没有相关的Dispatch，也没有相关的任务进程，则也不展示。但是这个情况似乎不会发生？总之我们只使用上面两条过滤要不要展示Agent，只要他现在有活要干，或者再等待别人，那就展示。

完全空闲且与当前任务没有活动交互的 Agent 不应占据画布空间。

这能避免画布被静态节点淹没。

## 5.3 右侧 30%: 用户第一眼需要看到的信息

右栏不是“详细信息杂物箱”，而应是当前 Task 的高价值摘要区。

建议分成两块：

### 5.3.1 Agent 状态面板

这里以类似 Discord 成员条的方式，横向列出当前 Task 的所有 Agent，每个Agent一个头像。如果一行放不下自动换行

每个 Agent 展示：

- 头像
- 小状态角标

状态角标建议：

- 绿色小圆点：在线且 active
- 蓝色小圆点：idle
- 红色叉号或红点：故障

### 5.3.2 活动概要

活动概要展示最近发生了什么。

注意：

- 每一条活动都应是卡片
- 不是大段纯文本日志
- 新活动在更上面

活动分三类：

#### Dispatch 类

展示格式：

`AAA(头像) -> BBB(头像) <Dispatch_X 块（和画布那个一样可点击）> Running/Failed/Finished`

这里的箭头代表 Dispatch 的发送方向。

规则：

- 一个 work-order 从 A 发到 B，是一条活动
- 这条活动会持续显示其状态，直到收到回复后标记为 Finished
- 如果 B 中途向 A 发 clarification-request，由于这是新的 Dispatch，所以应新增一条新的活动卡片

#### Planning 类

展示格式例如：

- `AAA set <Road Map Item> as finished`
- `AAA modified Road Map`

这里不需要把 roadmap 的完整 diff 暴露在摘要区，用户想看细节再点进去。

#### Error 类

展示格式例如：

- `BBB Error: <规则化错误提示>`

错误内容当前阶段可以直接使用系统已有错误消息。

---

## 6. Agent 详细面板设计

用户可以从三类入口点击 Agent：

- Task 画布中的 Agent 头像
- 右栏 Agent 状态面板
- 活动概要中的 Agent 头像

进入 Agent 详细面板时，默认行为应当是：

- 只展示当前 Task 下的 Session 和 Dispatch 信息

原因：

- 用户此时通常是在任务上下文中点进 Agent 的
- 默认应保持上下文一致

同时应提供一个范围切换：

- 当前 Task 视角
- 所有 Task 视角

从而允许用户切换到更全局的 Agent 观测模式。

Agent 详细面板建议包括：

- 当前状态
- 当前 Task 下的 Session 列表
- 当前 Task 下相关 Dispatch 列表
- 最近消息 / 最近活动
- 进入具体 Session 详情的入口

---

## 7. 用户可执行操作

## 7.1 新建 Task

用户应能在主界面完成：

- 设置 Task 标题
- 设置任务目标
- 指定主 Agent
- 指定参与 Agent 列表

这是最主要的主动操作。

## 7.2 查看 Dispatch 详情

用户应能点击 Dispatch 卡片，查看：

- 类型
- 发送方 / 接收方
- 状态
- 标题
- 已耗时
- payload 详情
- 回复情况

但不应该以“手工新建 dispatch”作为主交互。

## 7.3 Session 层级 steering

用户应能进入某个 Session，并在 Session 层级进行 steering。

这部分能力定位为：

- 精细控制
- 低层干预
- 面向具体执行实例

因此应放在 drill-down 之后，而不是首页主视觉入口。

---

## 8. 当前阶段的产品范围收敛

为了避免第一版面板过度膨胀，建议当前阶段只优先实现以下范围：

1. 顶部全局状态面板
2. Task 主选择入口与新建 Task
3. Task 三栏详细面板
4. Agent 协作画布
5. Dispatch 活动概要
6. Agent 详情面板
7. Session 级 steering drill-down 入口

当前阶段不必优先追求：

- 复杂多标签导航
- 很深的多层弹窗系统
- 过度通用的对象管理台
- 高度复杂的可拖拽编排交互

---

## 9. 与当前实现的关系

当前代码库里已有一个较早版本的 Web 控制面，但其结构仍偏向：

- agent/session 列表
- 局部 steering
- 会话级明细

这与当前的产品模型已经不完全一致。

后续前端重构应遵循本设计的方向：

- 从“会话控制台”转向“任务控制台”
- 从“用户直接操纵 session / dispatch”转向“用户创建 task，系统内 Agent 产生 dispatch”
- 从“对象平铺”转向“Task 主导的可解释视图”

---

## 10. 下一步实现建议

前端实现顺序建议如下：

1. 先重构页面信息架构
- 顶部全局状态
- Task 主入口
- Task 三栏面板

2. 再实现 Task 详情中的三块核心区域
- stage timeline
- agent collaboration canvas
- right-side summary rail

3. 再补 Agent 详情 drill-down

4. 最后再把 Session steering 面板接进来

这样可以保证：

- 用户先能看懂系统
- 再能理解任务推进
- 最后才进入精细控制

这比一开始就把底层 Session 细节堆到首页上更符合当前产品目标。
