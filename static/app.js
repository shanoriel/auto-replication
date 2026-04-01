(function () {
  const standaloneAgentPage = window.__AUTOREP_PAGE__ === "agents";
  const state = {
    mode: standaloneAgentPage ? "agents" : "tasks",
    overview: null,
    tasks: [],
    allAgents: [],
    selectedTaskId: null,
    board: null,
    showTaskModal: false,
    taskDraft: defaultTaskDraft(),
    runtimes: [],
    selectedRuntimeId: null,
    runtimeSnapshot: null,
    selectedManagedAgentId: null,
    managedAgentDraft: null,
    managedAgentTab: "config",
    managedSessions: [],
    sessionModal: null,
    pollHandle: null,
  };

  function defaultTaskDraft() {
    return {
      title: "",
      entryAgentId: "",
      objective: "",
      initialInput: "",
      summary: "",
      participantAgentIds: [],
      statusText: "",
    };
  }

  function emptyAgentDraft(runtimeId) {
    return {
      isNew: true,
      runtimeId,
      agentId: "",
      name: "",
      model: "",
      summary: "",
      enabled: true,
      roleHint: "",
      agentMd: "# Agent\n\nYou are the AutoReplication agent.\n",
      enabledRuntimeSkills: [],
      enabledAgentSkills: [],
      avatarUrl: null,
      avatarDataUrl: null,
      statusText: "",
      applying: false,
    };
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function localizeStatus(status) {
    const map = {
      idle: "空闲",
      busy: "忙碌",
      running: "运行中",
      created: "已创建",
      pending: "待处理",
      accepted: "已接收",
      replied: "已回复",
      completed: "已完成",
      failed: "失败",
      offline: "离线",
      applied: "已应用",
      claimed: "Applying",
    };
    return map[status] || status || "未设置";
  }

  function formatTime(value) {
    if (!value) return "未设置";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString([], {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function truncate(value, limit = 80) {
    const text = String(value ?? "").trim();
    if (!text) return "";
    return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
  }

  async function fetchJson(path, options) {
    const response = await fetch(path, options);
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`;
      try {
        const payload = await response.json();
        if (payload?.detail) message = String(payload.detail);
      } catch (error) {}
      throw new Error(message);
    }
    return response.json();
  }

  function avatarHtml(agent, sizeClass = "avatar") {
    const url = agent?.avatarUrl || agent?.avatar_url || null;
    const name = agent?.name || agent?.id || agent?.agentId || "?";
    if (url) {
      return `<div class="${sizeClass}"><img src="${escapeHtml(url)}" alt="${escapeHtml(name)}"></div>`;
    }
    return `<div class="${sizeClass}">${escapeHtml(String(name).slice(0, 2).toUpperCase())}</div>`;
  }

  function statusDotClass(status) {
    if (status === "busy" || status === "running") return "busy";
    if (status === "failed" || status === "offline") return "failed";
    return "idle";
  }

  function getOnlineRuntimeIds() {
    return new Set((state.runtimes || []).map((item) => item.id));
  }

  function getTaskCandidateAgents() {
    const onlineRuntimeIds = getOnlineRuntimeIds();
    return (state.allAgents || []).filter((agent) => {
      const metadata = agent.metadata || {};
      return metadata.enabled !== false && metadata.present !== false && onlineRuntimeIds.has(agent.runtime_id);
    });
  }

  function getSelectedManagedAgent() {
    if (!state.runtimeSnapshot) return null;
    return (state.runtimeSnapshot.agents || []).find((agent) => agent.id === state.selectedManagedAgentId) || null;
  }

  function syncManagedDraftFromAgent(agent) {
    if (!agent) {
      state.managedAgentDraft = emptyAgentDraft(state.selectedRuntimeId);
      return;
    }
    state.managedAgentDraft = {
      isNew: false,
      runtimeId: state.selectedRuntimeId,
      agentId: agent.id,
      name: agent.name || agent.id,
      model: agent.model || "",
      summary: agent.summary || "",
      enabled: agent.enabled !== false,
      roleHint: agent.role_hint || "",
      agentMd: agent.agent_md || "",
      enabledRuntimeSkills: [...(agent.enabled_runtime_skills || [])],
      enabledAgentSkills: [...(agent.enabled_agent_skills || [])],
      avatarUrl: agent.avatar_url || null,
      avatarDataUrl: null,
      statusText: "",
      applying: !!agent.applying,
    };
  }

  function captureDraftsFromDom() {
    const taskModal = document.querySelector("[data-modal='task']");
    if (taskModal && state.showTaskModal) {
      state.taskDraft = {
        title: document.getElementById("task-title")?.value || "",
        entryAgentId: document.getElementById("task-entry-agent")?.value || "",
        objective: document.getElementById("task-objective")?.value || "",
        initialInput: document.getElementById("task-initial-input")?.value || "",
        summary: document.getElementById("task-summary")?.value || "",
        participantAgentIds: [...document.querySelectorAll("[data-task-agent]:checked")].map((item) => item.value),
        statusText: document.getElementById("task-form-status")?.textContent || "",
      };
    }

    if (state.mode === "agents" && state.managedAgentDraft) {
      state.managedAgentDraft = {
        ...state.managedAgentDraft,
        agentId: document.getElementById("managed-agent-id")?.value || state.managedAgentDraft.agentId,
        name: document.getElementById("managed-agent-name")?.value || "",
        model: document.getElementById("managed-agent-model")?.value || "",
        summary: document.getElementById("managed-agent-summary")?.value || "",
        roleHint: document.getElementById("managed-agent-role-hint")?.value || "",
        agentMd: document.getElementById("managed-agent-md")?.value || "",
        enabled: !!document.getElementById("managed-agent-enabled")?.checked,
      };
    }

    if (state.sessionModal) {
      state.sessionModal.steerText = document.getElementById("session-steer-input")?.value || "";
    }
  }

  async function loadOverview() {
    state.overview = await fetchJson("/api/overview");
  }

  async function loadTasksAndAgents() {
    const [tasks, agents] = await Promise.all([
      fetchJson("/api/tasks"),
      fetchJson("/api/agents"),
    ]);
    state.tasks = tasks;
    state.allAgents = agents;
    if (!state.selectedTaskId && tasks.length) {
      state.selectedTaskId = tasks[0].id;
    }
    if (state.selectedTaskId && !tasks.some((task) => task.id === state.selectedTaskId)) {
      state.selectedTaskId = tasks[0]?.id || null;
    }
  }

  async function loadBoard() {
    if (!state.selectedTaskId) {
      state.board = null;
      return;
    }
    state.board = await fetchJson(`/api/tasks/${encodeURIComponent(state.selectedTaskId)}/board`);
  }

  async function loadAgentManagement() {
    state.runtimes = await fetchJson("/api/agent-management/runtimes");
    if (!state.selectedRuntimeId && state.runtimes.length) {
      state.selectedRuntimeId = state.runtimes[0].id;
    }
    if (state.selectedRuntimeId && !state.runtimes.some((runtime) => runtime.id === state.selectedRuntimeId)) {
      state.selectedRuntimeId = state.runtimes[0]?.id || null;
    }
    if (!state.selectedRuntimeId) {
      state.runtimeSnapshot = null;
      state.managedSessions = [];
      return;
    }
    state.runtimeSnapshot = await fetchJson(`/api/agent-management/runtimes/${encodeURIComponent(state.selectedRuntimeId)}`);
    if (!state.selectedManagedAgentId && state.runtimeSnapshot.agents.length) {
      state.selectedManagedAgentId = state.runtimeSnapshot.agents[0].id;
      syncManagedDraftFromAgent(state.runtimeSnapshot.agents[0]);
    }
    if (state.selectedManagedAgentId === "__new__") {
      state.managedAgentDraft = state.managedAgentDraft || emptyAgentDraft(state.selectedRuntimeId);
      return;
    }
    const selected = getSelectedManagedAgent();
    if (!selected && state.runtimeSnapshot.agents.length) {
      state.selectedManagedAgentId = state.runtimeSnapshot.agents[0].id;
      syncManagedDraftFromAgent(state.runtimeSnapshot.agents[0]);
    } else if (!selected) {
      state.selectedManagedAgentId = null;
      state.managedAgentDraft = null;
    } else if (!state.managedAgentDraft || state.managedAgentDraft.agentId !== selected.id || !document.activeElement || !document.activeElement.closest(".agent-main")) {
      syncManagedDraftFromAgent(selected);
    }
    if (state.managedAgentTab === "sessions" && state.selectedManagedAgentId && state.selectedManagedAgentId !== "__new__") {
      state.managedSessions = await fetchJson(`/api/sessions?agent_id=${encodeURIComponent(state.selectedManagedAgentId)}`);
    } else {
      state.managedSessions = [];
    }
  }

  async function loadSessionModal() {
    if (!state.sessionModal?.sessionId) return;
    const sessionId = state.sessionModal.sessionId;
    const [session, messages, events] = await Promise.all([
      fetchJson(`/api/sessions/${encodeURIComponent(sessionId)}`),
      fetchJson(`/api/sessions/${encodeURIComponent(sessionId)}/messages?limit=100`),
      fetchJson(`/api/sessions/${encodeURIComponent(sessionId)}/events?limit=100`),
    ]);
    state.sessionModal = {
      ...state.sessionModal,
      loading: false,
      session,
      messages,
      events,
    };
  }

  async function refreshAll() {
    captureDraftsFromDom();
    await Promise.all([
      loadOverview(),
      loadTasksAndAgents(),
      loadAgentManagement(),
    ]);
    await loadBoard();
    if (state.sessionModal?.sessionId) {
      await loadSessionModal();
    }
    render();
  }

  function renderStatusStrip() {
    if (!state.overview) return "";
    const cards = [
      {
        label: "Gateway",
        value: localizeStatus(state.overview.gateway.status),
        meta: `${state.overview.gateway.app} · 端口 ${state.overview.gateway.port}`,
      },
      {
        label: "Runtime",
        value: state.overview.runtimes.total,
        meta: `${state.overview.runtimes.by_status.idle || 0} 空闲 · ${state.overview.runtimes.by_status.busy || 0} 忙碌`,
      },
      {
        label: "工作中 Agent",
        value: state.overview.agents.working,
        meta: `共 ${state.overview.agents.total} 个 Agent`,
      },
      {
        label: "运行中任务",
        value: state.overview.tasks.running,
        meta: `共 ${state.overview.tasks.total} 个任务`,
      },
      {
        label: "等待中的 Dispatch",
        value: state.overview.dispatches.waiting_reply,
        meta: `共 ${state.overview.dispatches.total} 个 Dispatch`,
      },
    ];
    return cards
      .map(
        (card) => `
          <div class="surface status-card">
            <div class="status-label">${escapeHtml(card.label)}</div>
            <div class="status-value">${escapeHtml(card.value)}</div>
            <div class="status-meta">${escapeHtml(card.meta)}</div>
          </div>
        `
      )
      .join("");
  }

  function renderStages() {
    const stages = state.board?.task?.stage_plan?.stages || [];
    if (!stages.length) {
      return `<div class="empty-state">这个任务还没有阶段计划。</div>`;
    }
    return `<div class="list">${stages
      .map(
        (stage) => `
          <div class="item-card">
            <div class="item-title">${escapeHtml(stage.title || "未命名阶段")}</div>
            <div class="item-meta">${escapeHtml(localizeStatus(stage.status || "pending"))} · ${escapeHtml(formatTime(stage.updated_at))}</div>
            <div class="item-meta">${escapeHtml(stage.summary || stage.description || "暂无摘要。")}</div>
          </div>
        `
      )
      .join("")}</div>`;
  }

  function renderTaskPage() {
    const taskOptions = state.tasks.length
      ? state.tasks
          .map(
            (task) => `
              <option value="${escapeHtml(task.id)}" ${task.id === state.selectedTaskId ? "selected" : ""}>
                ${escapeHtml(task.title)}
              </option>
            `
          )
          .join("")
      : `<option value="">暂无任务</option>`;

    let boardHtml = `<div class="empty-state">创建一个任务以启动控制闭环。</div>`;
    if (state.board) {
      const task = state.board.task;
      const sessions = state.board.sessions || [];
      const dispatches = state.board.dispatches || [];
      const participants = state.board.participant_agents || [];
      boardHtml = `
        <div class="task-board">
          <section class="surface stack">
            <div class="panel-header"><div class="panel-title">任务概览</div></div>
            <div class="panel-body stack">
              <div>
                <h2 style="margin:0 0 8px 0;">${escapeHtml(task.title)}</h2>
                <div class="muted">${escapeHtml(task.summary || task.objective || "暂无摘要。")}</div>
              </div>
              <div class="chip-row">
                <span class="chip">${escapeHtml(state.board.counts.participant_agents)} 个参与者</span>
                <span class="chip">${escapeHtml(state.board.counts.running_sessions)} 个 Session</span>
                <span class="chip">${escapeHtml(state.board.counts.open_dispatches)} 个 Dispatch</span>
              </div>
              <div>
                <div class="panel-title" style="margin-bottom:8px;">参与 Agent</div>
                <div class="chip-row">
                  ${participants.length ? participants.map((agent) => `<span class="chip">${escapeHtml(agent.name || agent.id)}</span>`).join("") : `<span class="muted">暂无</span>`}
                </div>
              </div>
              <div>
                <div class="panel-title" style="margin-bottom:8px;">阶段时间线</div>
                ${renderStages()}
              </div>
            </div>
          </section>
          <section class="surface">
            <div class="panel-header"><div class="panel-title">Sessions</div></div>
            <div class="panel-body">
              ${sessions.length
                ? `<div class="list">${sessions
                    .map(
                      (session) => `
                        <button class="list-button session-row" data-action="open-session" data-session-id="${escapeHtml(session.id)}" type="button">
                          <div class="item-title">${escapeHtml(session.title)}</div>
                          <div class="session-meta">
                            <span>${escapeHtml(session.agent_id)}</span>
                            <span>${escapeHtml(localizeStatus(session.status))}</span>
                            <span>${escapeHtml(session.model || "未设置 model")}</span>
                            <span>${escapeHtml(formatTime(session.updated_at))}</span>
                          </div>
                          <div class="item-meta">${escapeHtml(session.summary || "暂无 Session 摘要。")}</div>
                        </button>
                      `
                    )
                    .join("")}</div>`
                : `<div class="empty-state">暂无 Session。</div>`}
            </div>
          </section>
          <section class="surface">
            <div class="panel-header"><div class="panel-title">Dispatches</div></div>
            <div class="panel-body">
              ${dispatches.length
                ? `<div class="list">${dispatches
                    .map(
                      (dispatch) => `
                        <div class="item-card">
                          <div class="item-title">${escapeHtml(dispatch.payload.title || dispatch.payload.goal || dispatch.kind)}</div>
                          <div class="item-meta">${escapeHtml(dispatch.from_agent_id)} → ${escapeHtml(dispatch.to_agent_id)} · ${escapeHtml(localizeStatus(dispatch.status))}</div>
                          <div class="item-meta">${escapeHtml(dispatch.reply?.summary || dispatch.payload.question || "暂无更多内容。")}</div>
                        </div>
                      `
                    )
                    .join("")}</div>`
                : `<div class="empty-state">暂无 Dispatch。</div>`}
            </div>
          </section>
        </div>
      `;
    }

    return `
      <section class="surface">
        <div class="panel-body task-controls">
          <label class="label">
            任务
            <select id="task-select">${taskOptions}</select>
          </label>
          <button class="primary-btn" data-action="open-task-modal" type="button">新建任务</button>
          <button class="secondary-btn" data-action="refresh" type="button">刷新</button>
        </div>
      </section>
      ${boardHtml}
    `;
  }

  function renderAgentList() {
    if (!state.runtimeSnapshot) {
      return `<div class="empty-state">当前没有在线 Runtime。</div>`;
    }
    const agents = state.runtimeSnapshot.agents || [];
    return `
      <div class="agent-list">
        <button class="agent-plus" data-action="new-agent" type="button">+</button>
        ${agents.length
          ? agents
              .map(
                (agent) => `
                  <button class="agent-card ${agent.id === state.selectedManagedAgentId ? "active" : ""}" data-action="select-managed-agent" data-agent-id="${escapeHtml(agent.id)}" type="button">
                    <div class="agent-row">
                      ${avatarHtml(agent)}
                      <div style="min-width:0;flex:1;">
                        <div style="display:flex;align-items:center;gap:8px;">
                          <span class="agent-name">${escapeHtml(agent.name || agent.id)}</span>
                          <span class="status-dot ${statusDotClass(agent.status)}"></span>
                        </div>
                        <div class="agent-sub">${escapeHtml(agent.model || "未设置 model")} · ${escapeHtml(agent.id)}</div>
                      </div>
                    </div>
                    <div class="agent-sub">${escapeHtml(agent.applying ? "Applying..." : (agent.summary || "暂无摘要。"))}</div>
                  </button>
                `
              )
              .join("")
          : `<div class="empty-state">当前 Runtime 还没有 Agent。</div>`}
      </div>
    `;
  }

  function renderSkillList(skills, selectedIds, source) {
    if (!skills.length) {
      return `<div class="empty-state">暂无 ${source === "runtime" ? "共享" : "专属"} skill。</div>`;
    }
    return `
      <div class="skills-list">
        ${skills
          .map((skill) => {
            const checked = selectedIds.includes(skill.skill_id);
            return `
              <label class="skill-card">
                <div class="skill-head">
                  <div>
                    <div class="item-title">${escapeHtml(skill.name || skill.skill_id)}</div>
                    <div class="item-meta">${escapeHtml(skill.description || "暂无描述。")}</div>
                  </div>
                  <span class="badge">${escapeHtml(source === "runtime" ? "Runtime" : "Agent")}</span>
                </div>
                <div class="item-meta">${escapeHtml(skill.path || "")}</div>
                <div class="inline-actions">
                  <input class="skill-toggle" type="checkbox" data-action="toggle-skill" data-source="${escapeHtml(source)}" value="${escapeHtml(skill.skill_id)}" ${checked ? "checked" : ""}>
                  <span class="notice">${checked ? "当前已启用" : "当前未启用"}</span>
                </div>
              </label>
            `;
          })
          .join("")}
      </div>
    `;
  }

  function renderManagedConfig(agent, draft) {
    if (!draft) {
      return `<div class="empty-state">请选择或新建一个 Agent。</div>`;
    }
    const runtimeModels = state.runtimeSnapshot?.runtime?.available_models || [];
    const modelOptions = runtimeModels.length
      ? runtimeModels
          .map(
            (item) => `<option value="${escapeHtml(item)}" ${item === draft.model ? "selected" : ""}>${escapeHtml(item)}</option>`
          )
          .join("")
      : `<option value="">未上报可用 model</option>`;
    return `
      <div class="form-grid">
        <div class="two-col">
          <label class="label">
            显示名
            <input id="managed-agent-name" value="${escapeHtml(draft.name)}">
          </label>
          <label class="label">
            Agent ID
            <input id="managed-agent-id" value="${escapeHtml(draft.agentId)}" ${draft.isNew ? "" : "readonly"}>
          </label>
        </div>
        <div class="two-col">
          <label class="label">
            Model
            <select id="managed-agent-model">
              <option value="">未设置</option>
              ${modelOptions}
            </select>
          </label>
          <label class="label">
            Role Hint
            <input id="managed-agent-role-hint" value="${escapeHtml(draft.roleHint || "")}">
          </label>
        </div>
        <label class="label">
          Summary
          <textarea id="managed-agent-summary">${escapeHtml(draft.summary || "")}</textarea>
        </label>
        <label class="label">
          AGENT.md
          <textarea id="managed-agent-md" class="mono" style="min-height:280px;">${escapeHtml(draft.agentMd || "")}</textarea>
        </label>
        <div class="two-col">
          <label class="label">
            头像
            <div class="inline-actions">
              ${avatarHtml({ avatarUrl: draft.avatarDataUrl || draft.avatarUrl, name: draft.name || draft.agentId })}
              <input id="managed-agent-avatar" class="file-input" type="file" accept="image/png,image/jpeg,image/webp">
            </div>
          </label>
          <label class="label">
            Enabled
            <div class="inline-actions">
              <input id="managed-agent-enabled" type="checkbox" style="width:auto;" ${draft.enabled ? "checked" : ""}>
              <span class="notice">${draft.enabled ? "当前启用" : "当前禁用"}</span>
            </div>
          </label>
        </div>
      </div>
    `;
  }

  function renderManagedSessions() {
    if (state.selectedManagedAgentId === "__new__") {
      return `<div class="empty-state">新建 Agent 还没有 Session。</div>`;
    }
    if (!state.managedSessions.length) {
      return `<div class="empty-state">这个 Agent 暂无 Session。</div>`;
    }
    return `
      <div class="session-table">
        ${state.managedSessions
          .map(
            (session) => `
              <button class="list-button session-row" data-action="open-session" data-session-id="${escapeHtml(session.id)}" type="button">
                <div class="item-title">${escapeHtml(session.title)}</div>
                <div class="session-meta">
                  <span>${escapeHtml(localizeStatus(session.status))}</span>
                  <span>${escapeHtml(session.task_id || "无 task")}</span>
                  <span>${escapeHtml(formatTime(session.updated_at))}</span>
                </div>
                <div class="item-meta">${escapeHtml(session.summary || "暂无摘要。")}</div>
              </button>
            `
          )
          .join("")}
      </div>
    `;
  }

  function renderPromptPreview(agent) {
    const preview = agent?.prompt_preview || {};
    return `
      <div class="stack">
        <section class="surface">
          <div class="panel-header"><div class="panel-title">归一化 Prompt 预览</div></div>
          <div class="panel-body mono">${escapeHtml(preview.normalized_text || "暂无预览。")}</div>
        </section>
        <section class="surface">
          <div class="panel-header"><div class="panel-title">Skills 摘要</div></div>
          <div class="panel-body mono">${escapeHtml(preview.skills_summary || "none")}</div>
        </section>
      </div>
    `;
  }

  function renderAgentPage() {
    const runtimeOptions = state.runtimes.length
      ? state.runtimes
          .map(
            (runtime) => `
              <option value="${escapeHtml(runtime.id)}" ${runtime.id === state.selectedRuntimeId ? "selected" : ""}>
                ${escapeHtml(runtime.name)} · ${escapeHtml(runtime.machine_id)}
              </option>
            `
          )
          .join("")
      : `<option value="">暂无在线 Runtime</option>`;
    const selected = getSelectedManagedAgent();
    const draft = state.managedAgentDraft;
    const runtimeSkills = state.runtimeSnapshot?.runtime?.shared_skills || [];
    const agentSkills = selected?.agent_skill_inventory || [];
    let body = `<div class="empty-state">选择一个 Agent 开始编辑。</div>`;
    if (draft) {
      if (state.managedAgentTab === "config") {
        body = renderManagedConfig(selected, draft);
      } else if (state.managedAgentTab === "skills") {
        body = `
          <div class="stack">
            <section class="surface">
              <div class="panel-header"><div class="panel-title">Runtime 共享 Skills</div></div>
              <div class="panel-body">${renderSkillList(runtimeSkills, draft.enabledRuntimeSkills || [], "runtime")}</div>
            </section>
            <section class="surface">
              <div class="panel-header"><div class="panel-title">Agent 专属 Skills</div></div>
              <div class="panel-body">${renderSkillList(agentSkills, draft.enabledAgentSkills || [], "agent")}</div>
            </section>
          </div>
        `;
      } else if (state.managedAgentTab === "sessions") {
        body = renderManagedSessions();
      } else if (state.managedAgentTab === "prompt") {
        body = renderPromptPreview(selected || draft);
      }
    }
    return `
      <div class="agent-layout">
        <aside class="agent-sidebar">
          <section class="surface">
            <div class="panel-header"><div class="panel-title">Runtime</div></div>
            <div class="panel-body">
              <label class="label">
                当前 Runtime
                <select id="runtime-select">${runtimeOptions}</select>
              </label>
              <div class="notice" style="margin-top:10px;">只展示在线 Runtime。</div>
            </div>
          </section>
          <section class="surface">
            <div class="panel-header"><div class="panel-title">Agents</div></div>
            <div class="panel-body">
              ${renderAgentList()}
            </div>
          </section>
        </aside>
        <section class="surface agent-main">
          <div class="panel-header">
            <div>
              <div class="panel-title">Agent 管理</div>
              <div style="margin-top:4px;font-weight:600;">${escapeHtml(draft?.name || selected?.name || "未选择 Agent")}</div>
              <div class="notice">${escapeHtml(draft?.statusText || (selected?.applying ? "Applying..." : ""))}</div>
            </div>
            <div class="inline-actions">
              <div class="tab-strip">
                <button class="tab-btn ${state.managedAgentTab === "config" ? "active" : ""}" data-action="set-agent-tab" data-tab="config" type="button">配置</button>
                <button class="tab-btn ${state.managedAgentTab === "skills" ? "active" : ""}" data-action="set-agent-tab" data-tab="skills" type="button">Skills</button>
                <button class="tab-btn ${state.managedAgentTab === "sessions" ? "active" : ""}" data-action="set-agent-tab" data-tab="sessions" type="button">Sessions</button>
                <button class="tab-btn ${state.managedAgentTab === "prompt" ? "active" : ""}" data-action="set-agent-tab" data-tab="prompt" type="button">Prompt 预览</button>
              </div>
              <button class="primary-btn" data-action="save-agent" type="button" ${draft ? "" : "disabled"}>Save</button>
            </div>
          </div>
          <div class="panel-body">${body}</div>
        </section>
      </div>
    `;
  }

  function renderTaskModal() {
    if (!state.showTaskModal) return "";
    const agents = getTaskCandidateAgents();
    const entryOptions = agents.length
      ? agents
          .map(
            (agent) => `
              <option value="${escapeHtml(agent.id)}" ${agent.id === state.taskDraft.entryAgentId ? "selected" : ""}>
                ${escapeHtml(agent.name || agent.id)} · ${escapeHtml(agent.id)}
              </option>
            `
          )
          .join("")
      : `<option value="">暂无可用 Agent</option>`;
    return `
      <div class="modal-backdrop" data-modal="task">
        <div class="modal">
          <div class="panel-header">
            <div class="panel-title">创建任务</div>
            <button class="secondary-btn" data-action="close-task-modal" type="button">关闭</button>
          </div>
          <div class="modal-body">
            <div class="form-grid">
              <label class="label">
                标题
                <input id="task-title" value="${escapeHtml(state.taskDraft.title)}">
              </label>
              <label class="label">
                入口 Agent
                <select id="task-entry-agent">${entryOptions}</select>
              </label>
              <label class="label">
                目标
                <textarea id="task-objective">${escapeHtml(state.taskDraft.objective)}</textarea>
              </label>
              <label class="label">
                初始提示词
                <textarea id="task-initial-input">${escapeHtml(state.taskDraft.initialInput)}</textarea>
              </label>
              <label class="label">
                操作员摘要
                <textarea id="task-summary">${escapeHtml(state.taskDraft.summary)}</textarea>
              </label>
              <div class="label">
                参与 Agent
                <div class="list">
                  ${agents
                    .map(
                      (agent) => `
                        <label class="item-card">
                          <div class="inline-actions">
                            <input data-task-agent type="checkbox" value="${escapeHtml(agent.id)}" style="width:auto;" ${state.taskDraft.participantAgentIds.includes(agent.id) ? "checked" : ""}>
                            <span>${escapeHtml(agent.name || agent.id)} · ${escapeHtml(agent.id)}</span>
                          </div>
                        </label>
                      `
                    )
                    .join("")}
                </div>
              </div>
              <div class="inline-actions">
                <button class="primary-btn" data-action="create-task" type="button">创建任务</button>
                <span id="task-form-status" class="notice">${escapeHtml(state.taskDraft.statusText || "")}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderSessionModal() {
    if (!state.sessionModal) return "";
    const { loading, session, messages, events, steerText, statusText } = state.sessionModal;
    return `
      <div class="modal-backdrop" data-modal="session">
        <div class="modal">
          <div class="panel-header">
            <div>
              <div class="panel-title">Session</div>
              <div style="margin-top:4px;font-weight:600;">${escapeHtml(session?.title || "加载中...")}</div>
            </div>
            <button class="secondary-btn" data-action="close-session-modal" type="button">关闭</button>
          </div>
          <div class="modal-body">
            ${loading
              ? `<div class="empty-state">正在加载 Session 详情...</div>`
              : `
                <div class="modal-grid">
                  <section class="surface">
                    <div class="panel-header"><div class="panel-title">Messages</div></div>
                    <div class="panel-body">
                      ${messages?.length
                        ? `<div class="message-list">${messages
                            .map(
                              (message) => `
                                <div class="message-card">
                                  <div class="message-head">
                                    <span>${escapeHtml(message.sender)} · ${escapeHtml(message.direction)}</span>
                                    <span>${escapeHtml(formatTime(message.created_at))}</span>
                                  </div>
                                  <div class="mono" style="margin-top:8px;">${escapeHtml(message.content)}</div>
                                </div>
                              `
                            )
                            .join("")}</div>`
                        : `<div class="empty-state">暂无消息。</div>`}
                    </div>
                  </section>
                  <section class="stack">
                    <section class="surface">
                      <div class="panel-header"><div class="panel-title">Session Info</div></div>
                      <div class="panel-body kv-table">
                        <div><strong>ID:</strong> ${escapeHtml(session.id)}</div>
                        <div><strong>Agent:</strong> ${escapeHtml(session.agent_id)}</div>
                        <div><strong>状态:</strong> ${escapeHtml(localizeStatus(session.status))}</div>
                        <div><strong>Task:</strong> ${escapeHtml(session.task_id || "未设置")}</div>
                        <div><strong>Dispatch:</strong> ${escapeHtml(session.dispatch_id || "未设置")}</div>
                        <div><strong>Model:</strong> ${escapeHtml(session.model || "未设置")}</div>
                        <div><strong>更新于:</strong> ${escapeHtml(formatTime(session.updated_at))}</div>
                      </div>
                    </section>
                    <section class="surface">
                      <div class="panel-header"><div class="panel-title">Events</div></div>
                      <div class="panel-body">
                        ${events?.length
                          ? `<div class="event-list">${events
                              .map(
                                (event) => `
                                  <div class="event-card">
                                    <div class="event-head">
                                      <span>${escapeHtml(event.event_type)}</span>
                                      <span>${escapeHtml(formatTime(event.created_at))}</span>
                                    </div>
                                    <div class="mono" style="margin-top:8px;">${escapeHtml(JSON.stringify(event.payload, null, 2))}</div>
                                  </div>
                                `
                              )
                              .join("")}</div>`
                          : `<div class="empty-state">暂无事件。</div>`}
                      </div>
                    </section>
                    <section class="surface">
                      <div class="panel-header"><div class="panel-title">Steer</div></div>
                      <div class="panel-body">
                        <label class="label">
                          Steering 输入
                          <textarea id="session-steer-input">${escapeHtml(steerText || "")}</textarea>
                        </label>
                        <div class="inline-actions">
                          <button class="primary-btn" data-action="submit-steer" type="button">发送</button>
                          <span class="notice">${escapeHtml(statusText || "")}</span>
                        </div>
                      </div>
                    </section>
                  </section>
                </div>
              `}
          </div>
        </div>
      </div>
    `;
  }

  function render() {
    const app = document.getElementById("app");
    const controlRow = standaloneAgentPage
      ? `
        <section class="surface">
          <div class="control-row">
            <div class="mode-tabs">
              <a class="secondary-btn" href="/">任务工作台</a>
              <button class="mode-tab active" type="button">Agent 管理</button>
            </div>
            <button class="secondary-btn" data-action="refresh" type="button">刷新</button>
          </div>
        </section>
      `
      : `
        <section class="surface">
          <div class="control-row">
            <div class="mode-tabs">
              <button class="mode-tab ${state.mode === "tasks" ? "active" : ""}" data-action="switch-mode" data-mode="tasks" type="button">任务工作台</button>
              <button class="mode-tab ${state.mode === "agents" ? "active" : ""}" data-action="switch-mode" data-mode="agents" type="button">Agent 管理</button>
            </div>
            <button class="secondary-btn" data-action="refresh" type="button">刷新</button>
          </div>
        </section>
      `;
    app.innerHTML = `
      <div class="shell">
        <section class="masthead">
          <div class="masthead-copy">
            <h1>AutoReplication</h1>
            <div class="subtitle">面向多 Runtime、多 Agent 的研究控制台。现在包含任务工作台和基于本地 Agent 文件真相的 Agent 管理页。</div>
          </div>
          <div class="status-strip">${renderStatusStrip()}</div>
        </section>
        ${controlRow}
        ${state.mode === "tasks" ? renderTaskPage() : renderAgentPage()}
      </div>
    `;
    document.getElementById("modal-root").innerHTML = `${renderTaskModal()}${renderSessionModal()}`;
  }

  async function openSessionModal(sessionId) {
    state.sessionModal = {
      sessionId,
      loading: true,
      session: null,
      messages: [],
      events: [],
      steerText: "",
      statusText: "",
    };
    render();
    try {
      await loadSessionModal();
      render();
    } catch (error) {
      state.sessionModal = {
        ...state.sessionModal,
        loading: false,
        statusText: error.message,
      };
      render();
    }
  }

  async function createTask() {
    captureDraftsFromDom();
    const draft = state.taskDraft;
    if (!draft.title.trim() || !draft.entryAgentId || !draft.initialInput.trim()) {
      state.taskDraft.statusText = "标题、入口 Agent 和初始提示词为必填项。";
      render();
      return;
    }
    state.taskDraft.statusText = "创建中...";
    render();
    try {
      const payload = {
        title: draft.title.trim(),
        created_by: "human",
        entry_agent_id: draft.entryAgentId,
        participant_agent_ids: draft.participantAgentIds,
        objective: draft.objective.trim() || draft.initialInput.trim(),
        initial_input: draft.initialInput.trim(),
        summary: draft.summary.trim() || null,
        stage_plan: {
          stages: [
            {
              title: "任务已创建",
              status: "active",
              summary: "由操作员创建了初始任务框架。",
              updated_at: new Date().toISOString(),
            },
          ],
        },
      };
      const task = await fetchJson("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      state.selectedTaskId = task.id;
      state.showTaskModal = false;
      state.taskDraft = defaultTaskDraft();
      await refreshAll();
    } catch (error) {
      state.taskDraft.statusText = error.message;
      render();
    }
  }

  async function saveManagedAgent() {
    captureDraftsFromDom();
    const draft = state.managedAgentDraft;
    if (!draft || !draft.runtimeId) return;
    if (!draft.agentId.trim() || !draft.name.trim() || !draft.agentMd.trim()) {
      state.managedAgentDraft.statusText = "Agent ID、显示名和 AGENT.md 为必填项。";
      render();
      return;
    }
    state.managedAgentDraft.statusText = "Saving...";
    render();
    const payload = {
      name: draft.name.trim(),
      model: draft.model || null,
      summary: draft.summary.trim() || null,
      enabled: draft.enabled,
      role_hint: draft.roleHint.trim() || null,
      agent_md: draft.agentMd,
      enabled_runtime_skills: draft.enabledRuntimeSkills,
      enabled_agent_skills: draft.enabledAgentSkills,
      avatar_data_url: draft.avatarDataUrl || null,
    };
    try {
      if (draft.isNew) {
        await fetchJson(`/api/agent-management/runtimes/${encodeURIComponent(draft.runtimeId)}/agents`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...payload, agent_id: draft.agentId.trim() }),
        });
        state.selectedManagedAgentId = draft.agentId.trim();
      } else {
        await fetchJson(`/api/agent-management/agents/${encodeURIComponent(draft.agentId)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }
      state.managedAgentDraft.statusText = "Applying...";
      state.managedAgentDraft.avatarDataUrl = null;
      await loadAgentManagement();
      render();
    } catch (error) {
      state.managedAgentDraft.statusText = error.message;
      render();
    }
  }

  async function submitSteer() {
    if (!state.sessionModal?.sessionId) return;
    captureDraftsFromDom();
    const content = String(state.sessionModal.steerText || "").trim();
    if (!content) {
      state.sessionModal.statusText = "请输入 steer 内容。";
      render();
      return;
    }
    state.sessionModal.statusText = "发送中...";
    render();
    try {
      await fetchJson(`/api/sessions/${encodeURIComponent(state.sessionModal.sessionId)}/inputs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, kind: "message", sender: "operator", metadata: { source: "agent-page" } }),
      });
      state.sessionModal.steerText = "";
      state.sessionModal.statusText = "已入队。";
      await loadSessionModal();
      render();
    } catch (error) {
      state.sessionModal.statusText = error.message;
      render();
    }
  }

  function toggleSkill(input) {
    const draft = state.managedAgentDraft;
    if (!draft) return;
    const key = input.dataset.source === "runtime" ? "enabledRuntimeSkills" : "enabledAgentSkills";
    const current = new Set(draft[key] || []);
    if (input.checked) current.add(input.value);
    else current.delete(input.value);
    draft[key] = [...current].sort();
  }

  async function handleClick(event) {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const action = button.dataset.action;
    if (action === "switch-mode") {
      captureDraftsFromDom();
      state.mode = button.dataset.mode;
      if (state.mode === "agents") {
        await loadAgentManagement();
      }
      render();
      return;
    }
    if (action === "refresh") {
      await refreshAll();
      return;
    }
    if (action === "open-task-modal") {
      const firstAgent = getTaskCandidateAgents()[0];
      state.taskDraft = {
        ...defaultTaskDraft(),
        entryAgentId: firstAgent?.id || "",
      };
      state.showTaskModal = true;
      render();
      return;
    }
    if (action === "close-task-modal") {
      state.showTaskModal = false;
      render();
      return;
    }
    if (action === "create-task") {
      await createTask();
      return;
    }
    if (action === "open-session") {
      await openSessionModal(button.dataset.sessionId);
      return;
    }
    if (action === "close-session-modal") {
      state.sessionModal = null;
      render();
      return;
    }
    if (action === "submit-steer") {
      await submitSteer();
      return;
    }
    if (action === "select-managed-agent") {
      captureDraftsFromDom();
      state.selectedManagedAgentId = button.dataset.agentId;
      syncManagedDraftFromAgent(getSelectedManagedAgent());
      if (state.managedAgentTab === "sessions") {
        await loadAgentManagement();
      }
      render();
      return;
    }
    if (action === "new-agent") {
      state.selectedManagedAgentId = "__new__";
      state.managedAgentTab = "config";
      state.managedAgentDraft = emptyAgentDraft(state.selectedRuntimeId);
      render();
      return;
    }
    if (action === "set-agent-tab") {
      captureDraftsFromDom();
      state.managedAgentTab = button.dataset.tab;
      await loadAgentManagement();
      render();
      return;
    }
    if (action === "save-agent") {
      await saveManagedAgent();
      return;
    }
  }

  async function handleChange(event) {
    const target = event.target;
    if (target.id === "task-select") {
      state.selectedTaskId = target.value || null;
      await loadBoard();
      render();
      return;
    }
    if (target.id === "runtime-select") {
      captureDraftsFromDom();
      state.selectedRuntimeId = target.value || null;
      state.selectedManagedAgentId = null;
      state.managedAgentDraft = null;
      await loadAgentManagement();
      render();
      return;
    }
    if (target.dataset.action === "toggle-skill") {
      toggleSkill(target);
      return;
    }
    if (target.id === "managed-agent-avatar" && target.files?.[0]) {
      const file = target.files[0];
      const reader = new FileReader();
      reader.onload = () => {
        if (!state.managedAgentDraft) return;
        state.managedAgentDraft.avatarDataUrl = String(reader.result || "");
        state.managedAgentDraft.avatarUrl = String(reader.result || "");
        render();
      };
      reader.readAsDataURL(file);
    }
  }

  function bindEvents() {
    document.addEventListener("click", (event) => {
      handleClick(event).catch((error) => {
        console.error(error);
      });
    });
    document.addEventListener("change", (event) => {
      handleChange(event).catch((error) => {
        console.error(error);
      });
    });
    document.addEventListener("click", (event) => {
      const backdrop = event.target.closest(".modal-backdrop");
      if (!backdrop || event.target !== backdrop) return;
      if (backdrop.dataset.modal === "task") {
        state.showTaskModal = false;
      } else if (backdrop.dataset.modal === "session") {
        state.sessionModal = null;
      }
      render();
    });
  }

  async function boot() {
    bindEvents();
    await refreshAll();
    state.pollHandle = window.setInterval(() => {
      refreshAll().catch(() => {});
    }, 5000);
  }

  boot().catch((error) => {
    document.getElementById("app").innerHTML = `
      <div class="shell">
        <section class="surface"><div class="panel-body"><div class="empty-state">UI 加载失败：${escapeHtml(error.message)}</div></div></section>
      </div>
    `;
  });
})();
