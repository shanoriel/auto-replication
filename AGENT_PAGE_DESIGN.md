# Agent 管理页修正版方案

## 摘要

`Agent 管理` 不是一个普通“配置表单页”，而是一个 Runtime 在线时可操作的 Agent 控制台。
这里的 Agent 不再按“自由字段对象”理解，而是按当前系统定义收敛成：

- 一个 Runtime 机器上的本地 Agent 配置目录
- 由 `AGENT.md` 文件 + skill 启用集 + Agent 元数据 共同定义
- Session 启动时，Runtime 根据这套本地文件组装出实际运行环境

页面入口保持在标题下方这一行；切到 `Agent 管理` 后，下方主内容整块替换。

## 1. 产品模型

### Agent 的真实定义

Agent 本质上是一个 Runtime 本地配置单元，而不是 Gateway 里的纯数据库记录。
它至少由这些东西定义：

- 一份基础 `AGENT.md`
- 该 Runtime 可用的共享 skills 中，当前 Agent 启用了哪些
- 该 Agent 自己专属的 skills
- Agent 元数据：`agent_id`、显示名、头像、model、summary、enabled

`AGENT.md` 用来控制 Agent 的 role 和 rules。用户在配置页里修改的，不再叫 `preset`，而是直接编辑 `AGENT.md` 内容。

### Runtime 与展示范围

- `Runtime = 一台机器一个`
- 只展示在线 Runtime
- 离线 Runtime 不展示，也就不能管理其 Agent
- 新建 Agent 只能发生在当前选中的 Runtime 内

### Save 的语义

- 用户修改配置后，点击 `Save`
- Gateway 只做一件事：向该 Runtime 排队一个配置变更
- Runtime 下次 pull 到后，修改自己的本地文件并刷新 Agent
- UI 在这段时间显示 `Applying...`
- 只有 Runtime 确认应用成功，才显示成功

### Agent ID

- 新建时可填写 `agent_id`
- 创建后不可修改
- 理由：现有系统里 `task / dispatch / session / message / event / session_input` 都直接引用 `agent_id`

## 2. 页面结构与交互

### 顶部入口

标题下方这一行增加页面切换：

- `任务工作台`
- `Agent 管理`

`Agent 管理` 模式下，不显示 Task 三栏，而显示 Agent 管理页。

### 左侧栏

左栏只做两件事：

- 顶部 Runtime 选择器
- 当前 Runtime 下的 Agent 列表

具体布局：

- Runtime 下拉选择器放最上面
- 下面第一张卡是一个和普通 Agent 卡同尺寸的 `+` 卡片
  - 含义：向当前 Runtime 添加 Agent
- 再下面是当前 Runtime 的 Agent 列表

每个 Agent 卡显示：

- 头像
- 名称
- 状态点
- 简短副信息：`AGENT.md / model`
- 若有保存中的变更，显示 `Applying...`

头像规则：

- 默认使用当前的首字母头像逻辑
- 支持上传图片
- 未上传时自动回退到首字母头像

### 右侧主面板

右侧不拆中栏和右栏，做一个大面板。
这个大面板顶部有内部分页栏：

- `配置`
- `Skills`
- `Sessions`
- `Prompt 预览`

### 配置分页

展示和编辑：

- 头像
- 显示名
- Agent ID
  - 新建可编辑
  - 已存在 Agent 只读
- `AGENT.md`
- model
- summary
- enabled

这里不单独暴露“Runtime 切换”，因为 Agent 固定属于当前 Runtime。

这里用户原本理解里的“基础 preset”能力，统一替换为 `AGENT.md` 编辑器。
也就是说，用户不是选一个 preset，而是直接修改这个 Agent 的 `AGENT.md` 内容。

### Skills 分页

展示两类 skill：

- `Runtime 共享 skill`
- `Agent 专属 skill`

每个 skill 行显示：

- 名称
- 描述
- 来源 badge：`Runtime` 或 `Agent`
- 当前 Agent 是否启用
- 文件路径或逻辑来源摘要

关键语义：

- 即使 skill 来源于 Runtime 共享目录，用户在这里的启用/禁用也是对当前 Agent 生效
- 不会影响同 Runtime 的其他 Agent
- Runtime 级 skill 的意义是“当前 Runtime 可供选择的共享技能库”，不是全局开关

### Sessions 分页

展示当前 Agent 的所有 Session 列表，至少包含：

- session 标题
- 状态
- task
- 最近更新时间
- 最近摘要

交互：

- 点击某个 Session，弹出大窗口
- 大窗口展示完整会话内容
  - messages
  - events
  - 基本信息
- 窗口内提供 steer 输入框
  - 提交后走现有 `session_input` 机制

### Prompt 预览分页

第一版只展示基础 Agent Prompt，不展示某个具体 Task/Session 的完整启动 Prompt。

展示内容是：

- 当前 `AGENT.md` 文件内容
- 当前启用的 skills 如何影响 Agent 行为
- 当前 Agent 元数据对启动上下文的影响
- 最终归一化后的“基础 Agent Prompt 预览”

这个分页不依赖真实启动 Session。

## 3. 本地文件与 Runtime 模型

### Runtime 本地文件是真相

建议 Agent 本地目录结构固定为：

- `<state_root>/agents/<agent_id>/agent.json`
- `<state_root>/agents/<agent_id>/AGENT.md`
- `<state_root>/agents/<agent_id>/avatar.*`
- `<state_root>/agents/<agent_id>/skills/`（Agent 专属 skill）
- 可选：`<state_root>/runtime-skills/`（Runtime 共享 skill）

`agent.json` 至少包含：

- `agent_id`
- `name`
- `model`
- `summary`
- `enabled`
- `enabled_runtime_skills`
- `enabled_agent_skills`
- 头像元信息

`AGENT.md` 单独落盘，不塞进 `agent.json`。

### Runtime 启动模型调整

当前 Runtime 仍用 `--agent` 启动参数把 Agent 静态塞进内存，这个模型需要改。

第一版改成：

- Runtime 启动时从本地 `agents/` 目录加载 Agent
- 运行中定期 pull Agent 配置操作队列
- 应用后刷新内存中的 Agent 集合，再向 Gateway register/heartbeat

兼容性策略：

- `--agent` 不再作为长期真相
- 可保留为首次初始化本地 `agents/` 目录的 seed
- 一旦本地目录存在，之后都以本地文件为准

## 4. Gateway 与接口变化

### Gateway 的角色

Gateway 不保存 Agent 配置真相，只保存：

- 在线 Runtime 列表
- Runtime 上报的可用 `AGENT.md` 模板能力、可用共享 skill、model 能力
- Agent 的最后已知运行态投影
- 待 Runtime pull 的 Agent 配置变更队列
- 头像缓存副本（仅用于 UI 展示）

这里不再把 `preset` 作为用户可见概念；如果系统内部还保留模板来源或 role 模板映射，那只是内部实现，不直接暴露给用户。

### 新增队列

新增独立的 `runtime_agent_ops` 队列，不复用现有 `dispatch/runtime inbox`。

操作类型至少包括：

- `create_agent`
- `update_agent_config`
- `update_agent_skills`
- `enable_agent`
- `disable_agent`

状态至少包括：

- `pending`
- `claimed`
- `applied`
- `failed`

UI 统一把 `pending + claimed` 折叠显示成 `Applying...`

### Runtime 上报能力

Runtime 需要上报：

- 当前在线状态
- 当前 Runtime 可用的 `AGENT.md` 模板能力或 role 模板来源摘要
- 当前 Runtime 可用的共享 skills 列表
- 当前本地 Agent 列表摘要
- 可选：每个 Agent 的 prompt preview 版本号/摘要

### Session 能力复用

Session 管理和 steer 直接复用现有能力：

- `GET /api/sessions/{id}`
- `GET /api/sessions/{id}/messages`
- `GET /api/sessions/{id}/events`
- `POST /api/sessions/{id}/inputs`

这块不需要重新发明协议，只需要在 Agent 管理页里组织 UI。

## 5. Prompt 预览与 Skills 组装

### Prompt 预览的真实来源

由于现在系统实际是通过：

- 把 `AGENT.md` 拷到 workspace
- 把 skill 文件拷到 `CODEX_HOME/skills`
- 再让 Codex 启动

所以“system prompt”并不是代码里一条硬编码字符串。

第一版的 `Prompt 预览` 应定义成：

- 一个归一化预览结果
- 由 Runtime 本地文件生成
- 让用户看到“当前配置下，这个 Agent 会以什么基础行为被启动”

### Skills 组装语义

Session 启动时的有效 skills =

- 当前 Runtime 共享 skill 库中，被当前 Agent 启用的 skill
- 当前 Agent 专属 skill 目录中，被当前 Agent 启用的 skill

也就是说：

- Runtime skill 决定“有哪些共享 skill 可供选择”
- Agent skill toggle 决定“这个 Agent 最终挂载哪些 skill”

## 6. 验收场景

- 进入 `Agent 管理` 时，只能看到在线 Runtime。
- 左栏顶部先选 Runtime，再看该 Runtime 的 Agent。
- 左栏第一张 `+` 卡片可以在当前 Runtime 内创建 Agent。
- Agent 创建后写入 Runtime 本地文件，而不是长期依赖启动参数。
- 在 `Skills` 分页中，Runtime 共享 skill 可见，但开关只影响当前 Agent。
- 在 `Sessions` 分页中，能看到该 Agent 的所有 Session。
- 点击某个 Session 后，弹大窗口展示完整会话，并能 steer。
- `Prompt 预览` 分页显示基础 Agent Prompt，而不是 Task 级完整启动 prompt。
- 点击 `Save` 后，UI 显示 `Applying...`，直到 Runtime pull 并确认应用成功。
- 上传头像后，Agent 卡和配置页都显示图片；未上传则回退到首字母头像。

## 假设与默认选择

- Agent 的核心定义是 `AGENT.md + skills 选择 + Agent 元数据`。
- Runtime 共享 skill 是“可选库”，不是“全体 Agent 强制启用”。
- Prompt 预览第一版只做基础 Agent Prompt。
- Runtime 离线时完全不展示，不做只读历史浏览。
- 第一版不做跨 Runtime 移动 Agent，不做硬删除。
