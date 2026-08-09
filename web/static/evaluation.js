/* ============================================================
   Model Detective — Evaluation Page JavaScript v5.1
   模型测评页面专用脚本
   修复：SSE流程、协议分类、事件处理、结果渲染
   ============================================================ */

(function() {
  'use strict';

  // ============ Starfield Canvas Animation ============
  function initStarfield() {
    const canvas = document.getElementById('star-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let width = window.innerWidth;
    let height = window.innerHeight;

    canvas.width = width;
    canvas.height = height;

    const STAR_COUNT = 300;
    const stars = [];

    for (let i = 0; i < STAR_COUNT; i++) {
      stars.push({
        x: Math.random() * width,
        y: Math.random() * height,
        radius: Math.random() * 1.5 + 0.5,
        alpha: Math.random(),
        speed: Math.random() * 0.02 + 0.005,
        twinkleSpeed: Math.random() * 0.03 + 0.01,
        color: Math.random() > 0.7 ? '#a8c5ff' :
               Math.random() > 0.5 ? '#ffd4a3' : '#ffffff'
      });
    }

    let shootingStars = [];

    function createShootingStar() {
      if (Math.random() > 0.99 && shootingStars.length < 3) {
        shootingStars.push({
          x: Math.random() * width,
          y: Math.random() * height * 0.3,
          length: Math.random() * 100 + 60,
          speed: Math.random() * 15 + 10,
          angle: Math.PI / 4 + Math.random() * 0.2,
          alpha: 1
        });
      }
    }

    function drawNebula() {
      const grad1 = ctx.createRadialGradient(width * 0.2, height * 0.8, 0, width * 0.2, height * 0.8, width * 0.6);
      grad1.addColorStop(0, 'rgba(107, 70, 193, 0.4)');
      grad1.addColorStop(0.4, 'rgba(107, 70, 193, 0.1)');
      grad1.addColorStop(1, 'transparent');
      ctx.fillStyle = grad1;
      ctx.fillRect(0, 0, width, height);

      const grad2 = ctx.createRadialGradient(width * 0.8, height * 0.2, 0, width * 0.8, height * 0.2, width * 0.5);
      grad2.addColorStop(0, 'rgba(59, 130, 246, 0.35)');
      grad2.addColorStop(0.4, 'rgba(59, 130, 246, 0.08)');
      grad2.addColorStop(1, 'transparent');
      ctx.fillStyle = grad2;
      ctx.fillRect(0, 0, width, height);

      const grad3 = ctx.createRadialGradient(width * 0.5, 0, 0, width * 0.5, 0, width * 0.4);
      grad3.addColorStop(0, 'rgba(6, 182, 212, 0.2)');
      grad3.addColorStop(1, 'transparent');
      ctx.fillStyle = grad3;
      ctx.fillRect(0, 0, width, height);
    }

    function drawStars() {
      stars.forEach(star => {
        star.alpha += star.twinkleSpeed;
        const brightness = Math.sin(star.alpha) * 0.5 + 0.5;

        const glow = ctx.createRadialGradient(star.x, star.y, 0, star.x, star.y, star.radius * 4);
        glow.addColorStop(0, star.color + Math.floor(brightness * 40).toString(16).padStart(2, '0'));
        glow.addColorStop(1, 'transparent');
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(star.x, star.y, star.radius * 4, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = star.color + Math.floor(brightness * 255).toString(16).padStart(2, '0');
        ctx.beginPath();
        ctx.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
        ctx.fill();
      });
    }

    function drawShootingStars() {
      shootingStars.forEach((star, i) => {
        star.x += Math.cos(star.angle) * star.speed;
        star.y += Math.sin(star.angle) * star.speed;
        star.alpha -= 0.015;

        if (star.alpha <= 0) {
          shootingStars.splice(i, 1);
          return;
        }

        const grad = ctx.createLinearGradient(
          star.x, star.y,
          star.x - Math.cos(star.angle) * star.length,
          star.y - Math.sin(star.angle) * star.length
        );
        grad.addColorStop(0, `rgba(255, 255, 255, ${star.alpha})`);
        grad.addColorStop(0.5, `rgba(168, 197, 255, ${star.alpha * 0.5})`);
        grad.addColorStop(1, 'transparent');

        ctx.strokeStyle = grad;
        ctx.lineWidth = 3;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(star.x, star.y);
        ctx.lineTo(
          star.x - Math.cos(star.angle) * star.length,
          star.y - Math.sin(star.angle) * star.length
        );
        ctx.stroke();

        ctx.fillStyle = `rgba(255, 255, 255, ${star.alpha})`;
        ctx.beginPath();
        ctx.arc(star.x, star.y, 2, 0, Math.PI * 2);
        ctx.fill();
      });
    }

    function animate() {
      ctx.clearRect(0, 0, width, height);
      drawNebula();
      drawStars();
      createShootingStar();
      drawShootingStars();
      requestAnimationFrame(animate);
    }

    window.addEventListener('resize', () => {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width;
      canvas.height = height;
      stars.forEach(star => {
        if (star.x > width) star.x = Math.random() * width;
        if (star.y > height) star.y = Math.random() * height;
      });
    });

    animate();
  }

  // ============ Utils ============
  const $ = id => document.getElementById(id);
  const $$ = sel => document.querySelectorAll(sel);

  function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
  }

  function show(el) {
    if (el) {
      el.hidden = false;
      el.classList.add('revealed');
    }
  }
  function hide(el) {
    if (el) {
      el.hidden = true;
      el.classList.remove('revealed');
    }
  }

  // ============ Provider Presets ============
  const PROVIDERS = [
    { name: 'Anthropic Official', url: 'https://api.anthropic.com/v1' },
    { name: 'OpenAI Official', url: 'https://api.openai.com/v1' },
    { name: 'Gemini Official', url: 'https://generativelanguage.googleapis.com/v1beta' },
    { name: 'OpenRouter', url: 'https://openrouter.ai/api/v1' },
    { name: 'DeepSeek Official', url: 'https://api.deepseek.com/v1' },
    { name: 'Moonshot (Kimi)', url: 'https://api.moonshot.cn/v1' },
    { name: 'SiliconFlow', url: 'https://api.siliconflow.cn/v1' },
    { name: 'Groq', url: 'https://api.groq.com/openai/v1' },
    { name: 'Together AI', url: 'https://api.together.xyz/v1' },
    { name: 'Fireworks AI', url: 'https://api.fireworks.ai/inference/v1' },
    { name: 'Mistral AI', url: 'https://api.mistral.ai/v1' },
    { name: 'Cerebras', url: 'https://api.cerebras.ai/v1' },
    { name: 'SambaNova', url: 'https://api.sambanova.ai/v1' },
    { name: 'Novita AI', url: 'https://api.novita.ai/v3/openai' },
    { name: 'Zhipu (GLM)', url: 'https://open.bigmodel.cn/api/paas/v4' },
  ];

  // ============ State ============
  const state = {
    baseUrl: '',
    apiKey: '',
    models: [],           // [{id, protocol}]
    selectedModels: new Set(),
    dimensions: new Set(['basic_language', 'technical', 'advanced_cognition', 'practical', 'boundary']),
    difficulty: 'quick',
    probeStatus: null,
    isRunning: false,
    completeHandled: false,
  };

  // ============ Scroll to Config ============
  window.scrollToEvalConfig = function() {
    const configSection = $('eval-config');
    if (configSection) {
      configSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setTimeout(() => {
        const baseUrlInput = $('eval-base_url');
        if (baseUrlInput) baseUrlInput.focus();
      }, 600);
    }
  };

  // ============ Navbar Scroll Effect ============
  function initNavbarScroll() {
    const navbar = document.querySelector('.navbar');
    const backToTop = $('back-to-top');
    if (!navbar) return;

    let ticking = false;
    function onScroll() {
      const currentScroll = window.pageYOffset;

      if (currentScroll > 50) {
        navbar.classList.add('scrolled');
      } else {
        navbar.classList.remove('scrolled');
      }

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

  // ============ Mouse Tracking Glow ============
  function initMouseTracking() {
    if (window.matchMedia('(hover: none) and (pointer: coarse)').matches) return;

    const cards = document.querySelectorAll('.dimension-card');
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

  // ============ Particle Animation ============
  function initParticles() {
    const container = $('hero-particles');
    if (!container) return;

    const particleCount = window.matchMedia('(pointer: coarse)').matches ? 15 : 20;

    for (let i = 0; i < particleCount; i++) {
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

  // ============ Touch Optimization ============
  function initTouchOptimizations() {
    const touchElements = document.querySelectorAll('.btn-primary, .btn-secondary, .btn-ghost, .nav-tab, .tab, .eval-difficulty-option, .eval-dim-checkbox');
    touchElements.forEach(el => {
      el.addEventListener('touchstart', () => {}, { passive: true });
    });

    let lastTouchEnd = 0;
    document.addEventListener('touchend', (e) => {
      const now = Date.now();
      if (now - lastTouchEnd <= 300) {
        e.preventDefault();
      }
      lastTouchEnd = now;
    }, { passive: false });
  }

  // ============ Scroll Animations ============
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

    document.querySelectorAll('.dimension-card').forEach(el => {
      el.style.opacity = '0';
      el.style.transform = 'translateY(20px)';
      el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
      observer.observe(el);
    });
  }

  // ============ Provider Dropdown ============
  function initProviderDropdown() {
    const btn = $('eval-provider-btn');
    const dropdown = $('eval-provider-dropdown');
    const search = $('eval-provider-search');
    const list = $('eval-provider-list');
    const input = $('eval-base_url');

    if (!btn || !dropdown) return;

    function renderProviders(filter = '') {
      const filtered = PROVIDERS.filter(p =>
        p.name.toLowerCase().includes(filter.toLowerCase()) ||
        p.url.toLowerCase().includes(filter.toLowerCase())
      );

      list.innerHTML = filtered.map(p => `
        <div class="dropdown-item" data-url="${escapeHtml(p.url)}">
          <span class="di-name">${escapeHtml(p.name)}</span>
          <span class="di-url">${escapeHtml(p.url)}</span>
        </div>
      `).join('');

      list.querySelectorAll('.dropdown-item').forEach(item => {
        item.addEventListener('click', () => {
          input.value = item.dataset.url;
          dropdown.hidden = true;
          input.focus();
          onInputChange();
        });
      });
    }

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (dropdown.hidden) {
        show(dropdown);
        renderProviders('');
        search.focus();
      } else {
        hide(dropdown);
      }
    });

    search.addEventListener('input', (e) => {
      renderProviders(e.target.value);
    });

    document.addEventListener('click', (e) => {
      if (!dropdown.contains(e.target) && e.target !== btn) {
        hide(dropdown);
      }
    });
  }

  // ============ API Key Toggle ============
  function initApiKeyToggle() {
    const toggle = $('eval-toggle-key');
    const input = $('eval-api_key');
    if (!toggle || !input) return;

    const eye = toggle.querySelector('.icon-eye');
    const eyeOff = toggle.querySelector('.icon-eye-off');

    toggle.addEventListener('click', () => {
      const isPassword = input.type === 'password';
      input.type = isPassword ? 'text' : 'password';
      if (eye) eye.style.display = isPassword ? 'none' : 'block';
      if (eyeOff) eyeOff.style.display = isPassword ? 'block' : 'none';
    });
  }

  // ============ Debounce ============
  function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }

  // ============ Guess Protocol ============
  function guessProto(m) {
    const s = m.toLowerCase();
    if (s.startsWith('claude') || s.includes('claude')) return 'anthropic';
    if (s.startsWith('gemini') || s.includes('gemini')) return 'gemini';
    return 'openai';
  }

  // ============ Input Change → Probe ============
  const debouncedProbe = debounce(probeApi, 700);

  function onInputChange() {
    const baseUrl = $('eval-base_url').value.trim();
    const apiKey = $('eval-api_key').value.trim();
    state.baseUrl = baseUrl;
    state.apiKey = apiKey;

    const ready = baseUrl.startsWith('http') && apiKey.length >= 8;
    if (ready) {
      debouncedProbe();
    } else {
      hide($('eval-step-2'));
      hide($('eval-step-3'));
      hide($('eval-step-4'));
    }
  }

  // ============ Probe API ============
  async function probeApi() {
    const baseUrl = $('eval-base_url').value.trim();
    const apiKey = $('eval-api_key').value.trim();
    const pill = $('eval-probe-pill');

    if (!baseUrl || !apiKey) {
      if (pill) {
        pill.innerHTML = '<span class="status-dot error"></span> 请填写 Base URL 和 API Key';
        show(pill);
      }
      return;
    }

    state.baseUrl = baseUrl;
    state.apiKey = apiKey;

    if (pill) {
      pill.className = 'probe-status info';
      pill.innerHTML = '<span class="spinner"></span> 正在探测可用模型...';
      show(pill);
    }

    try {
      const resp = await fetch('/api/probe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ base_url: baseUrl, api_key: apiKey })
      });

      const data = await resp.json();

      // 认证失败
      if (!data.ok && data.auth_ok === false) {
        pill.className = 'probe-status err';
        pill.textContent = '认证失败 — 请检查 API Key';
        return;
      }

      // 模型端点不可用
      if (!data.models_endpoint_supported) {
        pill.className = 'probe-status warn';
        pill.textContent = data.error || '未找到 /v1/models 端点 — 你可以手动输入模型名。';
        show($('eval-step-2'));
        renderModelGrid();
        return;
      }

      // 使用后端返回的 effective_base_url
      if (data.effective_base_url) {
        state.baseUrl = data.effective_base_url;
        $('eval-base_url').value = data.effective_base_url;
      }

      // 使用 by_protocol 数据正确分类模型协议
      const byProto = data.by_protocol || {};
      const protoMap = {};
      for (const [p, ms] of Object.entries(byProto)) {
        for (const m of ms) protoMap[m] = p;
      }

      const allModels = data.all_models || [];
      state.models = allModels.map(m => ({
        id: m,
        protocol: protoMap[m] || guessProto(m)
      }));

      state.probeStatus = 'success';

      const a = byProto.anthropic?.length || 0;
      const o = byProto.openai?.length || 0;
      const g = byProto.gemini?.length || 0;
      pill.className = 'probe-status ok';
      pill.innerHTML = `发现 <b>${data.raw_count}</b> 个模型 (Anthropic ${a} · OpenAI ${o} · Gemini ${g})`;

      // 显示后续步骤
      show($('eval-step-2'));
      show($('eval-step-3'));
      show($('eval-step-4'));
      renderModelGrid();
      updateLaunchSummary();

      // 滚动到步骤2
      setTimeout(() => {
        if ($('eval-step-2')) {
          $('eval-step-2').scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }, 300);

    } catch (err) {
      state.probeStatus = 'error';
      if (pill) {
        pill.className = 'probe-status warn';
        pill.textContent = '探测失败: ' + err.message + ' — 你可以手动输入模型名。';
      }
      show($('eval-step-2'));
      renderModelGrid();
    }
  }

  // ============ Render Model Grid ============
  function renderModelGrid(filter = 'all') {
    const grid = $('eval-model-grid');
    if (!grid) return;

    let models = state.models;
    if (filter !== 'all') {
      models = models.filter(m => m.protocol === filter);
    }

    if (models.length === 0) {
      grid.innerHTML = '<div class="empty-state">暂无可用模型，可手动添加</div>';
      return;
    }

    grid.innerHTML = models.map(m => {
      const isSelected = state.selectedModels.has(m.id);
      const p = m.protocol || 'openai';
      return `<div class="model-chip ${isSelected ? 'selected' : ''}" data-model-id="${escapeHtml(m.id)}" tabindex="0" role="button" aria-pressed="${isSelected}">
        <span class="model-dot ${p}"></span>
        <span class="model-name">${escapeHtml(m.id)}</span>
        <span class="model-check">✓</span>
      </div>`;
    }).join('');

    grid.querySelectorAll('.model-chip').forEach(chip => {
      const toggle = () => {
        const modelId = chip.dataset.modelId;
        if (state.selectedModels.has(modelId)) {
          state.selectedModels.delete(modelId);
          chip.classList.remove('selected');
          chip.setAttribute('aria-pressed', 'false');
        } else {
          state.selectedModels.add(modelId);
          chip.classList.add('selected');
          chip.setAttribute('aria-pressed', 'true');
        }
        updateLaunchSummary();
      };
      chip.addEventListener('click', toggle);
      chip.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
      });
    });
  }

  // ============ Protocol Tabs ============
  function initProtocolTabs() {
    const tabs = document.querySelectorAll('[data-eval-proto]');
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        renderModelGrid(tab.dataset.evalProto);
      });
    });
  }

  // ============ Dimension Checkboxes ============
  function initDimensionCheckboxes() {
    const container = $('eval-dimensions');
    if (!container) return;

    container.querySelectorAll('.eval-dim-checkbox').forEach(label => {
      const checkbox = label.querySelector('input[type="checkbox"]');
      const dim = label.dataset.dim;

      label.addEventListener('click', (e) => {
        if (e.target !== checkbox) {
          checkbox.checked = !checkbox.checked;
        }

        if (checkbox.checked) {
          state.dimensions.add(dim);
          label.classList.add('checked');
        } else {
          state.dimensions.delete(dim);
          label.classList.remove('checked');
        }
        updateLaunchSummary();
      });
    });
  }

  // ============ Difficulty Selection ============
  function initDifficultySelection() {
    const container = $('eval-difficulty');
    if (!container) return;

    container.querySelectorAll('.eval-difficulty-option').forEach(option => {
      option.addEventListener('click', () => {
        container.querySelectorAll('.eval-difficulty-option').forEach(o => o.classList.remove('active'));
        option.classList.add('active');
        state.difficulty = option.dataset.diff;
        updateLaunchSummary();
      });
    });
  }

  // ============ Update Launch Summary ============
  function updateLaunchSummary() {
    const summary = $('eval-launch-summary');
    if (!summary) return;

    // 合并手动输入的模型
    const manualText = $('eval-models-input')?.value || '';
    const manualModels = manualText.split(/[,\n\r]+/)
      .map(m => m.trim())
      .filter(m => m.length > 0 && m.length <= 200);

    const allSelected = new Set([...state.selectedModels, ...manualModels]);
    const modelCount = allSelected.size;
    const dimCount = state.dimensions.size;
    const diffText = { quick: '精简版 (20题)', standard: '标准版 (40题)', full: '完整版 (100题)' }[state.difficulty];
    const timePerModel = state.difficulty === 'quick' ? 2 : state.difficulty === 'standard' ? 5 : 12;
    const totalTime = modelCount * timePerModel;
    const timeStr = totalTime < 60 ? `${totalTime}分钟` : `${Math.floor(totalTime / 60)}小时${totalTime % 60}分钟`;

    if (modelCount === 0) {
      summary.innerHTML = '<div class="summary-row" style="color: var(--txt-3);"><span>⚠️ 请先选择或输入要测评的模型</span></div>';
      hide($('eval-step-4'));
      return;
    }

    show($('eval-step-4'));

    summary.innerHTML = `
      <div class="summary-row"><span>待测评模型</span><strong>${modelCount} 个</strong></div>
      <div class="summary-row"><span>测评维度</span><strong>${dimCount} 个</strong></div>
      <div class="summary-row"><span>测评模式</span><strong>${escapeHtml(diffText)}</strong></div>
      <div class="summary-row"><span>预计耗时</span><strong>~${timeStr}</strong></div>
      <div class="summary-models">${[...allSelected].map(m => `<span class="summary-tag">${escapeHtml(m)}</span>`).join('')}</div>
    `;
  }

  // ============ Start Evaluation ============
  async function startEvaluation() {
    // 合并手动输入的模型
    const manualText = $('eval-models-input')?.value || '';
    const manualModels = manualText.split(/[,\n\r]+/)
      .map(m => m.trim())
      .filter(m => m.length > 0 && m.length <= 200);

    const allSelected = new Set([...state.selectedModels, ...manualModels]);
    const models = [...allSelected];

    if (models.length === 0) {
      alert('请至少选择或输入一个模型');
      return;
    }

    if (state.dimensions.size === 0) {
      alert('请至少选择一个测评维度');
      return;
    }

    // 使用输入框的最新值（可能被探测更新过）
    const baseUrl = $('eval-base_url').value.trim();
    const apiKey = $('eval-api_key').value.trim();
    state.baseUrl = baseUrl;
    state.apiKey = apiKey;

    state.isRunning = true;
    state.completeHandled = false;
    const btn = $('eval-start-btn');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '启动中...';
    }

    // 隐藏配置步骤，显示结果
    hide($('eval-step-1'));
    hide($('eval-step-2'));
    hide($('eval-step-3'));
    hide($('eval-step-4'));
    show($('eval-step-5'));
    $('eval-step-5').scrollIntoView({ behavior: 'smooth', block: 'start' });

    const progressContainer = $('eval-progress-container');
    const resultsContainer = $('eval-results-container');

    if (resultsContainer) resultsContainer.innerHTML = '';

    // 初始化进度条
    if (progressContainer) {
      progressContainer.innerHTML = models.map((m, i) => `
        <div class="prog-item" id="eval-prog-${i}">
          <div class="prog-head">
            <span class="prog-name">${escapeHtml(m)}</span>
            <span class="prog-badge pending">等待</span>
          </div>
          <div class="prog-bar"><div class="prog-fill" style="width:0"></div></div>
        </div>
      `).join('');
    }

    try {
      const resp = await fetch('/api/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: state.baseUrl,
          api_key: state.apiKey,
          models: models,
          dimensions: Array.from(state.dimensions),
          difficulty: state.difficulty
        })
      });

      const data = await resp.json();

      if (!data.ok) {
        if (progressContainer) {
          progressContainer.innerHTML = `<div class="probe-status err">启动失败: ${escapeHtml(data.error || '')}</div>`;
        }
        if (btn) { btn.disabled = false; btn.textContent = '开始测评'; }
        show($('eval-step-1'));
        show($('eval-step-2'));
        show($('eval-step-3'));
        show($('eval-step-4'));
        hide($('eval-step-5'));
        return;
      }

      // 使用 EventSource 轮询 SSE
      pollEvalStatus(data.job_id, models);

    } catch (err) {
      if (progressContainer) {
        progressContainer.innerHTML = `<div class="probe-status err">网络错误: ${escapeHtml(err.message)}</div>`;
      }
      if (btn) { btn.disabled = false; btn.textContent = '开始测评'; }
      show($('eval-step-1'));
      show($('eval-step-2'));
      show($('eval-step-3'));
      show($('eval-step-4'));
      hide($('eval-step-5'));
    }
  }

  // ============ SSE Status Polling ============
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
          if (!state.completeHandled) handleEvalComplete(data);
          return;
        }
        const evts = (data.progress || []).slice(lastIdx);
        lastIdx = (data.progress || []).length;
        evts.forEach(e => handleEvalProgress(e, models));
      } catch (e) { /* keep polling */ }
    }, 1000);
  }

  // ============ Progress Handler ============
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
      // 题目级进度（current/total/score）
      // 可选：更新进度条
    }
  }

  // ============ Complete Handler ============
  function handleEvalComplete(data) {
    if (state.completeHandled) return;
    state.completeHandled = true;

    const btn = $('eval-start-btn');
    if (btn) { btn.disabled = false; btn.textContent = '开始测评'; }
    state.isRunning = false;

    const resultsContainer = $('eval-results-container');
    if (!resultsContainer) return;

    resultsContainer.innerHTML = '';

    if (data.error) {
      resultsContainer.innerHTML = `<div class="probe-status err">测评失败: ${escapeHtml(data.error)}</div>`;
      return;
    }

    if (data.results && data.results.length > 0) {
      for (const r of data.results) {
        renderEvalResult(r);
      }
      if (data.results.length > 1) {
        renderEvalComparison(data.results);
      }
    } else {
      resultsContainer.innerHTML = '<div class="probe-status warn">未获取到测评结果</div>';
    }

    // 添加操作按钮
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

    resultsContainer.appendChild(actions);
  }

  // ============ Render Evaluation Result ============
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
          <span class="report-verdict" style="background:${verdictBg};color:${sc}">${verdictLabels[r.verdict] || r.verdict}</span>
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

  // ============ Render Comparison ============
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

  // ============ Auto Probe on Input ============
  function initAutoProbe() {
    const baseUrlInput = $('eval-base_url');
    const apiKeyInput = $('eval-api_key');
    const modelsInput = $('eval-models-input');

    if (baseUrlInput) baseUrlInput.addEventListener('input', onInputChange);
    if (apiKeyInput) apiKeyInput.addEventListener('input', onInputChange);
    if (modelsInput) modelsInput.addEventListener('input', updateLaunchSummary);
  }

  // ============ Initialization ============
  document.addEventListener('DOMContentLoaded', () => {
    initStarfield();
    initNavbarScroll();
    initParticles();
    initMouseTracking();
    initScrollProgress();
    initScrollAnimations();
    initTouchOptimizations();
    initProviderDropdown();
    initApiKeyToggle();
    initProtocolTabs();
    initDimensionCheckboxes();
    initDifficultySelection();
    initAutoProbe();

    // Start button
    const startBtn = $('eval-start-btn');
    if (startBtn) {
      startBtn.addEventListener('click', startEvaluation);
    }

    // Initialize launch summary
    updateLaunchSummary();
  });

})();
