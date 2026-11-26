/* NEXORA AI LABS — founder console.
   Talks to the real API: projects, pipeline state, workspace files, approvals,
   build/test output and the live preview. No mock data anywhere. */

const state = {
  health: null,
  aiStatus: null,
  projects: [],
  selectedId: null,
  dashboard: null,
  file: null,
  editing: false,
  pollTimer: null,
  nav: 'projects',
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
}

function toast(message, variant = 'info') {
  const stack = $('#toastStack');
  const node = document.createElement('div');
  node.className = `toast ${variant}`;
  node.textContent = message;
  stack.append(node);
  setTimeout(() => node.remove(), 5200);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  let payload = null;
  try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) {
    const detail = payload && payload.detail ? payload.detail : `Request failed (${response.status})`;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return payload;
}

/* ------------------------------------------------------------------ chrome */

function badge(status) {
  const map = {
    passed: 'ok', ready: 'ok', approved: 'ok', completed: 'ok', running: 'info',
    awaiting_architecture_approval: 'warn', awaiting_application_review: 'warn',
    awaiting_founder_approval: 'warn', awaiting_founder_review: 'warn',
    pending: 'warn', revision_requested: 'bad', failed: 'bad', blocked: 'bad', rejected: 'bad',
    review: 'warn', fallback: 'warn', blueprint: 'warn', ai: 'info',
  };
  return `<span class="badge ${map[status] || ''}">${esc(String(status).replace(/_/g, ' '))}</span>`;
}

function setNav(nav) {
  state.nav = nav;
  $$('.side-nav button').forEach((button) => button.classList.toggle('active', button.dataset.nav === nav));
  $$('.view').forEach((view) => { view.hidden = view.id !== `view-${nav}`; });
  $('#viewTitle').textContent = {
    projects: 'Projects', workspace: 'Development workspace',
    approvals: 'Founder approvals', agents: 'AI employees',
  }[nav] || 'Projects';
  if (nav === 'approvals') loadApprovals();
}

/* ------------------------------------------------------------------ health */

async function loadHealth() {
  try {
    const [health, ai] = await Promise.all([api('/api/health'), api('/api/ai/status')]);
    state.health = health;
    state.aiStatus = ai;
    const connected = ai.state === 'online';
    $('#modelState').textContent = connected ? 'online' : (ai.state === 'model_missing' ? 'model missing' : 'offline');
    $('#modelState').style.color = connected ? 'var(--green)' : 'var(--amber)';
    $('#modelName').textContent = ai.model || health.model;
    $('#sandboxState').textContent = health.node || 'unknown';
    const pill = $('#pipelinePill');
    pill.textContent = connected ? '● Local AI online' : '● Blueprint mode (AI offline)';
    pill.className = `pill ${connected ? '' : 'warn'}`;
    pill.title = ai.detail || '';
  } catch (error) {
    toast(`Health check failed: ${error.message}`, 'error');
  }
}

/* ------------------------------------------------------------------ projects */

function projectCard(project) {
  const active = project.id === state.selectedId ? ' active' : '';
  return `<article class="list-item${active}" data-project="${project.id}">
    <div class="row-between">
      <h3>${esc(project.name)}</h3>
      ${badge(project.status)}
    </div>
    <p>${esc((project.description || 'No requirement captured').slice(0, 150))}</p>
    <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">
      ${project.app_type ? `<span class="badge gold">${esc(project.app_type)}</span>` : ''}
      ${project.slug ? `<span class="badge">${esc(project.slug)}</span>` : ''}
    </div>
  </article>`;
}

async function loadProjects() {
  try {
    state.projects = await api('/api/projects');
    const list = $('#projectList');
    if (!state.projects.length) {
      list.innerHTML = '<p class="muted small">No projects yet. Create your first one on the left.</p>';
      return;
    }
    list.innerHTML = state.projects.map(projectCard).join('');
    $$('#projectList [data-project]').forEach((node) => {
      node.addEventListener('click', () => openWorkspace(Number(node.dataset.project)));
    });
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function createProject(event) {
  event.preventDefault();
  const button = $('#createBtn');
  const payload = {
    name: $('#projectName').value.trim(),
    description: $('#projectDescription').value.trim(),
    business_line: $('#projectBusiness').value,
    blueprint: $('#projectBlueprint').value || null,
    autostart: $('#projectAutostart').checked,
  };
  try {
    button.disabled = true;
    button.textContent = 'Creating…';
    const project = await api('/api/projects', { method: 'POST', body: JSON.stringify(payload) });
    $('#projectForm').reset();
    $('#projectAutostart').checked = true;
    toast(`Project #${project.id} created${payload.autostart ? ' — AI pipeline started' : ''}`, 'success');
    await loadProjects();
    openWorkspace(project.id);
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    button.disabled = false;
    button.textContent = 'Create project & start AI';
  }
}

/* ------------------------------------------------------------------ workspace */

async function openWorkspace(projectId) {
  state.selectedId = projectId;
  state.file = null;
  state.editing = false;
  setNav('workspace');
  await loadProjects();
  await loadWorkspace();
  startPolling();
}

function stopPolling() {
  if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
}

function startPolling() {
  stopPolling();
  state.pollTimer = setInterval(async () => {
    if (state.nav !== 'workspace' || !state.selectedId) return;
    const status = state.dashboard && state.dashboard.workspace ? state.dashboard.workspace.status : null;
    if (status === 'running') await loadWorkspace(true);
  }, 4000);
}

function pipelineStrip(pipeline, dashboard) {
  if (!pipeline) return '';
  const workspace = dashboard.workspace || {};
  const completedPhases = new Set((dashboard.events || [])
    .filter((event) => ['agent', 'file', 'verify', 'build', 'test', 'scan', 'seed', 'preview'].includes(event.kind))
    .map((event) => event.phase));
  return `<div class="pipeline">${pipeline.map((step) => {
    const done = completedPhases.has(step.phase);
    const active = workspace.current_phase === step.phase;
    const failed = ['failed', 'blocked'].includes(workspace.status) && active;
    return `<div class="pipeline-step ${done ? 'done' : ''} ${active ? 'active' : ''} ${failed ? 'failed' : ''}"
      title="${esc(step.label)} — ${esc(step.agent_id)}">
      <span class="step-label">${done ? '✓ ' : ''}${esc(step.label)}</span>
      <span class="step-agent">${esc(step.agent_id)}</span>
    </div>`;
  }).join('')}</div>`;
}

function renderTree(nodes, depth = 0) {
  return nodes.map((node) => {
    if (node.type === 'dir') {
      if (!node.children || !node.children.length) return '';
      return `<details ${depth < 1 ? 'open' : ''}>
        <summary>${esc(node.name)}</summary>
        ${renderTree(node.children, depth + 1)}
      </details>`;
    }
    const aiMarker = node.ai ? '<span class="ai-dot" title="AI-authored">●</span>' : '';
    return `<button class="file" data-path="${esc(node.path)}">${esc(node.name)} ${aiMarker}</button>`;
  }).join('');
}

function mergeTree(tree, indexed) {
  const aiPaths = new Map((indexed || []).map((row) => [row.path, row.is_ai_generated]));
  const walk = (nodes) => nodes.map((node) => {
    if (node.type === 'dir') return { ...node, children: walk(node.children || []) };
    return { ...node, ai: Boolean(aiPaths.get(node.path)) };
  });
  return walk(tree);
}

async function loadWorkspace(silent = false) {
  if (!state.selectedId) return;
  const root = $('#workspaceRoot');
  try {
    const [dashboard, tree] = await Promise.all([
      api(`/api/projects/${state.selectedId}/dashboard`),
      api(`/api/projects/${state.selectedId}/files`).catch(() => ({ tree: { children: [] }, files: [] })),
    ]);
    state.dashboard = dashboard;
    state.tree = tree;
    if (!dashboard.workspace) {
      root.innerHTML = `<div class="empty-state">
        <h2>${esc(dashboard.project.name)}</h2>
        <p>${esc(dashboard.message || 'No pipeline run yet.')}</p>
        <button class="btn" id="startPipeline">Start AI pipeline</button>
      </div>`;
      $('#startPipeline').addEventListener('click', startPipeline);
      return;
    }
    root.innerHTML = renderWorkspace(dashboard, tree);
    wireWorkspace();
    if (!silent) await refreshPendingApprovals();
  } catch (error) {
    if (!silent) toast(error.message, 'error');
  }
}

function renderWorkspace(dashboard, treeData) {
  const ws = dashboard.workspace;
  const project = dashboard.project;
  const fileCount = ws.file_count || (treeData.files || []).length;
  const aiFiles = (dashboard.files || []).filter((file) => file.is_ai_generated).length;
  const events = dashboard.events || [];
  const approvals = dashboard.approvals || [];
  const realFiles = treeData.tree ? mergeTree(treeData.tree.children || [], dashboard.files) : [];
  const buildRuns = dashboard.builds || [];
  const latestTests = buildRuns.find((run) => run.kind === 'test');
  const previewLive = ws.preview_status === 'running';

  return `
    <div class="ws-head">
      <div>
        <p class="eyebrow">Project #${project.id} · ${esc(ws.slug)}</p>
        <h1>${esc(project.name)}</h1>
        <div class="ws-meta">
          ${badge(ws.status)}
          <span class="badge gold">${esc(project.app_type || 'application')}</span>
          <span class="badge">${esc(ws.engine)}</span>
          ${ws.model ? `<span class="badge info">${esc(ws.model)}</span>` : ''}
        </div>
      </div>
      <div class="topbar-actions">
        <button class="btn secondary small" id="wsGenerate">Re-run analysis</button>
        <button class="btn small" id="wsBuild">${ws.progress >= 100 ? 'Rebuild application' : 'Approve & generate code'}</button>
        ${previewLive
          ? `<a class="btn small ghost" href="${esc(ws.preview_url)}" target="_blank" rel="noopener">Open live app ↗</a>
             <button class="btn small danger" id="wsStopPreview">Stop</button>`
          : `<button class="btn small ghost" id="wsStartPreview" ${ws.build_status === 'passed' ? '' : 'disabled'}>Start preview</button>`}
      </div>
    </div>

    <div class="progress-wrap">
      <div class="progress-top">
        <span>${esc(ws.phase_label || ws.current_phase || 'idle')} · currently ${esc(ws.current_agent_name || '—')}</span>
        <span>${ws.progress}%</span>
      </div>
      <div class="progress-track"><div class="progress-fill" style="width:${ws.progress}%"></div></div>
    </div>

    ${pipelineStrip(dashboard.pipeline, dashboard)}

    <div class="stat-row">
      <div class="stat"><div class="label">Files generated</div><div class="value">${fileCount}</div></div>
      <div class="stat"><div class="label">AI-authored edits</div><div class="value">${aiFiles}</div></div>
      <div class="stat"><div class="label">Build</div><div class="value small-value">${badge(ws.build_status)}</div></div>
      <div class="stat"><div class="label">Tests</div><div class="value small-value">${badge(ws.test_status)}</div></div>
      <div class="stat"><div class="label">Security</div><div class="value small-value">${badge(ws.security_status)}</div></div>
      <div class="stat"><div class="label">Preview</div><div class="value small-value">${badge(ws.preview_status)}</div></div>
      <div class="stat"><div class="label">Workspace size</div><div class="value">${ws.size_kb} KB</div></div>
    </div>

    <div class="ws-grid">
      <div style="display:grid;gap:14px">
        <div class="panel">
          <div class="panel-head"><h3>Files</h3><span class="badge">${fileCount} on disk</span></div>
          <div class="tree" id="fileTree">${renderTree(realFiles) || '<p class="muted small" style="padding:10px">No files yet.</p>'}</div>
        </div>
        <div class="panel">
          <div class="panel-head"><h3>Approval checkpoints</h3></div>
          <div style="padding:12px 14px;display:grid;gap:9px">
            ${approvals.length ? approvals.map((approval) => `
              <div class="row-between" style="gap:8px">
                <span class="small">${esc(approval.title)}</span>${badge(approval.status)}
              </div>`).join('') : '<p class="muted small">No checkpoints yet.</p>'}
          </div>
        </div>
      </div>

      <div style="display:grid;gap:14px;min-width:0">
        <div class="panel" id="sourcePanel">
          <div class="panel-head">
            <h3>Source viewer</h3>
            <span class="small muted" id="sourceMeta">Select a file</span>
          </div>
          <div id="sourceBody"><p class="muted small" style="padding:14px">Choose a file from the explorer to read its real source.</p></div>
        </div>

        <div class="panel">
          <div class="panel-head"><h3>Live development log</h3><span class="badge">${events.length} events</span></div>
          <div class="log" id="devLog">
            ${events.length ? [...events].reverse().map((event) => `
              <div class="entry ${esc(event.kind)}">
                <span class="time">${esc((event.created_at || '').slice(11, 19))}</span>
                <span class="phase">${esc(event.phase)}</span>
                <span class="agent">${esc(event.agent_id)}</span>
                <span class="msg">${esc(event.message)}</span>
              </div>`).join('') : '<p class="muted small">No events yet.</p>'}
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h3>Build &amp; test output</h3>
            <span class="badge ${latestTests ? (latestTests.status === 'passed' ? 'ok' : 'bad') : ''}">
              ${latestTests ? esc(latestTests.status) : 'not run'}
            </span>
          </div>
          <pre class="code-block wrap" style="max-height:300px">${esc(
            buildRuns.length
              ? buildRuns.slice(0, 4).map((run) => `$ ${run.command}\n[${run.status}] exit=${run.exit_code} · ${run.duration_ms}ms\n${(run.output || '').slice(-1400)}`).join('\n\n────────\n\n')
              : 'No build has run yet.'
          )}</pre>
        </div>
      </div>
    </div>`;
}

function wireWorkspace() {
  $('#wsGenerate')?.addEventListener('click', async () => {
    try {
      await api(`/api/projects/${state.selectedId}/generate`, { method: 'POST' });
      toast('AI analysis started', 'success');
      await loadWorkspace();
    } catch (error) { toast(error.message, 'error'); }
  });

  $('#wsBuild')?.addEventListener('click', startPipeline);
  $('#wsStartPreview')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = 'Starting…';
    try {
      await api(`/api/projects/${state.selectedId}/preview/start`, { method: 'POST' });
      toast('Preview server started', 'success');
    } catch (error) {
      toast(error.message, 'error');
      button.disabled = false;
      button.textContent = 'Start preview';
    }
    await loadWorkspace();
  });
  $('#wsStopPreview')?.addEventListener('click', async () => {
    try {
      await api(`/api/projects/${state.selectedId}/preview/stop`, { method: 'POST' });
      toast('Preview stopped');
    } catch (error) { toast(error.message, 'error'); }
    await loadWorkspace();
  });

  $$('#fileTree [data-path]').forEach((button) => {
    button.addEventListener('click', () => openFile(button.dataset.path));
  });
}

async function startPipeline() {
  try {
    const pendingGate = (state.dashboard?.approvals || []).find(
      (approval) => ['architecture', 'design', 'development_plan'].includes(approval.kind) && approval.status !== 'approved',
    );
    if (pendingGate) {
      toast(`Approve "${pendingGate.title}" before code generation.`, 'error');
      setNav('approvals');
      await loadApprovals();
      return;
    }
    await api(`/api/projects/${state.selectedId}/build`, { method: 'POST' });
    toast('Implementation started — watch the log for each AI employee.', 'success');
    await loadWorkspace();
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function openFile(path) {
  try {
    const file = await api(`/api/projects/${state.selectedId}/file?path=${encodeURIComponent(path)}`);
    state.file = file;
    state.editing = false;
    renderSource();
    $$('#fileTree .file').forEach((node) => node.classList.toggle('active', node.dataset.path === path));
  } catch (error) {
    toast(error.message, 'error');
  }
}

function renderSource() {
  const body = $('#sourceBody');
  const meta = $('#sourceMeta');
  if (!state.file) {
    body.innerHTML = '<p class="muted small" style="padding:14px">Choose a file from the explorer to read its real source.</p>';
    meta.textContent = 'Select a file';
    return;
  }
  meta.innerHTML = `${state.file.is_ai_generated ? '<span class="badge info">AI-authored</span> ' : ''}
    <span class="badge">${state.file.lines} lines</span>
    <span class="badge">${state.file.agent_id || 'blueprint'}</span>`;
  if (state.editing) {
    body.innerHTML = `
      <div class="code-head">
        <span class="code-path">${esc(state.file.path)}</span>
        <span style="display:flex;gap:8px">
          <button class="btn small" id="saveFile">Save &amp; index</button>
          <button class="btn small ghost" id="cancelEdit">Cancel</button>
        </span>
      </div>
      <textarea class="code-editor" id="editor" spellcheck="false">${esc(state.file.content)}</textarea>`;
    $('#saveFile').addEventListener('click', saveFile);
    $('#cancelEdit').addEventListener('click', () => { state.editing = false; renderSource(); });
    return;
  }
  body.innerHTML = `
    <div class="code-head">
      <span class="code-path">${esc(state.file.path)}</span>
      <button class="btn small ghost" id="editFile">Edit</button>
    </div>
    <pre class="code-block">${esc(state.file.content)}</pre>`;
  $('#editFile').addEventListener('click', () => { state.editing = true; renderSource(); });
}

async function saveFile() {
  try {
    const content = $('#editor').value;
    const result = await api(`/api/projects/${state.selectedId}/file`, {
      method: 'PUT', body: JSON.stringify({ path: state.file.path, content }),
    });
    toast(`Saved ${result.path} (${result.lines} lines)`, 'success');
    state.file.content = content;
    state.file.lines = result.lines;
    state.editing = false;
    renderSource();
    await loadWorkspace(true);
  } catch (error) {
    toast(error.message, 'error');
  }
}

/* ------------------------------------------------------------------ approvals */

async function refreshPendingApprovals() {
  const approvals = state.dashboard?.approvals || [];
  const pending = approvals.filter((approval) => approval.status === 'pending').length;
  const badgeEl = $('#pendingApprovals');
  badgeEl.textContent = String(pending);
  badgeEl.hidden = pending === 0;
}

async function loadApprovals() {
  const root = $('#approvalRoot');
  if (!state.projects.length) { await loadProjects(); }
  const projectId = state.selectedId || (state.projects[0] && state.projects[0].id);
  if (!projectId) {
    root.innerHTML = '<div class="empty-state"><h2>No projects</h2><p>Create a project to see approval checkpoints.</p></div>';
    return;
  }
  state.selectedId = state.selectedId || projectId;
  root.innerHTML = '<p class="muted small">Loading approvals…</p>';
  try {
    const [approvals, dashboard] = await Promise.all([
      api(`/api/projects/${projectId}/approvals`),
      api(`/api/projects/${projectId}/dashboard`),
    ]);
    state.dashboard = dashboard;
    const pending = approvals.filter((approval) => approval.status === 'pending');
    $('#pendingApprovals').textContent = String(pending.length);
    $('#pendingApprovals').hidden = pending.length === 0;
    const project = dashboard.project;
    root.innerHTML = `
      <div class="card" style="margin-bottom:16px">
        <div class="row-between">
          <div>
            <p class="eyebrow">Approval queue</p>
            <h2>${esc(project.name)}</h2>
            <p class="muted small" style="margin:0">${approvals.length} checkpoint(s) · ${pending.length} awaiting your decision</p>
          </div>
          <button class="btn ghost small" id="approvalRefresh">Refresh</button>
        </div>
      </div>
      ${approvals.length ? approvals.map((approval) => `
        <article class="approval-card ${esc(approval.status)}">
          <div class="row-between">
            <h3>${esc(approval.title)}</h3>
            <div>${badge(approval.status)}</div>
          </div>
          <div class="approval-summary">${esc((approval.summary || '').slice(0, 1600))}</div>
          ${approval.decision_note ? `<div class="approval-note">Founder note: ${esc(approval.decision_note)}</div>` : ''}
          ${approval.status === 'pending' ? `
            <div class="approval-actions">
              <button class="btn small" data-approve="${approval.id}">Approve</button>
              <button class="btn small secondary" data-revise="${approval.id}">Request revision</button>
              <button class="btn small danger" data-reject="${approval.id}">Reject</button>
            </div>` : ''}
        </article>`).join('') : '<div class="empty-state"><h2>No checkpoints yet</h2><p>Run the AI pipeline to create approval gates.</p></div>'}`;

    $('#approvalRefresh').addEventListener('click', loadApprovals);
    $$('[data-approve]').forEach((button) => button.addEventListener('click', async () => {
      try {
        await api(`/api/approvals/${button.dataset.approve}/decide`, {
          method: 'POST', body: JSON.stringify({ decision: 'approve', note: 'Approved by founder.' }),
        });
        toast('Checkpoint approved', 'success');
        await loadApprovals();
      } catch (error) { toast(error.message, 'error'); }
    }));
    $$('[data-reject]').forEach((button) => button.addEventListener('click', async () => {
      try {
        await api(`/api/approvals/${button.dataset.reject}/decide`, {
          method: 'POST', body: JSON.stringify({ decision: 'reject', note: 'Rejected by founder.' }),
        });
        toast('Checkpoint rejected');
        await loadApprovals();
      } catch (error) { toast(error.message, 'error'); }
    }));
    $$('[data-revise]').forEach((button) => button.addEventListener('click', () => openRevisionModal(button.dataset.revise)));
  } catch (error) {
    root.innerHTML = `<div class="empty-state"><h2>Approvals unavailable</h2><p>${esc(error.message)}</p></div>`;
  }
}

function openRevisionModal(approvalId) {
  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop';
  backdrop.innerHTML = `<div class="modal" role="dialog" aria-modal="true">
    <h3>Request a revision</h3>
    <p class="muted small">Your note is added to the project requirement and the AI pipeline re-runs from analysis. Be specific about what must change.</p>
    <div class="field">
      <label for="revisionNote">What should change?</label>
      <textarea id="revisionNote" rows="5" placeholder="e.g. Add product reviews with a star rating and a moderation queue for staff."></textarea>
    </div>
    <div class="approval-actions">
      <button class="btn" id="revisionSubmit">Request revision</button>
      <button class="btn ghost" id="revisionCancel">Cancel</button>
    </div>
  </div>`;
  document.body.append(backdrop);
  const close = () => backdrop.remove();
  backdrop.addEventListener('click', (event) => { if (event.target === backdrop) close(); });
  $('#revisionCancel').addEventListener('click', close);
  $('#revisionSubmit').addEventListener('click', async () => {
    const note = $('#revisionNote').value.trim();
    if (note.length < 5) { toast('Describe the revision first.', 'error'); return; }
    try {
      await api(`/api/projects/${state.selectedId}/revision`, {
        method: 'POST', body: JSON.stringify({ decision: 'revision', note }),
      });
      close();
      toast('Revision requested — the AI pipeline is re-running.', 'success');
      await loadApprovals();
    } catch (error) { toast(error.message, 'error'); }
  });
}

/* ------------------------------------------------------------------ agents */

async function loadAgents() {
  try {
    const agents = await api('/api/agents');
    $('#agentGrid').innerHTML = agents.map((agent) => `
      <div class="agent-card">
        <strong>${esc(agent.role)}</strong>
        <span class="dept">${esc(agent.department)}</span>
        <p>${esc(agent.mission)}</p>
      </div>`).join('');
  } catch (error) { toast(error.message, 'error'); }
}

/* ------------------------------------------------------------------ boot */

function wireChrome() {
  $$('.side-nav button').forEach((button) => button.addEventListener('click', () => {
    setNav(button.dataset.nav);
    if (button.dataset.nav === 'workspace' && !state.selectedId && state.projects.length) {
      openWorkspace(state.projects[0].id);
    } else if (button.dataset.nav === 'workspace' && state.selectedId) {
      loadWorkspace();
    }
  }));
  $('#projectForm').addEventListener('submit', createProject);
  $('#loadProjects').addEventListener('click', loadProjects);
  $('#refreshBtn').addEventListener('click', async () => {
    await loadHealth();
    await loadProjects();
    if (state.nav === 'workspace') await loadWorkspace();
    if (state.nav === 'approvals') await loadApprovals();
    toast('Refreshed');
  });
  $('#chatForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = $('#chatBtn');
    const output = $('#chatOutput');
    const message = $('#chatInput').value.trim();
    if (message.length < 2) return;
    button.disabled = true;
    output.hidden = false;
    output.textContent = 'Consulting the local model…';
    try {
      const result = await api('/api/ai/chat', { method: 'POST', body: JSON.stringify({ message }) });
      output.textContent = result.reply;
    } catch (error) {
      output.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
}

async function boot() {
  wireChrome();
  await loadHealth();
  await loadProjects();
  await loadAgents();
  if (state.projects.length) {
    state.selectedId = state.projects[0].id;
    await loadApprovals();
    await loadProjects();
  }
  setNav('projects');
}

boot().catch((error) => toast(`Boot failed: ${error.message}`, 'error'));
