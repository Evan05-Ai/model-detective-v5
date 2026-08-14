/* ============================================================
   Model Detective — Web Frontend v2.7
   Fixed: Tab switching works correctly now.
   ============================================================ */

(function () {
  'use strict';

  // ============ State ============
  const State = {
    baseUrl: '',
    apiKey: '',
    probeData: null,
    selectedModels: new Set(),
    manualModels: new Set(),
    mode: 'standard',
    protoFilter: 'all',
    completeHandled: false,
    currentRelayUrl: '',
    // Evaluation state
    evalBaseUrl: '',
    evalApiKey: '',
    evalProbeData: null,
    evalSelectedModels: new Set(),
    evalManualModels: new Set(),
    evalModels: [],
    evalDimensions: ['basic_language', 'technical', 'advanced_cognition', 'practical', 'boundary'],
    evalDifficulty: 'quick',
    evalProtoFilter: 'all',
    evalCompleteHandled: false,
  };

  // ============ LocalStorage Helper ============
  const Store = {
    get: (key, def) => { try { return JSON.parse(localStorage.getItem(key)) || def; } catch { return def; } },
    set: (key, val) => { try { localStorage.setItem(key, JSON.stringify(val)); } catch {} },
    addUrl: (url) => {
      if (!url) return;
      const urls = Store.get('md_urls', []).filter(u => u !== url);
      urls.unshift(url);
      Store.set('md_urls', urls.slice(0, 30));
    },
    getUrls: () => Store.get('md_urls', []),
    addReport: (report) => {
      const reports = Store.get('md_reports', []);
      const entry = {
        id: report.job_id || Date.now().toString(36),
        time: Date.now(),
        model: report.model,
        base_url: report.base_url || State.currentRelayUrl,
        total_score: report.total_score,
        verdict: report.verdict,
        verdict_cn: report.verdict_cn,
        protocol: report.protocol,
        mode: report.mode,
        duration_seconds: report.duration_seconds,
        total_tokens: report.total_tokens,
        backend_source_cn: report.backend_source_cn,
        results: report.results,
        authenticity_score: report.authenticity_score,
        capability_score: report.capability_score,
        compliance_score: report.compliance_score,
        estimated_cost_usd: report.estimated_cost_usd,
        has_critical: report.has_critical,
        degraded: report.degraded,
        degrade_reason: report.degrade_reason,
      };
      reports.unshift(entry);
      Store.set('md_reports', reports.slice(0, 100));
      Store.addUrl(entry.base_url);
    },
    getReports: () => Store.get('md_reports', []),
    deleteReport: (id) => {
      const reports = Store.get('md_reports', []).filter(r => r.id !== id);
      Store.set('md_reports', reports);
    },
    clearReports: () => { Store.set('md_reports', []); Store.set('md_urls', []); },
  };

  // ============ Utils ============
  const $ = (id) => document.getElementById(id);
const show = (el) => {
  if (el) {
    el.hidden = false;
    el.classList.add('revealed');
  }
};
const hide = (el) => {
  if (el) {
    el.hidden = true;
    el.classList.remove('revealed');
  }
};

  function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
  }

  function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }

  function cssEscape(s) {
    if (typeof CSS !== 'undefined' && CSS.escape) return CSS.escape(s);
    return String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  }

  // ============ Hero Tab Switching ============
  // 模型测评已迁移至 /evaluation 独立页面，这里仅处理 API 检测页内逻辑

  // v2.8: 恢复检测页到初始状态（配置步骤可见，其他隐藏）
  function resetToDetectionHome() {
    show($('step-config'));
    hide($('step-models'));
    hide($('step-mode'));
    hide($('step-start'));
    const c = $('results-container');
    if (c) c.innerHTML = '';
    hide($('step-results'));
  }

  window.switchTab = function(tab) {
    if (tab === 'evaluation') {
      window.location.href = '/evaluation';
      return;
    }
    // detection tab
    const tabDetection = $('tab-detection');
    const sectionDetection = $('section-detection');
    const sectionEvaluation = $('section-evaluation');
    if (tabDetection) tabDetection.classList.add('active');
    if (sectionDetection) {
      sectionDetection.hidden = false;
      sectionDetection.classList.add('revealed');
    }
    if (sectionEvaluation) {
      sectionEvaluation.hidden = true;
      sectionEvaluation.classList.remove('revealed');
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  window.scrollToConfig = function() {
    // 确保在 API 检测页面，并恢复配置步骤显示
    resetToDetectionHome();
    window.switchTab('detection');
    // 等待切换完成后再滚动
    setTimeout(() => {
      const configSection = $('step-config');
      if (configSection) {
        configSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
        const baseUrlInput = $('base_url');
        if (baseUrlInput) {
          setTimeout(() => baseUrlInput.focus(), 600);
        }
      }
    }, 150);
  };

  function initHeroTabs() {
    const tabDetection = $('tab-detection');
    if (tabDetection) {
      tabDetection.addEventListener('click', () => {
        // v2.8: 点击 API 检测 tab 时恢复配置步骤
        resetToDetectionHome();
        window.switchTab('detection');
      });
    }
    // 模型测评按钮现在是 <a href="/evaluation">链接，无需JS事件
    // 全局函数供HTML内联事件调用
    window.switchToEvaluation = function() {
      window.location.href = '/evaluation';
    };
    window.goToHome = function() {
      // v2.8: 返回首页时恢复配置步骤
      resetToDetectionHome();
      window.switchTab('detection');
    };
  }

  // ============ Provider Presets ============
  const PROVIDERS = [
    { name: 'Anthropic Official', url: 'https://api.anthropic.com/v1' },
    { name: 'OpenAI Official', url: 'https://api.openai.com/v1' },
    { name: 'Gemini Official', url: 'https://generativelanguage.googleapis.com/v1beta' },
    { name: 'OpenRouter', url: 'https://openrouter.ai/api/v1' },
    { name: 'DeepSeek Official', url: 'https://api.deepseek.com/v1' },
    { name: 'Moonshot (Kimi)', url: 'https://api.moonshot.cn/v1' },
    { name: 'Zhipu (GLM)', url: 'https://open.bigmodel.cn/api/paas/v4' },
    { name: 'Together AI', url: 'https://api.together.xyz/v1' },
    { name: 'Groq', url: 'https://api.groq.com/openai/v1' },
    { name: 'Fireworks AI', url: 'https://api.fireworks.ai/inference/v1' },
    { name: 'Mistral AI', url: 'https://api.mistral.ai/v1' },
    { name: 'Cerebras', url: 'https://api.cerebras.ai/v1' },
    { name: 'SambaNova', url: 'https://api.sambanova.ai/v1' },
    { name: 'Novita AI', url: 'https://api.novita.ai/v3/openai' },
    { name: 'SiliconFlow', url: 'https://api.siliconflow.cn/v1' },
  ];

  // ============ Init: Provider Dropdown ============
  function initProviders() {
    const btn = $('provider-btn');
    const dd = $('provider-dropdown');
    const list = $('provider-list');
    const search = $('provider-search');

    function render(q) {
      const f = PROVIDERS.filter(p =>
        p.name.toLowerCase().includes(q) || p.url.toLowerCase().includes(q)
      );
      list.innerHTML = f.map(p =>
        `<div class="dropdown-item" data-url="${escapeHtml(p.url)}">
          <span class="di-name">${escapeHtml(p.name)}</span>
          <span class="di-url">${escapeHtml(p.url)}</span>
        </div>`
      ).join('');
      list.querySelectorAll('.dropdown-item').forEach(item => {
        item.addEventListener('click', () => {
          $('base_url').value = item.dataset.url;
          hide(dd);
          onInputChange();
        });
      });
    }

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (dd.hidden) { show(dd); render(''); search.focus(); }
      else hide(dd);
    });

    search.addEventListener('input', () => render(search.value.toLowerCase().trim()));

    document.addEventListener('click', (e) => {
      if (!dd.contains(e.target) && e.target !== btn) hide(dd);
    });
  }

  // ============ Init: Eval Provider Dropdown ============
  function initEvalProviders() {
    const btn = $('eval-provider-btn');
    const dd = $('eval-provider-dropdown');
    const list = $('eval-provider-list');
    const search = $('eval-provider-search');

    function render(q) {
      const f = PROVIDERS.filter(p =>
        p.name.toLowerCase().includes(q) || p.url.toLowerCase().includes(q)
      );
      list.innerHTML = f.map(p =>
        `<div class="dropdown-item" data-url="${escapeHtml(p.url)}">
          <span class="di-name">${escapeHtml(p.name)}</span>
          <span class="di-url">${escapeHtml(p.url)}</span>
        </div>`
      ).join('');
      list.querySelectorAll('.dropdown-item').forEach(item => {
        item.addEventListener('click', () => {
          $('eval-base_url').value = item.dataset.url;
          hide(dd);
          onEvalInputChange();
        });
      });
    }

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (dd.hidden) { show(dd); render(''); search.focus(); }
      else hide(dd);
    });

    search.addEventListener('input', () => render(search.value.toLowerCase().trim()));

    document.addEventListener('click', (e) => {
      if (!dd.contains(e.target) && e.target !== btn) hide(dd);
    });
  }

  // ============ Init: Key Toggle ============
  function initKeyToggle() {
    const btn = $('toggle-key');
    const input = $('api_key');
    const eyeOn = btn.querySelector('.icon-eye');
    const eyeOff = btn.querySelector('.icon-eye-off');

    btn.addEventListener('click', () => {
      if (input.type === 'password') {
        input.type = 'text';
        eyeOn.style.display = 'none';
        eyeOff.style.display = '';
      } else {
        input.type = 'password';
        eyeOn.style.display = '';
        eyeOff.style.display = 'none';
      }
    });
  }

  // ============ Init: Eval Key Toggle ============
  function initEvalKeyToggle() {
    const btn = $('eval-toggle-key');
    const input = $('eval-api_key');
    const eyeOn = btn.querySelector('.icon-eye');
    const eyeOff = btn.querySelector('.icon-eye-off');

    btn.addEventListener('click', () => {
      if (input.type === 'password') {
        input.type = 'text';
        eyeOn.style.display = 'none';
        eyeOff.style.display = '';
      } else {
        input.type = 'password';
        eyeOn.style.display = '';
        eyeOff.style.display = 'none';
      }
    });
  }

  // ============ Input Change → Probe ============
  const debouncedProbe = debounce(runProbe, 700);

  function onInputChange() {
    State.baseUrl = $('base_url').value.trim();
    State.apiKey = $('api_key').value.trim();

    const ready = State.baseUrl.startsWith('http') && State.apiKey.length >= 8;
    if (ready) {
      debouncedProbe();
} else {
hide($('probe-pill'));
hide($('detection-workflow'));
}
  }

  // ============ Eval Input Change ============
  const debouncedEvalProbe = debounce(runEvalProbe, 700);

  function onEvalInputChange() {
    State.evalBaseUrl = $('eval-base_url').value.trim();
    State.evalApiKey = $('eval-api_key').value.trim();

    const ready = State.evalBaseUrl.startsWith('http') && State.evalApiKey.length >= 8;
    if (ready) {
      show($('eval-step-config'));
      debouncedEvalProbe();
    } else {
      hide($('eval-step-models'));
      hide($('eval-step-dimensions'));
      hide($('eval-step-launch'));
    }
  }

  // ============ Probe ============
  async function runProbe() {
    const pill = $('probe-pill');
    show(pill);
    pill.className = 'probe-status info';
    pill.innerHTML = '<span class="spinner"></span> 正在探测可用模型...';

    try {
      const resp = await fetch('/api/probe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ base_url: State.baseUrl, api_key: State.apiKey }),
      });
      const data = await resp.json();
      renderProbeResult(data);
    } catch (e) {
      pill.className = 'probe-status warn';
      pill.textContent = '探测失败: ' + e.message + ' — 你可以手动输入模型名。';
      show($('step-models'));
      renderModels([], null);
    }
  }

  async function runEvalProbe() {
    const pill = $('eval-probe-pill');
    if (!pill) return;
    show(pill);
    pill.className = 'probe-status info';
    pill.innerHTML = '<span class="spinner"></span> 正在探测可用模型...';

    try {
      const resp = await fetch('/api/probe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ base_url: State.evalBaseUrl, api_key: State.evalApiKey }),
      });
      const data = await resp.json();
      renderEvalProbeResult(data);
    } catch (e) {
      pill.className = 'probe-status warn';
      pill.textContent = '探测失败: ' + e.message + ' — 你可以手动输入模型名。';
      show($('eval-step-models'));
      renderEvalModels([], null);
    }
  }

  function renderEvalProbeResult(data) {
    const pill = $('eval-probe-pill');

    if (!data.ok && data.auth_ok === false) {
      pill.className = 'probe-status err';
      pill.textContent = '认证失败 — 请检查 API Key';
      return;
    }

    if (!data.models_endpoint_supported) {
      pill.className = 'probe-status warn';
      pill.textContent = data.error || '未找到 /v1/models 端点 — 你可以手动输入模型名。';
      show($('eval-step-models'));
      renderEvalModels([], null);
      return;
    }

    State.evalProbeData = data;
    // 使用后端返回的有效 base_url（可能已补 /v1）
    if (data.effective_base_url) {
      State.evalBaseUrl = data.effective_base_url;
      // 同时更新输入框的值，让用户知道实际使用的 URL
      $('eval-base_url').value = data.effective_base_url;
    }
    const a = data.by_protocol?.anthropic?.length || 0;
    const o = data.by_protocol?.openai?.length || 0;
    const g = data.by_protocol?.gemini?.length || 0;
    pill.className = 'probe-status ok';
    pill.innerHTML = `发现 <b>${data.raw_count}</b> 个模型 (Anthropic ${a} · OpenAI ${o} · Gemini ${g})`;

    show($('eval-step-models'));
    renderEvalModels(data.all_models || [], data.by_protocol);
    show($('eval-step-dimensions'));
  }

  function renderEvalModels(allModels, byProto) {
    const grid = $('eval-model-grid');
    if (!grid) return;

    const protoMap = {};
    if (byProto) {
      for (const [p, ms] of Object.entries(byProto)) {
        for (const m of ms) protoMap[m] = p;
      }
    }
    for (const m of State.evalManualModels) {
      if (!protoMap[m]) protoMap[m] = guessEvalProto(m);
    }

    const allSet = new Set([...allModels, ...State.evalManualModels]);
    const filtered = State.evalProtoFilter === 'all'
      ? [...allSet]
      : [...allSet].filter(m => protoMap[m] === State.evalProtoFilter);

    if (filtered.length === 0) {
      grid.innerHTML = '<div class="model-empty">没有匹配的模型，可手动添加。</div>';
      return;
    }

    grid.innerHTML = filtered.map(m => {
      const p = protoMap[m] || 'openai';
      const sel = State.evalSelectedModels.has(m) ? ' selected' : '';
      return `<div class="model-card${sel}" data-eval-model="${escapeHtml(m)}" tabindex="0" role="button" aria-pressed="${State.evalSelectedModels.has(m)}">
        <div class="model-card-name">${escapeHtml(m)}</div>
        <div class="model-card-badge"><span class="dot dot-${p}"></span>${p}</div>
      </div>`;
    }).join('');

    grid.querySelectorAll('.model-card').forEach(card => {
      const toggle = () => {
        const m = card.dataset.evalModel;
        if (State.evalSelectedModels.has(m)) {
          State.evalSelectedModels.delete(m);
          card.classList.remove('selected');
          card.setAttribute('aria-pressed', 'false');
        } else {
          State.evalSelectedModels.add(m);
          card.classList.add('selected');
          card.setAttribute('aria-pressed', 'true');
        }
        updateEvalSummary();
      };
      card.addEventListener('click', toggle);
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
      });
    });

    updateEvalSummary();
  }

  function renderProbeResult(data) {
    const pill = $('probe-pill');

    if (!data.ok && data.auth_ok === false) {
      pill.className = 'probe-status err';
      pill.textContent = '认证失败 — 请检查 API Key';
      return;
    }

    if (!data.models_endpoint_supported) {
pill.className = 'probe-status warn';
pill.textContent = data.error || '未找到 /v1/models 端点 — 你可以手动输入模型名。';
show($('detection-workflow'));
renderModels([], null);
return;
    }

    State.probeData = data;
    // 使用后端返回的有效 base_url（可能已补 /v1）
    if (data.effective_base_url) {
      State.baseUrl = data.effective_base_url;
      // 同时更新输入框的值，让用户知道实际使用的 URL
      $('base_url').value = data.effective_base_url;
    }
    const a = data.by_protocol?.anthropic?.length || 0;
    const o = data.by_protocol?.openai?.length || 0;
    const g = data.by_protocol?.gemini?.length || 0;
    pill.className = 'probe-status ok';
    pill.innerHTML = `发现 <b>${data.raw_count}</b> 个模型 (Anthropic ${a} · OpenAI ${o} · Gemini ${g})`;

    // 显示工作流容器
    show($('detection-workflow'));
    renderModels(data.all_models || [], data.by_protocol);
    updateSummary();
  }

  // ============ Model Grid ============
  function renderModels(allModels, byProto) {
    const grid = $('model-grid');

    const protoMap = {};
    if (byProto) {
      for (const [p, ms] of Object.entries(byProto)) {
        for (const m of ms) protoMap[m] = p;
      }
    }
    for (const m of State.manualModels) {
      if (!protoMap[m]) protoMap[m] = guessProto(m);
    }

    const allSet = new Set([...allModels, ...State.manualModels]);
    const filtered = State.protoFilter === 'all'
      ? [...allSet]
      : [...allSet].filter(m => protoMap[m] === State.protoFilter);

    if (filtered.length === 0) {
      grid.innerHTML = '<div class="model-empty">没有匹配的模型，可手动添加。</div>';
      return;
    }

    grid.innerHTML = filtered.map(m => {
      const p = protoMap[m] || 'openai';
      const sel = State.selectedModels.has(m) ? ' selected' : '';
      return `<div class="model-card${sel}" data-model="${escapeHtml(m)}" tabindex="0" role="button" aria-pressed="${State.selectedModels.has(m)}">
        <div class="model-card-name">${escapeHtml(m)}</div>
        <div class="model-card-badge"><span class="dot dot-${p}"></span>${p}</div>
      </div>`;
    }).join('');

    grid.querySelectorAll('.model-card').forEach(card => {
      const toggle = () => {
        const m = card.dataset.model;
        if (State.selectedModels.has(m)) {
          State.selectedModels.delete(m);
          card.classList.remove('selected');
          card.setAttribute('aria-pressed', 'false');
        } else {
          State.selectedModels.add(m);
          card.classList.add('selected');
          card.setAttribute('aria-pressed', 'true');
        }
        updateSummary();
      };
      card.addEventListener('click', toggle);
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
      });
    });

    updateSummary();
  }

  function guessProto(m) {
    const s = m.toLowerCase();
    if (s.startsWith('claude')) return 'anthropic';
    if (s.startsWith('gemini')) return 'gemini';
    return 'openai';
  }

  // ============ Protocol Tabs ============
  function initProtocolTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        State.protoFilter = tab.dataset.proto;
        if (State.probeData) {
          renderModels(State.probeData.all_models, State.probeData.by_protocol);
        }
      });
    });
  }

  // ============ Model Actions ============
  function initModelActions() {
    $('select-all-models').addEventListener('click', () => {
      const all = State.probeData?.all_models || [];
      const byP = State.probeData?.by_protocol || {};
      const pmap = {};
      for (const [p, ms] of Object.entries(byP)) for (const m of ms) pmap[m] = p;
      const target = State.protoFilter === 'all' ? all : all.filter(m => pmap[m] === State.protoFilter);
      target.forEach(m => State.selectedModels.add(m));
      renderModels(all, byP);
    });

    $('deselect-all-models').addEventListener('click', () => {
      State.selectedModels.clear();
      if (State.probeData) renderModels(State.probeData.all_models, State.probeData.by_protocol);
      updateSummary();
    });

    $('manual-model-btn').addEventListener('click', () => {
      const row = $('manual-input-row');
      if (row.hidden) { show(row); $('manual-model-input').focus(); }
      else hide(row);
    });

    $('add-manual-model').addEventListener('click', addManual);
    $('manual-model-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); addManual(); }
    });
  }

  function addManual() {
    const input = $('manual-model-input');
    const m = input.value.trim();
    if (!m) return;
    State.manualModels.add(m);
    State.selectedModels.add(m);
    input.value = '';

    const all = [...(State.probeData?.all_models || []), ...State.manualModels];
    const origP = State.probeData?.by_protocol || { anthropic: [], openai: [], gemini: [] };
    const byP = JSON.parse(JSON.stringify(origP));
    for (const mm of State.manualModels) {
      const p = guessProto(mm);
      if (!byP[p]) byP[p] = [];
      if (!byP[p].includes(mm)) byP[p].push(mm);
    }
    renderModels(all, byP);
  }

  // ============ Mode Selection ============
  function initModes() {
    document.querySelectorAll('.mode-card').forEach(card => {
      const select = () => {
        document.querySelectorAll('.mode-card').forEach(c => {
          c.classList.remove('active');
          c.setAttribute('aria-pressed', 'false');
        });
        card.classList.add('active');
        card.setAttribute('aria-pressed', 'true');
        State.mode = card.dataset.mode;
        updateSummary();
      };
      card.addEventListener('click', select);
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(); }
      });
    });
  }

  // ============ Summary ============
  function updateSummary() {
    const models = [...State.selectedModels];
    
    // 更新已选模型栏
    const selectedCount = $('selected-count');
    const selectedTags = $('selected-tags');
    if (selectedCount) {
      selectedCount.textContent = `已选择 ${models.length} 个模型`;
    }
    if (selectedTags) {
      if (models.length === 0) {
        selectedTags.innerHTML = '<span style="color: var(--txt-4); font-size: 0.85rem;">点击上方模型卡片进行选择</span>';
      } else {
        selectedTags.innerHTML = models.map(m => `<span class="selected-tag">${escapeHtml(m)}</span>`).join('');
      }
    }
    
    // 更新启动区域
    const startBtn = $('start-btn');
    if (!startBtn) return;
    
    if (models.length === 0) {
      $('launch-summary').innerHTML = `
        <div class="summary-row" style="color: var(--txt-3);">
          <span>⚠️ 请先选择要检测的模型</span>
        </div>
      `;
      startBtn.disabled = true;
      startBtn.textContent = '请先选择模型';
      return;
    }
    
    startBtn.disabled = false;
    startBtn.textContent = '开始检测';

    const labels = { quick: 'Quick (~15s/模型)', standard: 'Standard (~40s/模型)', full: 'Full (~70s+/模型)' };
    const perModel = State.mode === 'quick' ? 15 : State.mode === 'standard' ? 40 : 70;
    const total = models.length * perModel;
    const timeStr = total < 60 ? total + 's' : Math.floor(total / 60) + 'm ' + (total % 60) + 's';

    const modelsList = models.map(m => `<span class="summary-model-tag">${escapeHtml(m)}</span>`).join('');
    $('launch-summary').innerHTML = `
      <div class="summary-row"><span>检测模型</span><strong>${models.length} 个</strong></div>
      <div class="summary-models-list">${modelsList}</div>
      <div class="summary-row"><span>检测模式</span><strong>${escapeHtml(labels[State.mode] || State.mode)}</strong></div>
      <div class="summary-row"><span>预计耗时</span><strong>~${timeStr}</strong></div>
    `;
  }

  // ============ Start Detection ============
  function initStart() {
    $('start-btn').addEventListener('click', startDetection);
  }

  async function startDetection() {
    const models = [...State.selectedModels];
    if (models.length === 0) return;

    // 优先使用输入框的值（因为探测阶段会更新输入框为 effective_base_url）
    const baseUrl = $('base_url').value.trim();
    const apiKey = $('api_key').value.trim();
    
    // 更新 State 以确保使用最新的值
    State.baseUrl = baseUrl;
    State.apiKey = apiKey;
    
    State.currentRelayUrl = baseUrl;

    const btn = $('start-btn');
    btn.disabled = true;
    btn.textContent = '启动中...';

    hide($('detection-workflow'));
    show($('step-results'));
    State.completeHandled = false;

    $('results-container').innerHTML = '';
    $('step-results').scrollIntoView({ behavior: 'smooth' });

    $('progress-container').innerHTML = models.map((m, i) => `
      <div class="prog-item" id="prog-${i}">
        <div class="prog-head">
          <span class="prog-name">${escapeHtml(m)}</span>
          <span class="prog-badge pending">等待</span>
        </div>
        <div class="prog-bar"><div class="prog-fill" style="width:0"></div></div>
      </div>
    `).join('');

    try {
      const resp = await fetch('/api/detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: baseUrl,
          api_key: apiKey,
          models,
          mode: State.mode,
        }),
      });
      const data = await resp.json();

      if (!data.ok) {
        $('results-container').innerHTML = `<div class="probe-status err">启动失败: ${escapeHtml(data.error || '')}</div>`;
        btn.disabled = false;
        btn.textContent = '开始检测';
        show($('detection-workflow'));
        hide($('step-results'));
        return;
      }

      pollStatus(data.job_id, models);
    } catch (e) {
      $('results-container').innerHTML = `<div class="probe-status err">网络错误: ${escapeHtml(e.message)}</div>`;
      btn.disabled = false;
      btn.textContent = '开始检测';
      show($('detection-workflow'));
      hide($('step-results'));
    }
  }

  // ============ Status Polling (SSE + fallback) ============
  function pollStatus(jobId, models) {
    if (typeof EventSource !== 'undefined') {
      const es = new EventSource(`/api/status/${jobId}`);
      let errCount = 0;

      es.addEventListener('progress', (e) => {
        const evt = JSON.parse(e.data);
        handleProgress(evt, models);
      });
      es.addEventListener('complete', (e) => {
        const data = JSON.parse(e.data);
        es.close();
        handleComplete(data);
      });
      es.addEventListener('error', () => {
        errCount++;
        if (errCount > 3) { es.close(); pollFallback(jobId, models); }
      });
    } else {
      pollFallback(jobId, models);
    }
  }

  function pollFallback(jobId, models) {
    let lastIdx = 0;
    const iv = setInterval(async () => {
      try {
        const resp = await fetch(`/api/status/${jobId}`);
        const data = await resp.json();
        if (data.status === 'done' || data.status === 'error') {
          clearInterval(iv);
          (data.progress || []).slice(lastIdx).forEach(e => handleProgress(e, models));
          if (!State.completeHandled) handleComplete(data);
          return;
        }
        const evts = (data.progress || []).slice(lastIdx);
        lastIdx = (data.progress || []).length;
        evts.forEach(e => handleProgress(e, models));
      } catch (e) { /* keep polling */ }
    }, 1000);
  }

  // ============ Progress Handler ============
  function handleProgress(evt, models) {
    if (evt.type === 'model_start') {
      const p = $('prog-' + evt.index);
      if (p) {
        p.querySelector('.prog-badge').className = 'prog-badge running';
        p.querySelector('.prog-badge').textContent = '检测中';
        p.querySelector('.prog-fill').className = 'prog-fill indeterminate';
      }
    } else if (evt.type === 'model_done') {
      const p = $('prog-' + evt.index);
      if (p) {
        p.querySelector('.prog-badge').className = 'prog-badge done';
        p.querySelector('.prog-badge').textContent = '完成';
        const fill = p.querySelector('.prog-fill');
        fill.className = 'prog-fill';
        fill.style.width = '100%';
      }
      renderReport(evt.report);
    } else if (evt.type === 'model_error') {
      const p = $('prog-' + evt.index);
      if (p) {
        p.querySelector('.prog-badge').className = 'prog-badge error';
        p.querySelector('.prog-badge').textContent = '错误';
        const fill = p.querySelector('.prog-fill');
        fill.className = 'prog-fill';
        fill.style.width = '100%';
        fill.style.background = 'var(--red)';
      }
      renderReport({ model: evt.model, error: evt.error });
    }
  }

  // ============ Complete Handler ============
  function handleComplete(data) {
    if (State.completeHandled) return;
    State.completeHandled = true;

    if (data.reports) {
      for (const r of data.reports) {
        r.base_url = State.currentRelayUrl;
        Store.addReport(r);
        const sel = `[data-rpt="${cssEscape(r.model)}"]`;
        if (!document.querySelector(sel)) renderReport(r);
      }
      if (data.reports.length > 1) renderComparison(data.reports);
    }

    const container = $('results-container');
    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex;gap:0.6rem;margin-top:1.5rem;flex-wrap:wrap;';

    const newBtn = document.createElement('button');
    newBtn.className = 'btn-secondary';
    newBtn.textContent = '重新检测';
    newBtn.addEventListener('click', () => location.reload());
    actions.appendChild(newBtn);

    const dlBtn = document.createElement('button');
    dlBtn.className = 'btn-secondary';
    dlBtn.textContent = '下载 JSON 报告';
    dlBtn.addEventListener('click', () => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `model-detective-${data.job_id || Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    });
    actions.appendChild(dlBtn);

    container.appendChild(actions);
  }

  // ============ Report Card ============
  function renderReport(r) {
    const c = $('results-container');

    if (r.error) {
      const card = document.createElement('div');
      card.className = 'report-card';
      card.dataset.rpt = r.model;
      card.innerHTML = `
        <div class="report-head">
          <div class="report-head-top">
            <div>
              <div class="report-name">${escapeHtml(r.model)}</div>
            </div>
            <span class="report-verdict" style="background:rgba(239,68,68,0.12);color:var(--red)">ERROR</span>
          </div>
          <div style="color:var(--txt-2);font-size:0.88rem;">检测失败: ${escapeHtml(r.error)}</div>
        </div>`;
      c.appendChild(card);
      return;
    }

    const score = r.total_score || 0;
    const sc = score >= 85 ? 'var(--green)' : score >= 70 ? 'var(--blue)' : score >= 50 ? 'var(--yellow)' : 'var(--red)';
    const vcs = {
      passed_excellent: { bg: 'rgba(34,197,94,0.12)', co: 'var(--green)', lb: '优秀' },
      passed: { bg: 'rgba(34,197,94,0.08)', co: 'var(--green)', lb: '通过' },
      marginal: { bg: 'rgba(245,158,11,0.12)', co: 'var(--yellow)', lb: '及格' },
      failed: { bg: 'rgba(239,68,68,0.12)', co: 'var(--red)', lb: '不通过' },
    };
    const vc = vcs[r.verdict] || vcs.failed;
    const bk = r.backend_source_cn || backendLabel(r.backend_source);
    const deg = r.degraded ? ` <span style="color:var(--yellow);font-size:0.78rem;">[降级: ${escapeHtml(r.degrade_reason || '原生协议不可用')}]</span>` : '';

    const card = document.createElement('div');
    card.className = 'report-card';
    card.dataset.rpt = r.model;
    card.innerHTML = `
      <div class="report-head">
        <div class="report-head-top">
          <div>
            <div class="report-name">${escapeHtml(r.model)}${deg}</div>
            <div class="report-meta">
              <span>🔗 ${escapeHtml(r.base_url || '未知中转站')}</span>
              <span>协议: ${escapeHtml(r.protocol)}</span>
              <span>模式: ${escapeHtml(r.mode)}</span>
              <span>耗时: ${r.duration_seconds}s</span>
              <span>Tokens: ${r.total_tokens}</span>
              <span>费用: $${r.estimated_cost_usd}</span>
              ${bk ? `<span class="backend-badge ${backendClass(r.backend_source)}">${escapeHtml(bk)}</span>` : ''}
            </div>
          </div>
          <div class="report-score" style="border-color:${sc}">
            <div class="report-score-val" style="color:${sc}">${score.toFixed(0)}</div>
            <div class="report-score-lbl">Score</div>
          </div>
        </div>
        <div style="display:flex;gap:0.6rem;align-items:center;">
          <span class="report-verdict" style="background:${vc.bg};color:${vc.co}">${vc.lb}</span>
          ${r.has_critical ? '<span class="issue-badge iss-critical">存在严重问题</span>' : ''}
        </div>
        <div class="report-dims">
          ${renderDim('真伪', r.authenticity_score)}
          ${renderDim('能力', r.capability_score)}
          ${renderDim('合规', r.compliance_score)}
        </div>
      </div>
      <div class="report-body">
        <table class="det-table">
          <thead><tr><th>检测项</th><th>状态</th><th>得分</th><th>类别</th><th>问题 & 详情</th></tr></thead>
          <tbody>${r.results.map(renderRow).join('')}</tbody>
        </table>
      </div>`;
    c.appendChild(card);
  }

  function renderDim(label, score) {
    const co = score >= 85 ? 'var(--green)' : score >= 70 ? 'var(--blue)' : score >= 50 ? 'var(--yellow)' : 'var(--red)';
    return `<div class="dim-card">
      <div class="dim-label">${escapeHtml(label)}</div>
      <div class="dim-score" style="color:${co}">${score.toFixed(1)}</div>
      <div class="dim-bar"><div class="dim-fill" style="width:${score}%;background:${co}"></div></div>
    </div>`;
  }

  function renderRow(r) {
    const isB = r.name.includes('billing') || r.name.includes('token');
    const co = r.score >= 85 ? 'var(--green)' : r.score >= 70 ? 'var(--blue)' : r.score >= 50 ? 'var(--yellow)' : 'var(--red)';
    const cnName = r.cn_name || r.name;
    const cnDesc = r.cn_desc || '';
    const catCn = r.category_cn || r.category;
    const issues = (r.issues || []).map(iss =>
      `<span class="issue-badge iss-${iss.level}">${escapeHtml(iss.message)}</span>`
    ).join('');
    return `<tr class="${isB ? 'billing-hl' : ''}">
      <td><div class="det-name">${escapeHtml(cnName)}</div><div class="det-name-cn">${escapeHtml(r.name)}</div>${cnDesc ? `<div class="det-desc">${escapeHtml(cnDesc)}</div>` : ''}</td>
      <td><span class="det-status st-${r.status}">${escapeHtml(r.status)}</span></td>
      <td><div class="det-score" style="color:${co}">${r.score.toFixed(1)}</div><div class="score-bar"><div class="score-fill" style="width:${r.score}%;background:${co}"></div></div></td>
      <td><span style="font-size:0.72rem;color:var(--txt-3);">${escapeHtml(catCn)}</span></td>
      <td>${issues}${r.details ? `<div class="det-details">${escapeHtml(r.details)}</div>` : ''}</td>
    </tr>`;
  }

  // ============ Comparison ============
  function renderComparison(reports) {
    const c = $('results-container');
    const div = document.createElement('div');
    div.className = 'report-card';
    div.innerHTML = `
      <div class="report-head">
        <div class="report-head-top">
          <div>
            <div class="report-name">对比摘要</div>
            <div class="report-meta"><span>${reports.length} 个模型</span></div>
          </div>
        </div>
      </div>
      <div class="report-body">
        <table class="det-table">
          <thead><tr><th>模型</th><th>总分</th><th>判定</th><th>真伪</th><th>能力</th><th>合规</th><th>费用</th><th>后端</th></tr></thead>
          <tbody>${reports.map(r => {
            const s = r.total_score || 0;
            const sc = s >= 85 ? 'var(--green)' : s >= 70 ? 'var(--blue)' : s >= 50 ? 'var(--yellow)' : 'var(--red)';
            const vc = ({
              passed_excellent: { bg: 'rgba(34,197,94,0.12)', co: 'var(--green)', lb: '优秀' },
              passed: { bg: 'rgba(34,197,94,0.08)', co: 'var(--green)', lb: '通过' },
              marginal: { bg: 'rgba(245,158,11,0.12)', co: 'var(--yellow)', lb: '及格' },
              failed: { bg: 'rgba(239,68,68,0.12)', co: 'var(--red)', lb: '不通过' },
            })[r.verdict] || { bg: 'rgba(239,68,68,0.12)', co: 'var(--red)', lb: '不通过' };
            return `<tr>
              <td><div class="det-name">${escapeHtml(r.model)}</div></td>
              <td><div class="det-score" style="color:${sc}">${s.toFixed(1)}</div></td>
              <td><span class="report-verdict" style="background:${vc.bg};color:${vc.co};font-size:0.68rem;">${vc.lb}</span></td>
              <td style="color:${r.authenticity_score >= 70 ? 'var(--green)' : 'var(--yellow)'}">${r.authenticity_score.toFixed(1)}</td>
              <td style="color:${r.capability_score >= 70 ? 'var(--green)' : 'var(--yellow)'}">${r.capability_score.toFixed(1)}</td>
              <td style="color:${r.compliance_score >= 70 ? 'var(--green)' : 'var(--yellow)'}">${r.compliance_score.toFixed(1)}</td>
              <td>$${r.estimated_cost_usd}</td>
              <td>${escapeHtml(r.backend_source_cn || backendLabel(r.backend_source)) || '-'}</td>
            </tr>`;
          }).join('')}</tbody>
        </table>
      </div>`;
    c.insertBefore(div, c.firstChild);
  }

  function backendLabel(s) {
    return ({ anthropic_direct: 'Anthropic Direct', bedrock_direct: 'Bedrock', kiro_proxy: 'Kiro', vertex_proxy: 'Vertex', unknown_proxy: 'Unknown Proxy' })[s] || '';
  }
  function backendClass(s) {
    if (s === 'kiro_proxy') return 'kiro';
    if (s === 'bedrock_direct') return 'bedrock';
    if (s === 'vertex_proxy') return 'vertex';
    return '';
  }

  // ============ URL Autocomplete ============
  function initUrlAutocomplete() {
    const input = $('base_url');
    const ac = $('url-autocomplete');

    input.addEventListener('input', () => {
      const val = input.value.trim().toLowerCase();
      if (!val || val.length < 2) { hide(ac); return; }
      const urls = Store.getUrls().filter(u => u.toLowerCase().includes(val) && u.toLowerCase() !== val);
      if (urls.length === 0) { hide(ac); return; }
      ac.innerHTML = urls.slice(0, 8).map(u =>
        `<div class="ac-item" data-url="${escapeHtml(u)}">${escapeHtml(u)}</div>`
      ).join('');
      ac.querySelectorAll('.ac-item').forEach(item => {
        item.addEventListener('click', () => {
          input.value = item.dataset.url;
          hide(ac);
          onInputChange();
        });
      });
      show(ac);
    });

    input.addEventListener('blur', () => { setTimeout(() => hide(ac), 200); });
    input.addEventListener('focus', () => { input.dispatchEvent(new Event('input')); });
  }

  // ============ History ============
  function initHistory() {
    $('history-btn').addEventListener('click', renderHistory);
  }

  function renderHistory() {
    const reports = Store.getReports();
    const c = $('results-container');

    hide($('step-config'));
    hide($('step-models'));
    hide($('step-mode'));
    hide($('step-start'));
    show($('step-results'));
    c.innerHTML = '';

    const card = document.createElement('div');
    card.className = 'report-card';
    card.innerHTML = `
      <div class="report-head">
        <div class="report-head-top">
          <div>
            <div class="report-name">检测历史</div>
            <div class="report-meta"><span>${reports.length} 条记录</span></div>
          </div>
          <button class="btn-secondary" id="clear-history">清空历史</button>
        </div>
      </div>
      <div class="report-body">${reports.length === 0 ?
        '<div style="text-align:center;padding:2rem;color:var(--txt-3);">暂无检测历史记录</div>' :
        `<table class="det-table">
          <thead><tr><th>时间</th><th>中转站</th><th>模型</th><th>总分</th><th>判定</th><th>操作</th></tr></thead>
          <tbody>${reports.map(r => {
            const s = r.total_score || 0;
            const sc = s >= 85 ? 'var(--green)' : s >= 70 ? 'var(--blue)' : s >= 50 ? 'var(--yellow)' : 'var(--red)';
            const vcs = { passed_excellent: '优秀', passed: '通过', marginal: '及格', failed: '不通过' };
            const vcl = { passed_excellent: 'var(--green)', passed: 'var(--green)', marginal: 'var(--yellow)', failed: 'var(--red)' };
            const time = new Date(r.time).toLocaleString('zh-CN');
            return `<tr>
              <td style="font-size:0.82rem;color:var(--txt-3);white-space:nowrap;">${escapeHtml(time)}</td>
              <td style="font-size:0.82rem;font-family:'JetBrains Mono',monospace;color:var(--cyan);">${escapeHtml(r.base_url || '-')}</td>
              <td><div class="det-name" style="font-size:0.85rem;">${escapeHtml(r.model)}</div></td>
              <td><div class="det-score" style="color:${sc}">${s.toFixed(1)}</div></td>
              <td><span class="report-verdict" style="background:rgba(255,255,255,0.05);color:${vcl[r.verdict] || 'var(--red)'};font-size:0.76rem;">${vcs[r.verdict] || r.verdict}</span></td>
              <td><button class="btn-ghost view-report" data-id="${escapeHtml(r.id)}" style="font-size:0.8rem;">查看</button>
                  <button class="btn-ghost del-report" data-id="${escapeHtml(r.id)}" style="font-size:0.8rem;color:var(--red);">删除</button></td>
            </tr>`;
          }).join('')}</tbody>
        </table>`
      }</div>`;

    c.appendChild(card);

    c.querySelectorAll('.view-report').forEach(btn => {
      btn.addEventListener('click', () => viewHistoryReport(btn.dataset.id));
    });
    c.querySelectorAll('.del-report').forEach(btn => {
      btn.addEventListener('click', () => { Store.deleteReport(btn.dataset.id); renderHistory(); });
    });
    const clr = $('clear-history');
    if (clr) clr.addEventListener('click', () => {
      if (confirm('确定清空所有检测历史？')) { Store.clearReports(); renderHistory(); }
    });

    const backBtn = document.createElement('button');
    backBtn.className = 'btn-secondary';
    backBtn.textContent = '← 返回';
    backBtn.style.marginTop = '1rem';
    backBtn.addEventListener('click', () => location.reload());
    c.appendChild(backBtn);
  }

  function viewHistoryReport(id) {
    const reports = Store.getReports();
    const r = reports.find(x => x.id === id);
    if (!r) return;
    const c = $('results-container');
    c.innerHTML = '';
    renderReport(r);
    const backBtn = document.createElement('button');
    backBtn.className = 'btn-secondary';
    backBtn.textContent = '← 返回历史';
    backBtn.style.marginTop = '1rem';
    backBtn.addEventListener('click', renderHistory);
    c.appendChild(backBtn);
  }

  // ============ Evaluation: Dimension Checkboxes ============
  function initEvalDimensions() {
    const checkboxes = document.querySelectorAll('#eval-dimensions .eval-dim-checkbox');
    checkboxes.forEach(cb => {
      cb.addEventListener('click', (e) => {
        const checkbox = cb.querySelector('input[type="checkbox"]');
        if (e.target !== checkbox) {
          checkbox.checked = !checkbox.checked;
        }
        cb.classList.toggle('checked', checkbox.checked);
        // Sync State.evalDimensions
        State.evalDimensions = [];
        document.querySelectorAll('#eval-dimensions .eval-dim-checkbox').forEach(c => {
          if (c.querySelector('input[type="checkbox"]').checked) {
            State.evalDimensions.push(c.dataset.dim);
          }
        });
        updateEvalSummary();
      });
    });
  }

  // ============ Evaluation: Model Actions (select all / deselect / manual add) ============
  function initEvalModelActions() {
    $('eval-select-all-models').addEventListener('click', () => {
      const all = State.evalProbeData?.all_models || [];
      const byP = State.evalProbeData?.by_protocol || {};
      const pmap = {};
      for (const [p, ms] of Object.entries(byP)) for (const m of ms) pmap[m] = p;
      const target = State.evalProtoFilter === 'all' ? all : all.filter(m => pmap[m] === State.evalProtoFilter);
      target.forEach(m => State.evalSelectedModels.add(m));
      renderEvalModels(all, byP);
    });

    $('eval-deselect-all-models').addEventListener('click', () => {
      State.evalSelectedModels.clear();
      if (State.evalProbeData) renderEvalModels(State.evalProbeData.all_models, State.evalProbeData.by_protocol);
      updateEvalSummary();
    });

    $('eval-manual-model-btn').addEventListener('click', () => {
      const row = $('eval-manual-input-row');
      if (row.hidden) { show(row); $('eval-manual-model-input').focus(); }
      else hide(row);
    });

    $('eval-add-manual-model').addEventListener('click', addEvalManual);
    $('eval-manual-model-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); addEvalManual(); }
    });
  }

  function addEvalManual() {
    const input = $('eval-manual-model-input');
    const m = input.value.trim();
    if (!m) return;
    State.evalManualModels.add(m);
    State.evalSelectedModels.add(m);
    input.value = '';

    const all = [...(State.evalProbeData?.all_models || []), ...State.evalManualModels];
    const origP = State.evalProbeData?.by_protocol || { anthropic: [], openai: [], gemini: [] };
    const byP = JSON.parse(JSON.stringify(origP));
    for (const mm of State.evalManualModels) {
      const p = guessEvalProto(mm);
      if (!byP[p]) byP[p] = [];
      if (!byP[p].includes(mm)) byP[p].push(mm);
    }
    renderEvalModels(all, byP);
  }

  // ============ Evaluation: Protocol Tabs ============
  function initEvalProtocolTabs() {
    document.querySelectorAll('#eval-protocol-tabs .tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('#eval-protocol-tabs .tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        State.evalProtoFilter = tab.dataset.evalProto;
        if (State.evalProbeData) {
          renderEvalModels(State.evalProbeData.all_models, State.evalProbeData.by_protocol);
        }
      });
    });
  }

  // ============ Evaluation: Difficulty Selection ============
  function initEvalDifficulty() {
    const options = document.querySelectorAll('#eval-difficulty .eval-difficulty-option');
    options.forEach(opt => {
      opt.addEventListener('click', () => {
        options.forEach(o => o.classList.remove('active'));
        opt.classList.add('active');
        State.evalDifficulty = opt.dataset.diff;
        updateEvalSummary();
      });
    });
  }

  // ============ Evaluation: Parse Models ============
  function parseEvalModels(text) {
    const fromText = text.split(/[,\n\r]+/)
      .map(m => m.trim())
      .filter(m => m.length > 0 && m.length <= 200);
    // Merge with selected models from grid
    const all = new Set([...fromText, ...State.evalSelectedModels]);
    return [...all];
  }

  // ============ Evaluation: Guess Protocol ============
  function guessEvalProto(m) {
    const s = m.toLowerCase();
    if (s.startsWith('claude')) return 'anthropic';
    if (s.startsWith('gemini')) return 'gemini';
    return 'openai';
  }

  // ============ Evaluation: Update Summary ============
  function updateEvalSummary() {
    const text = $('eval-models-input').value;
    const models = parseEvalModels(text);
    
    // 合并从网格选中的模型
    State.evalSelectedModels.forEach(m => {
      if (!models.includes(m)) models.push(m);
    });
    
    if (models.length === 0) {
      hide($('eval-step-launch'));
      return;
    }

    // 确保维度步骤可见
    show($('eval-step-dimensions'));

    const diffLabels = { quick: '精简版 (20题)', standard: '标准版 (40题)', full: '完整版 (100题)' };
    const timePerModel = State.evalDifficulty === 'quick' ? '~2分钟' : State.evalDifficulty === 'standard' ? '~5分钟' : '~12分钟';
    const totalTime = models.length * (State.evalDifficulty === 'quick' ? 2 : State.evalDifficulty === 'standard' ? 5 : 12);
    const timeStr = totalTime < 60 ? `${totalTime}分钟` : `${Math.floor(totalTime / 60)}小时${totalTime % 60}分钟`;

    $('eval-launch-summary').innerHTML = `
      <div class="summary-row"><span>待测评模型</span><strong>${models.length} 个</strong></div>
      <div class="summary-row"><span>测评维度</span><strong>${State.evalDimensions.length} 个</strong></div>
      <div class="summary-row"><span>测评模式</span><strong>${escapeHtml(diffLabels[State.evalDifficulty] || State.evalDifficulty)}</strong></div>
      <div class="summary-row"><span>预计耗时</span><strong>~${timeStr}</strong></div>
      <div class="summary-models">${models.map(m => `<span class="summary-tag">${escapeHtml(m)}</span>`).join('')}</div>
    `;
    show($('eval-step-launch'));
  }

  // ============ Evaluation: Start ============
  function initEvalStart() {
    $('eval-start-btn').addEventListener('click', startEvaluation);
  }

async function startEvaluation() {
    // 验证 API 配置是否已填写
    // 优先使用输入框的值（因为探测阶段会更新输入框为 effective_base_url）
    const baseUrl = $('eval-base_url').value.trim();
    const apiKey = $('eval-api_key').value.trim();

    if (!baseUrl.startsWith('http')) {
      alert('请填写有效的中转站网址 (Base URL)');
      show($('eval-step-config'));
      $('eval-base_url').focus();
      return;
    }
    if (apiKey.length < 8) {
      alert('请填写有效的 API Key');
      show($('eval-step-config'));
      $('eval-api_key').focus();
      return;
    }

    // 更新 State 以确保使用最新的值
    State.evalBaseUrl = baseUrl;
    State.evalApiKey = apiKey;
    
    const text = $('eval-models-input').value;
    const models = parseEvalModels(text);
    if (models.length === 0) {
      alert('请至少输入一个待测评模型');
      show($('eval-step-models'));
      $('eval-models-input').focus();
      return;
    }

    const btn = $('eval-start-btn');
    btn.disabled = true;
    btn.textContent = '启动中...';

    hide($('eval-step-config'));
    hide($('eval-step-models'));
    hide($('eval-step-dimensions'));
    hide($('eval-step-launch'));
    show($('eval-step-results'));
    State.evalCompleteHandled = false;

    $('eval-results-container').innerHTML = '';
    $('eval-progress-container').innerHTML = models.map((m, i) => `
      <div class="prog-item" id="eval-prog-${i}">
        <div class="prog-head">
          <span class="prog-name">${escapeHtml(m)}</span>
          <span class="prog-badge pending">等待</span>
        </div>
        <div class="prog-bar"><div class="prog-fill" style="width:0"></div></div>
      </div>
    `).join('');

    try {
      const dimensions = [];
      document.querySelectorAll('#eval-dimensions .eval-dim-checkbox').forEach(cb => {
        if (cb.querySelector('input[type="checkbox"]').checked) {
          dimensions.push(cb.dataset.dim);
        }
      });

      const resp = await fetch('/api/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: State.evalBaseUrl,
          api_key: State.evalApiKey,
          models,
          difficulty: State.evalDifficulty,
          dimensions,
        }),
      });
      const data = await resp.json();

      if (!data.ok) {
        $('eval-results-container').innerHTML = `<div class="probe-status err">启动失败: ${escapeHtml(data.error || '')}</div>`;
        btn.disabled = false;
        btn.textContent = '开始测评';
        show($('eval-step-config'));
        show($('eval-step-models'));
        show($('eval-step-dimensions'));
        show($('eval-step-launch'));
        hide($('eval-step-results'));
        return;
      }

      pollEvalStatus(data.job_id, models);
    } catch (e) {
      $('eval-results-container').innerHTML = `<div class="probe-status err">网络错误: ${escapeHtml(e.message)}</div>`;
      btn.disabled = false;
      btn.textContent = '开始测评';
      show($('eval-step-config'));
      show($('eval-step-models'));
      show($('eval-step-dimensions'));
      show($('eval-step-launch'));
      hide($('eval-step-results'));
    }
  }

  // ============ Evaluation: Status Polling ============
  function pollEvalStatus(jobId, models) {
    if (typeof EventSource !== 'undefined') {
      const es = new EventSource(`/api/evaluate/status/${jobId}`);
      let errCount = 0;

      es.addEventListener('progress', (e) => {
        const evt = JSON.parse(e.data);
        handleEvalProgress(evt, models);
      });
      es.addEventListener('complete', (e) => {
        const data = JSON.parse(e.data);
        es.close();
        handleEvalComplete(data);
      });
      es.addEventListener('error', () => {
        errCount++;
        if (errCount > 3) { es.close(); pollEvalFallback(jobId, models); }
      });
    } else {
      pollEvalFallback(jobId, models);
    }
  }

  function pollEvalFallback(jobId, models) {
    let lastIdx = 0;
    const iv = setInterval(async () => {
      try {
        const resp = await fetch(`/api/evaluate/status/${jobId}`);
        const data = await resp.json();
        if (data.status === 'done' || data.status === 'error') {
          clearInterval(iv);
          (data.progress || []).slice(lastIdx).forEach(e => handleEvalProgress(e, models));
          if (!State.evalCompleteHandled) handleEvalComplete(data);
          return;
        }
        const evts = (data.progress || []).slice(lastIdx);
        lastIdx = (data.progress || []).length;
        evts.forEach(e => handleEvalProgress(e, models));
      } catch (e) { /* keep polling */ }
    }, 1000);
  }

  // ============ Evaluation: Progress Handler ============
  function handleEvalProgress(evt, models) {
    if (evt.type === 'model_start') {
      const idx = models.indexOf(evt.model);
      if (idx >= 0) {
        const p = $('eval-prog-' + idx);
        if (p) {
          p.querySelector('.prog-badge').className = 'prog-badge running';
          p.querySelector('.prog-badge').textContent = '测评中';
          p.querySelector('.prog-fill').className = 'prog-fill indeterminate';
        }
      }
    } else if (evt.type === 'model_done') {
      const idx = models.indexOf(evt.model);
      if (idx >= 0) {
        const p = $('eval-prog-' + idx);
        if (p) {
          p.querySelector('.prog-badge').className = 'prog-badge done';
          p.querySelector('.prog-badge').textContent = '完成';
          const fill = p.querySelector('.prog-fill');
          fill.className = 'prog-fill';
          fill.style.width = '100%';
        }
      }
      if (evt.report) {
        renderEvalResult(evt.report);
      }
    } else if (evt.type === 'model_error') {
      const idx = models.indexOf(evt.model);
      if (idx >= 0) {
        const p = $('eval-prog-' + idx);
        if (p) {
          p.querySelector('.prog-badge').className = 'prog-badge error';
          p.querySelector('.prog-badge').textContent = '错误';
          const fill = p.querySelector('.prog-fill');
          fill.className = 'prog-fill';
          fill.style.width = '100%';
          fill.style.background = 'var(--red)';
        }
      }
    } else if (evt.type === 'progress') {
      const progress = $('eval-progress-bar');
      if (progress) {
        const fill = progress.querySelector('.eval-progress-fill');
        if (fill) {
          fill.style.width = evt.score + '%';
        }
      }
    }
  }

  // ============ Evaluation: Complete Handler ============
  function handleEvalComplete(data) {
    if (State.evalCompleteHandled) return;
    State.evalCompleteHandled = true;

    if (data.results && data.results.length > 0) {
      for (const r of data.results) {
        renderEvalResult(r);
      }
      if (data.results.length > 1) {
        renderEvalComparison(data.results);
      }
    }

    const container = $('eval-results-container');
    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex;gap:0.6rem;margin-top:1.5rem;flex-wrap:wrap;';

    const newBtn = document.createElement('button');
    newBtn.className = 'btn-secondary';
    newBtn.textContent = '重新测评';
    newBtn.addEventListener('click', () => location.reload());
    actions.appendChild(newBtn);

    const dlBtn = document.createElement('button');
    dlBtn.className = 'btn-secondary';
    dlBtn.textContent = '下载 JSON 报告';
    dlBtn.addEventListener('click', () => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `model-evaluation-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    });
    actions.appendChild(dlBtn);

    container.appendChild(actions);
  }

  // ============ Evaluation: Render Result ============
  function renderEvalResult(r) {
    const c = $('eval-results-container');

    if (r.error) {
      const card = document.createElement('div');
      card.className = 'eval-result-card';
      card.innerHTML = `
        <div class="eval-result-head">
          <div class="eval-result-head-top">
            <div>
              <div class="eval-result-name">${escapeHtml(r.model)}</div>
            </div>
            <span class="report-verdict" style="background:rgba(239,68,68,0.12);color:var(--red)">ERROR</span>
          </div>
          <div style="color:var(--txt-2);font-size:0.88rem;">测评失败: ${escapeHtml(r.error || '未知错误')}</div>
        </div>`;
      c.appendChild(card);
      return;
    }

    const score = r.total_score || 0;
    const sc = score >= 85 ? 'var(--green)' : score >= 70 ? 'var(--blue)' : score >= 50 ? 'var(--yellow)' : 'var(--red)';
    const verdictLabels = { excellent: '优秀', good: '良好', average: '一般', poor: '较差' };
    const verdictBg = score >= 85 ? 'rgba(34,197,94,0.12)' : score >= 70 ? 'rgba(59,130,246,0.12)' : score >= 50 ? 'rgba(245,158,11,0.12)' : 'rgba(239,68,68,0.12)';
    const verdictCo = sc;

    const dimLabels = {
      basic_language: '基础语言',
      technical: '技术能力',
      advanced_cognition: '高级认知',
      practical: '实用能力',
      boundary: '边界鲁棒',
    };

    let dimsHtml = '';
    for (const [dimKey, dimVal] of Object.entries(r.dimension_scores || {})) {
      const dimColor = dimVal >= 85 ? 'var(--green)' : dimVal >= 70 ? 'var(--blue)' : dimVal >= 50 ? 'var(--yellow)' : 'var(--red)';
      dimsHtml += `<div class="eval-dim-card">
        <div class="eval-dim-label">${dimLabels[dimKey] || dimKey}</div>
        <div class="eval-dim-score" style="color:${dimColor}">${dimVal.toFixed(1)}</div>
        <div class="eval-dim-bar"><div class="eval-dim-fill" style="width:${dimVal}%;background:${dimColor}"></div></div>
      </div>`;
    }

    const questionRows = (r.question_results || []).map(qr => {
      const qScore = qr.score || 0;
      const qMax = qr.max_score || 100;
      const qPercent = qMax > 0 ? (qScore / qMax * 100) : 0;
      const qColor = qPercent >= 85 ? 'var(--green)' : qPercent >= 70 ? 'var(--blue)' : qPercent >= 50 ? 'var(--yellow)' : 'var(--red)';
      const dimLabel = dimLabels[qr.dimension] || qr.dimension;
      return `<tr>
        <td><div class="eq-title">${escapeHtml(qr.title)}</div><div class="eq-dim">${dimLabel}</div></td>
        <td><div class="eq-score" style="color:${qColor}">${qScore.toFixed(0)}/${qMax}</div></td>
        <td><div class="eq-details">${escapeHtml(qr.details || '')}</div></td>
      </tr>`;
    }).join('');

    const card = document.createElement('div');
    card.className = 'eval-result-card';
    card.innerHTML = `
      <div class="eval-result-head">
        <div class="eval-result-head-top">
          <div>
            <div class="eval-result-name">${escapeHtml(r.model)}</div>
            <div class="eval-result-meta">
              <span>协议: ${escapeHtml(r.protocol || 'N/A')}</span>
              <span>耗时: ${r.duration_seconds || 0}s</span>
              <span>Tokens: ${r.total_tokens || 0}</span>
              <span>费用: $${(r.estimated_cost_usd || 0).toFixed(6)}</span>
            </div>
          </div>
          <div class="eval-result-score" style="border-color:${sc}">
            <div class="eval-result-score-val" style="color:${sc}">${score.toFixed(0)}</div>
            <div class="eval-result-score-lbl">Score</div>
          </div>
        </div>
        <div style="display:flex;gap:0.6rem;align-items:center;">
          <span class="report-verdict" style="background:${verdictBg};color:${verdictCo}">${verdictLabels[r.verdict] || r.verdict}</span>
          ${r.errors && r.errors.length > 0 ? `<span class="issue-badge iss-critical">${r.errors.length} 个错误</span>` : ''}
        </div>
        <div class="eval-result-dims">
          ${dimsHtml}
        </div>
      </div>
      <div class="report-body">
        <table class="eval-question-table">
          <thead><tr><th>题目</th><th>得分</th><th>详情</th></tr></thead>
          <tbody>${questionRows}</tbody>
        </table>
      </div>`;
    c.appendChild(card);
  }

  // ============ Evaluation: Render Comparison ============
  function renderEvalComparison(results) {
    const c = $('eval-results-container');
    const div = document.createElement('div');
    div.className = 'eval-result-card';

    const sorted = [...results].sort((a, b) => (b.total_score || 0) - (a.total_score || 0));

    const dimLabels = {
      basic_language: '基础语言',
      technical: '技术能力',
      advanced_cognition: '高级认知',
      practical: '实用能力',
      boundary: '边界鲁棒',
    };

    let headerHtml = '<tr><th>排名</th><th>模型</th><th>协议</th><th>总分</th><th>评定</th><th>基础语言</th><th>技术能力</th><th>高级认知</th><th>实用能力</th><th>边界鲁棒</th><th>耗时</th><th>Tokens</th></tr>';

    let rowsHtml = sorted.map((r, i) => {
      const score = r.total_score || 0;
      const sc = score >= 85 ? 'var(--green)' : score >= 70 ? 'var(--blue)' : score >= 50 ? 'var(--yellow)' : 'var(--red)';
      const verdictLabels = { excellent: '优秀', good: '良好', average: '一般', poor: '较差' };
      const rankClass = i === 0 ? 'eval-rank-1' : i === 1 ? 'eval-rank-2' : i === 2 ? 'eval-rank-3' : '';
      const dims = Object.entries(r.dimension_scores || {});

      return `<tr>
        <td><span class="eval-rank ${rankClass}">#${i + 1}</span></td>
        <td><strong>${escapeHtml(r.model)}</strong></td>
        <td>${escapeHtml(r.protocol || 'N/A')}</td>
        <td><span class="score" style="color:${sc}">${score.toFixed(1)}</span></td>
        <td><span class="verdict" style="background:${sc}22;color:${sc}">${verdictLabels[r.verdict] || r.verdict}</span></td>
        ${dims.map(([key, val]) => `<td style="color:${val >= 85 ? 'var(--green)' : val >= 70 ? 'var(--blue)' : val >= 50 ? 'var(--yellow)' : 'var(--red)'}">${val.toFixed(1)}</td>`).join('')}
        <td>${r.duration_seconds || 0}s</td>
        <td>${r.total_tokens || 0}</td>
      </tr>`;
    }).join('');

    div.innerHTML = `
      <div class="eval-result-head">
        <div class="eval-result-head-top">
          <div>
            <div class="report-name">测评对比摘要</div>
            <div class="report-meta"><span>${results.length} 个模型</span></div>
          </div>
        </div>
      </div>
      <div class="report-body">
        <table class="eval-comparison-table">
          <thead>${headerHtml}</thead>
          <tbody>${rowsHtml}</tbody>
        </table>
      </div>`;
    c.insertBefore(div, c.firstChild);
  }

  // ============ Init ============
  function init() {
    initHeroTabs();
    initProviders();
    initEvalProviders();
    initKeyToggle();
    initEvalKeyToggle();
    initUrlAutocomplete();
    initHistory();
    initModelActions();
    initModes();
    initStart();
    initEvalDimensions();
    initEvalDifficulty();
    initEvalStart();
    initProtocolTabs();
    initEvalModelActions();
    initEvalProtocolTabs();

    // 绑定输入事件（确保元素存在）
    const baseUrlInput = $('base_url');
    const apiKeyInput = $('api_key');
    const evalBaseUrlInput = $('eval-base_url');
    const evalApiKeyInput = $('eval-api_key');
    const evalModelsInput = $('eval-models-input');

    if (baseUrlInput) baseUrlInput.addEventListener('input', onInputChange);
    if (apiKeyInput) apiKeyInput.addEventListener('input', onInputChange);
    if (evalBaseUrlInput) evalBaseUrlInput.addEventListener('input', onEvalInputChange);
    if (evalApiKeyInput) evalApiKeyInput.addEventListener('input', onEvalInputChange);
    if (evalModelsInput) evalModelsInput.addEventListener('input', updateEvalSummary);
  }

  // ============ Navbar Scroll Effect ============
function initNavbarScroll() {
  const navbar = document.querySelector('.navbar');
  const backToTop = $('back-to-top');
  if (!navbar) return;

  let ticking = false;
  function onScroll() {
    const currentScroll = window.pageYOffset;

    // 使用 CSS 类控制导航栏样式
    if (currentScroll > 50) {
      navbar.classList.add('scrolled');
    } else {
      navbar.classList.remove('scrolled');
    }

    // 控制回到顶部按钮显示/隐藏
    if (backToTop) {
      backToTop.style.display = currentScroll > 300 ? 'block' : 'none';
    }

    ticking = false;
  }

  window.addEventListener('scroll', () => {
    if (!ticking) {
      window.requestAnimationFrame(onScroll);
      ticking = true;
    }
  }, { passive: true });
}

// ============ Particle Animation ============
function initParticles() {
  const container = $('hero-particles');
  if (!container) return;
  
  // 创建粒子元素
  for (let i = 0; i < 20; i++) {
    const particle = document.createElement('div');
    particle.className = 'particle';
    particle.style.cssText = `
      position: absolute;
      width: ${Math.random() * 4 + 2}px;
      height: ${Math.random() * 4 + 2}px;
      background: ${Math.random() > 0.5 ? 'var(--blue)' : 'var(--purple)'};
      border-radius: 50%;
      left: ${Math.random() * 100}%;
      top: ${Math.random() * 100}%;
      opacity: ${Math.random() * 0.5 + 0.2};
      animation: particleFloat ${Math.random() * 10 + 10}s ease-in-out infinite;
      animation-delay: ${Math.random() * 5}s;
      pointer-events: none;
    `;
    container.appendChild(particle);
  }
}

// ============ Mouse Tracking Glow ============
function initMouseTracking() {
  // 检测是否为触摸设备，触摸设备不启用鼠标追踪
  if (window.matchMedia('(hover: none) and (pointer: coarse)').matches) return;

  const cards = document.querySelectorAll('.feature-card, .step-card');
  cards.forEach(card => {
    card.addEventListener('mousemove', (e) => {
      const rect = card.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      card.style.setProperty('--mouse-x', x + '%');
      card.style.setProperty('--mouse-y', y + '%');
    });
  });
}

// ============ Scroll Progress Bar ============
function initScrollProgress() {
  const bar = $('scroll-progress');
  if (!bar) return;

  let ticking = false;
  function update() {
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    const scrollHeight = document.documentElement.scrollHeight - window.innerHeight;
    const progress = scrollHeight > 0 ? (scrollTop / scrollHeight) * 100 : 0;
    bar.style.width = progress + '%';
    ticking = false;
  }

  window.addEventListener('scroll', () => {
    if (!ticking) {
      window.requestAnimationFrame(update);
      ticking = true;
    }
  }, { passive: true });

  update();
}

// ============ Touch Optimization ============
function initTouchOptimizations() {
  // 为所有可点击元素添加触摸反馈
  const touchElements = document.querySelectorAll('.btn-primary, .btn-secondary, .btn-ghost, .btn-cta-primary, .btn-cta-secondary, .nav-tab, .tab, .model-card, .mode-card');
  touchElements.forEach(el => {
    el.addEventListener('touchstart', () => {}, { passive: true });
  });

  // 阻止双击缩放
  let lastTouchEnd = 0;
  document.addEventListener('touchend', (e) => {
    const now = Date.now();
    if (now - lastTouchEnd <= 300) {
      e.preventDefault();
    }
    lastTouchEnd = now;
  }, { passive: false });
}

// ============ Intersection Observer for Animations ============
function initScrollAnimations() {
  const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
  };
  
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = '1';
        entry.target.style.transform = 'translateY(0)';
      }
    });
  }, observerOptions);
  
  // 观察所有卡片元素
  document.querySelectorAll('.feature-card, .step-card').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
    observer.observe(el);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  // 星空背景由 starfield.js 独立初始化，无需在此重复调用
  init();
  initNavbarScroll();
  initParticles();
  initScrollAnimations();
  initMouseTracking();
  initScrollProgress();
  initTouchOptimizations();

  // v2.8: 检测 URL hash，支持从测评页"返回检测"直接跳转到配置区
  if (location.hash === '#config') {
    // 清除 hash，避免刷新时重复滚动
    history.replaceState(null, '', location.pathname);
    // 延迟调用确保所有初始化完成
    setTimeout(() => {
      if (typeof window.scrollToConfig === 'function') {
        window.scrollToConfig();
      }
    }, 300);
  }
});
})();
