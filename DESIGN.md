# AutoReplication Design

## 0. 文档定位

本文档描述 AutoReplication 的最高层愿景、系统边界和核心架构抽象。

文档分工如下：

- [`README.md`](/Users/shanoriel/Projects/AutoReplication/README.md)：说明当前仓库里已经实现了什么，以及如何运行
- [`DESIGN.md`](/Users/shanoriel/Projects/AutoReplication/DESIGN.md)：说明产品愿景、系统角色划分与顶层设计
- [`ROADMAP.md`](/Users/shanoriel/Projects/AutoReplication/ROADMAP.md)：说明分阶段落地路径与验收目标

## 1. 最高层愿景

AutoReplication 的目标是面向机器人领域的自动化研究工作，构建一个统一的多机、多 Agent 管理系统，用来执行需要多台机器协作的复杂任务。

这类任务可能包括：

- 一台机器负责论文搜索、阅读、规划与实验设计
- 一台机器负责写脚本、改代码、准备环境
- 一台机器负责启动训练、运行评测、收集结果
- 同一台机器内部也可能同时运行多个 Agent，分别承担不同职责

系统希望把这些分散在不同机器上的 Agent，统一纳入一个可观测、可调度、可人工介入的控制面。

## 2. 核心产品目标

系统要解决的不是“单个 Agent 能否完成一个任务”，而是下面这组更高层的问题：

- 如何让多个 Agent 在多台机器上长期稳定协作
- 如何让用户在一个统一界面里查看全局状态、发送指令、调整方向
- 如何让不同机器上的执行环境保持可复制、可恢复、可审计
- 如何让研究任务和实验任务自然地拆分到最适合的机器上执行

最终目标是把复杂的多机研究流程，从临时人工协调，演化为一个结构化、可管理的系统。

## 3. 代码与执行环境原则

系统默认采用一个重要约束：

- 每台机器上的工作代码库都来源于同一个 remote git 仓库

这样做的目的有几个：

- 每台机器都可以直接拉取同一份代码并运行
- 多机之间共享统一的代码基线，减少“这个结果是在哪个版本上跑出来的”这类歧义
- 用户和 Agent 的修改可以回到同一套版本控制流程里管理

在这个约束下，Runtime 更像是“在某台机器上管理同一类工作仓库及其会话”的本地执行代理，而不是一个完全脱离代码仓库上下文的黑盒 worker。

## 4. 顶层架构

系统分为两个层级：

- `Gateway`
- `Runtime`

### 4.1 Gateway

`Gateway` 是中枢管理系统，只会在一台电脑上运行。

它负责：

- 统一维护全局状态
- 管理机器、Agent、Session、消息、事件等核心对象
- 承担通讯与调度中枢的角色
- 提供 Web UI
- 处理用户交互
- 作为 Runtime 与 Runtime、Runtime 与用户之间的桥梁

`Gateway` 不直接代表某一台执行机器本身，而是全系统的控制平面。

### 4.2 Runtime

`Runtime` 是每台机器自己运行的 Client 系统。

它负责：

- 与 `Gateway` 建立通信
- 向 `Gateway` 汇报本机状态
- 接收来自 `Gateway` 的任务或控制指令
- 在本机上管理一个或多个 Agent
- 为本机 Agent 准备工作目录、环境、配置与运行上下文
- 把本机执行产生的事件、消息和结果回传给 `Gateway`

`Runtime` 是“每台机器的本地执行控制器”，而不是 UI 或全局调度中心。

## 5. 多机多 Agent 模型

系统允许：

- 多台机器同时接入同一个 `Gateway`
- 每台机器运行多个 Agent
- 不同 Agent 拥有不同角色，如 research、planning、implementation、experiment、review
- 用户从统一界面观察这些 Agent 的状态与协作过程

这意味着系统的基本抽象不应该是“只有一个 agent 在跑”，而应该是：

- 一个 `Gateway`
- 多个 `Runtime`
- 每个 `Runtime` 下有多个 `Agent`
- `Agent` 通过 `Session` 执行具体任务

## 6. 设计重点

为了支持长期演进，这个系统在顶层设计上应优先保证以下几点：

- **统一状态源**：全局状态以 `Gateway` 维护的结构化数据为准
- **Runtime 本地自治**：每台机器独立管理本地执行细节，但服从统一协议
- **可观测性**：用户可以看到机器状态、Agent 状态、Session 状态、事件流和消息流
- **可调度性**：任务可以被显式分配到某台机器、某类 Agent 或某个 Runtime
- **可恢复性**：进程重启、机器断连或任务中断后，系统状态应可恢复
- **可人工介入**：用户可以在全局层面随时查看、暂停、引导、纠偏

## 7. 当前实现与目标架构的关系

当前仓库已经实现了一个早期版本的 `Gateway`，并内嵌了一个本地 `Runtime` 原型。

这意味着当前代码已经覆盖了下面这些能力：

- 用 Web UI 创建和查看 session
- 用 SQLite 维护核心状态
- 启动本机 Codex 会话
- 向已有会话发送 steer message
- 记录消息与事件

但离目标中的完整架构还有明显差距：

- `Gateway` 与 `Runtime` 还没有彻底分离成独立部署单元
- 多 Runtime 协作还没有真正打通
- 每机多 Agent 的统一调度还没有完整建模
- 基于同一 remote git 的多机工作流还没有被正式协议化

## 8. 目标工作流：三 Agent 双机模型

系统的第一个目标工作流是"自动复现机器人论文实验"。经过分析，这个工作流只需要三个 Agent 分布在两台机器上。

### 8.1 Agent 定义

| Agent | 机器 | 职责 | 触发方式 |
|-------|------|------|----------|
| **Supervisor** | Mac mini | 监控系统运行状态，处理监控脚本无法 handle 的异常 | 被动触发（脚本兜底，越界时唤醒） |
| **Research** | Mac mini | 读论文、理解方法、产出实验规格、评审实验结果 | 主动运行 |
| **Experiment** | hjs-alienware | 审查规格完整性、请求补充信息、执行实验、回传结果 | 收到实验请求时触发 |

### 8.2 核心交互流

```
人 → Research: "复现 Diffusion Policy / Push-T"
     Research: 读论文，产出 ExperimentSpec
     Research → Experiment: 提交 ExperimentSpec
     Experiment: 审查规格 → 信息不足？
         ├─ 是 → Experiment → Research: 补充信息请求 (ClarificationRequest)
         │       Research → Experiment: 补充后重新提交
         └─ 否 → Experiment: 执行实验
     Experiment → Research: 返回 ExperimentResult
     Research: 评审结果，决定下一步（继续迭代 / 完成 / 换方向）

脚本持续监控 ──→ 超出边界 ──→ 唤醒 Supervisor 介入修正
```

### 8.3 交互模式特征

Research 与 Experiment 之间的交互不是自由聊天，而是 **结构化的工单协议**。

这里刻意保持最小设计，只保留两类跨 Agent 交互：

- `work-order`
- `clarification-request`

同时增加一个重要语义约束：

- 每个 dispatch 都有义务被回复

也就是说，下层执行结果不再单独建模为第三类 dispatch，而是作为对已有 dispatch 的正式回复语义存在。

这两类对象已经足够覆盖当前目标工作流，不在这一阶段继续引入更多协议层级。

#### 8.3.1 Work Order

`work-order` 是上层 Agent 分配给下层 Experiment Agent 的 **最小可执行工单**。

核心原则：

- 一个 `work-order` 必须尽量限制在 **单个 session 可以完成** 的范围内
- `work-order` 应该描述一个明确、可验证、可交付的执行目标
- 下层 Agent 不负责接收一个过于宏大的“完整实验愿景”，而是负责完成一个具体工单

对于机器人实验，这一点尤其重要。因为底层执行通常会涉及：

- 模拟器安装与环境准备
- 数据下载与校验
- 代码接入、修改与调试
- smoke test
- 正式训练或评测
- 结果导出、视频录制与产物整理

这些步骤往往不能在一个 session 里全部完成，因此应由上层 Agent 先完成高层理解与拆分，再将任务切成多个 `work-order` 逐步下发。

例如，一个完整的复现任务不应该直接作为一个工单交给底层，而应该先拆成：

1. 安装并跑通某个 Push-T 模拟器或图形库
2. 下载并校验指定数据集
3. 参考论文与开源仓库实现模型并做 sanity check
4. 启动正式训练并完成模拟器中的测试
5. 导出日志、结果与执行视频

在这一模式下：

- 上层 `Research` 负责理解论文、决定整体路线、控制高层实验逻辑
- 下层 `Experiment` 负责把单个工单执行到底

#### 8.3.2 Clarification Request

当某个 `work-order` 信息不足，导致 Experiment Agent 无法继续执行时，下层发出 `clarification-request`。

它的作用是：

- 明确指出当前阻塞点
- 请求上层补充缺失信息
- 尽量把问题限定在当前工单上下文内

`clarification-request` 不承担重新规划整个实验的职责。高层路线调整仍然属于上层 Agent。

#### 8.3.3 Dispatch Reply

虽然当前只保留两类 dispatch，但每个 dispatch 都应当有正式回复。

对于 `work-order`，回复应回答三个问题：

- 这个工单是否完成
- 实际执行了什么
- 产生了哪些结果与产物

回复可以表示：

- 成功完成
- 部分完成
- 执行失败
- 因外部阻塞而未完成

无论成功还是失败，回复都应尽量带回可审计的证据，例如：

- 命令与日志
- 产物路径
- 截图或视频
- 关键指标
- 失败原因与建议下一步

#### 8.3.4 当前设计选择

在现阶段，系统不试图把完整实验规划、多阶段编排、全局 DAG 调度都协议化。

当前采取的简化原则是：

- 高层复杂度先留在上层 Agent 自己的 session 内解决
- 跨 Agent 协作时只传递最小必要对象
- 优先保证底层工单真的能执行出来

这意味着 Agent 间消息需要有明确类型和关联关系，但协议本身保持极简，不做过度设计。

### 8.4 Supervisor 的触发机制

Supervisor 不常驻运行。大部分时间由外部监控脚本（cron job 或 watchdog）负责检查系统健康。只有当状况超出脚本预设的处理边界时，脚本才通过 Gateway API 创建 Supervisor session 并注入异常上下文，唤醒 Supervisor Agent 进行更智能的修正。

这意味着 Supervisor 的触发不需要内建到 Gateway 中，它是 Gateway 外部的一个独立脚本。

## 9. 设计结论

AutoReplication 的本质，不是一个单机 Agent UI，也不是一个简单的 Codex launcher。

它应当被设计为一个：

- 面向机器人研究任务
- 支持多机协作
- 支持每机多 Agent
- 由单点 `Gateway` 统一管理
- 由各机 `Runtime` 负责本地执行
- 基于共享 git 工作流组织代码与实验

的研究执行系统。

---

## Proposal: 数据模型与 Gateway/Runtime 拆分设计（待评审）

> 以下内容为 Claude 基于第 8 节工作流分析提出的设计提案，尚未实施，供评审讨论。

### P1. 问题陈述

当前实现存在两个结构性缺陷：

1. **Agent 间无法通信**：messages 表绑定在 session 内部（session_id 为外键），无法表达"Research session A 给 Experiment session B 发了一个请求"。
2. **Gateway 与 Runtime 耦合**：LocalRuntimeManager 作为 daemon thread 绑定在 FastAPI 进程内，无法独立部署到其他机器。

### P2. 数据模型变更

#### P2.1 新增 `tasks` 表

Task 代表一个完整的研究目标（如"复现 Diffusion Policy / Push-T"），多个 session 隶属于同一个 task。

```
tasks
├── id                  TEXT PRIMARY KEY
├── title               TEXT           -- "Replicate Diffusion Policy Push-T"
├── status              TEXT           -- created / active / completed / failed
├── created_by          TEXT           -- 发起者（human / agent_id）
├── entry_agent_id      TEXT           -- 第一个接收用户输入并负责高层推进的 agent
├── participant_agents_json TEXT       -- 被纳入该 task 的 agent 列表
├── objective           TEXT           -- 本任务的主要目标说明
├── created_at          TEXT
└── updated_at          TEXT
```

#### P2.2 新增 `dispatches` 表

Dispatch 代表一次跨 Agent 的结构化工单交互。这是 Agent 间协作的核心数据结构。

```
dispatches
├── id                  TEXT PRIMARY KEY
├── task_id             TEXT           -- 属于哪个 task
├── kind                TEXT           -- work_order / clarification_request
├── from_agent_id       TEXT           -- 发起方 agent
├── to_agent_id         TEXT           -- 接收方 agent
├── parent_dispatch_id  TEXT NULL      -- 关联的上游 dispatch（clarification 指向原 request）
├── payload_json        TEXT           -- 结构化内容（Work Order / Clarification Request）
├── status              TEXT           -- pending / accepted / running / replied / failed
├── reply_json          TEXT NULL      -- 对该 dispatch 的正式回复
├── created_at          TEXT
└── resolved_at         TEXT NULL
```

**为什么不复用 messages 表？** messages 是 session 内操作员↔Agent 的通信（人给 Agent 发指令、Agent 回复），dispatches 是 Agent 间的结构化契约传递，语义不同，混用会让查询和状态管理混乱。

#### P2.3 现有 `sessions` 表的小改动

```
sessions 新增字段:
├── task_id             TEXT NULL      -- 隶属于哪个 task
└── dispatch_id         TEXT NULL      -- 由哪个 dispatch 触发创建的
```

agents、events、messages 表不变。

#### P2.4 交互流程映射

以 Research → Experiment 下发工单为例：

1. Research 在自己的 session 中完成高层分析与任务拆分
2. Research 创建 dispatch（kind=`work_order`，to=Experiment agent）
3. Gateway 记录 dispatch，状态为 `pending`
4. hjs-alienware 的 Runtime 轮询发现新 dispatch → 自动创建 session 来处理
5. 如果信息不足 → Experiment 创建 dispatch（kind=`clarification_request`，parent=原 work-order）
6. Mac mini 的 Runtime 轮询发现 clarification → Research 补充信息后继续下发新工单或更新方案
7. 工单执行完成 → Experiment 对原 `work-order` 写入正式回复并结束该 dispatch

### P3. Gateway / Runtime 拆分

#### P3.1 原则

- Gateway 是纯控制面：API + DB + UI，不运行任何 Codex 进程
- Runtime 是纯执行面：连接 Gateway、拉取工作、运行 Codex、回报结果
- 两者通过 HTTP API 通信（现有代码已经在走这条路）
- 即使在同一台机器上，也是两个独立进程，先启动 Gateway 再启动 Runtime

#### P3.2 Gateway 侧改动

从 `main.py` 启动流程中移除 LocalRuntimeManager，新增 dispatch 相关 API：

```
POST   /api/dispatches                                  # 创建 dispatch
GET    /api/dispatches?to_agent_id=X&status=pending     # 拉取待处理 dispatch
PATCH  /api/dispatches/{id}                             # 更新 dispatch 状态
```

Gateway 变成纯粹的 API server + 静态文件服务。

#### P3.3 Runtime 侧改动

将 `local_runtime.py` 改造为独立可启动的包：

```bash
python -m autorep_runtime \
  --gateway-url http://192.168.1.100:11451 \
  --machine-id mac-mini
```

Runtime 启动后的 poll loop：

```
每 2 秒：
  1. POST /api/agents/{id}/heartbeat
  2. GET  /api/runtime/launch-queue?machine_id=X         → 拿待启动 session
  3. GET  /api/dispatches?to_agent_id=X&status=pending   → 拿待处理 dispatch
     → 对每个 pending dispatch：创建 session → 执行 → 完成后更新 dispatch 状态
```

#### P3.4 包结构

```
src/
├── autorep_gateway/        # Gateway 包
│   ├── main.py             # FastAPI app（移除 runtime 启动逻辑）
│   ├── db.py               # 数据库层（新增 tasks / dispatches 表）
│   ├── catalog.py
│   ├── config.py
│   ├── schemas.py          # 新增 dispatch 相关 Pydantic 模型
│   ├── service.py          # 移除 runtime 单例
│   └── __init__.py
└── autorep_runtime/        # Runtime 包（从 local_runtime.py 演化）
    ├── __main__.py         # 入口：python -m autorep_runtime --gateway-url ... --machine-id ...
    ├── manager.py          # RuntimeManager（轮询 + 调度逻辑）
    ├── executor.py         # Codex 进程管理（启动 / resume / 事件捕获）
    └── __init__.py
```

---

## 设计决策：Gateway 与 Runtime 的数据归属与通信模型

> 本节基于对 OpenClaw session 机制的分析以及 AutoReplication 自身需求的讨论，确定 Gateway 与 Runtime 之间的职责边界、数据归属和通信协议。

### D1. 核心原则

**Gateway 是邮局 + 注册处，不是档案馆。**

Gateway 需要知道"信该往哪送"和"dispatch 契约的状态"，但不需要存每个 session 的完整对话记录。Session 的运行体和详情留在 Runtime，Gateway 按需拉取或只看摘要。

### D2. 与 OpenClaw 的关键区别

OpenClaw 的模型是 Gateway 拥有 session 一切——session store、transcript 都在 Gateway 侧。这对 OpenClaw 成立，因为它的"运行时"本质上只是调 LLM API，没有真正的本地执行环境。

AutoReplication 不同：我们的 session 在远程机器上启动 Codex 进程、操作本地文件系统、运行训练脚本。运行体必须在 Runtime 侧。

因此我们采用 **双重所有权** 模型。

### D3. 数据归属表

| 数据 | 归属 | 说明 |
|------|------|------|
| Session identity（id, agent_id, task_id, dispatch_id, runtime_id） | **Gateway** | 全局唯一，路由依据 |
| Session lifecycle status | **Gateway 为权威源** | Runtime 通过 heartbeat 汇报变更 |
| Session 运行体（进程 handle, thread_id, 对话历史） | **Runtime** | 只有本机才能 attach / inject / terminate |
| Session transcript / events（完整消息流和事件流） | **Runtime** | Gateway 不主动存储，按需拉取 |
| Dispatch 完整记录（契约、payload、reply） | **Gateway** | 跨 Agent 协作的权威账本 |
| Task 和 stage_plan | **Gateway** | Agent 通过 Gateway API 更新 |
| session_inputs 待投递队列 | **Gateway** | Runtime 是 poll 模式，Gateway 暂存待注入消息 |
| Agent / Runtime 注册与状态 | **Gateway** | Runtime 通过 heartbeat 推送，Gateway 是查询入口 |

### D4. 通信模型

#### D4.1 基本约束

Runtime 始终是 client，Gateway 始终是 server。不假设 Gateway 能主动访问 Runtime（考虑 NAT、防火墙等限制）。所有通信由 Runtime 发起。

#### D4.2 Runtime → Gateway（主动推送，轻量）

Runtime 在每次 heartbeat（约 1 秒）中推送：

- Runtime 自身状态（idle / busy）
- Agent 状态（working / idle / fault）与 summary
- Session 状态变更（created → running → idle → failed 等）
- Dispatch 结果（reply）

这些都是轻量的状态字段，不含大 payload。

#### D4.3 Gateway → Runtime（通过 heartbeat response 下发请求）

Gateway 不能主动联系 Runtime，但可以在 heartbeat 的响应体中附带请求：

```json
{
  "ack": true,
  "requests": [
    {
      "type": "session_transcript",
      "session_id": "xxx",
      "since_event_id": "last-known-id"
    }
  ]
}
```

Runtime 收到 requests 后，在下一个 tick 中将数据推回 Gateway：

```
POST /api/sessions/{id}/transcript-sync
body: { events: [...], messages: [...] }
```

Gateway 暂存这份 transcript 供 UI 读取。用户关掉 Session Detail 页面后，Gateway 不再在 heartbeat response 中附带该 request，Runtime 也不再推送。

#### D4.4 Runtime 从 Gateway 拉取工作（已有机制）

Runtime 每次 tick 仍然主动拉取：

- `GET /api/runtime/launch-queue` → 待启动 session
- `GET /api/runtime/dispatch-queue` → 待处理 dispatch
- `GET /api/runtime/session-input-queue` → 待注入的 session inputs（steering / clarification）

### D5. Gateway 数据分层

**始终持有（薄层）：**

- Agent / Runtime / Session 注册表和状态摘要
- Dispatch 完整记录（跨 Agent 契约）
- Task 和 stage_plan
- session_inputs 暂存队列

**按需缓存（临时层）：**

- Session transcript（用户在 UI 中查看 Session Detail 时，Gateway 通过 heartbeat hook 从 Runtime 拉取并暂存；用户离开后可清除）

### D6. 场景分析：哪些 UI 操作需要从 Runtime 拉取

| UI 操作 | 需要 Runtime 数据？ | 说明 |
|---------|-------------------|------|
| 顶部全局状态 | 不需要 | heartbeat 已推送 |
| Task 三栏面板（stage timeline, canvas, activity） | 不需要 | dispatch / task / agent status 都在 Gateway |
| Agent Detail（session 列表、dispatch 列表） | 不需要 | Gateway 有 session 注册表 |
| Dispatch Detail（payload, reply） | 不需要 | Gateway 持有完整 dispatch |
| **Session Detail（transcript 和事件流）** | **需要** | Runtime 持有，通过 heartbeat hook 拉取 |
| Session steering 发送 | 不需要 | 写入 Gateway 的 session_inputs，Runtime 下次 poll 拿走 |

**结论：只有 Session Detail drill-down 需要从 Runtime 拉取数据。** 1 秒的 heartbeat 延迟在 drill-down 场景下完全可接受。

### D7. Session 持久化机制

从 OpenClaw 借鉴的三个核心思想：

1. **稳定的 session identity**：每个 session 通过 `task_id + agent_id + binding_kind` 构成稳定身份，确保 clarification 和 steering 总能路由回正确的 session。

2. **Send-to-existing-session 能力**：通过 Gateway 的 session_inputs 表 + Runtime 侧的 inject 机制实现。Codex CLI 原生支持 thread 持久化和继续输入，Runtime 利用 `thread_id` 对已有 session 继续注入。

3. **Session store 与 transcript 分层**：Gateway 持有 session 的结构化索引与状态（薄层），Runtime 持有完整的 transcript 和事件流（厚层）。
