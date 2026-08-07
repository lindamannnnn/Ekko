/* =====================================================================
 *  Ekko 课评系统 · 新手引导（v2，数据驱动）
 *  ---------------------------------------------------------------------
 *  设计目标：
 *    1. 视觉融入暗色玻璃主题（不再用浅蓝气泡）
 *    2. 流程基于"建班 → 加学生 → 让 AI 写出第一篇课评"
 *    3. 步骤配置集中在一处（TOURS 数组），后续改文案/调顺序只改数据
 *    4. 副作用严格管理：exit() 会断开所有观察器/高亮，防误触发
 *
 *  路由贯穿用 URL 参数：?tour=1&step=N
 *    不强制依赖任何 DOM 哨兵 id（tour-mask 仅在欢迎遮罩处需要）
 *
 *  进入方式：
 *    - 首次登录（localStorage 无 'crs_onboarded'）+ 未在流程中 → 欢迎遮罩
 *    - 导航栏「💡 新手引导」「?」按钮 → 重新打开欢迎遮罩
 *    - URL 带 tour=1&step=N → 直接进入对应步骤气泡
 * =================================================================== */

(function () {
  'use strict';

  const TOUR_KEY = 'crs_onboarded';

  // ===================================================================
  //  步骤配置（数据驱动：改文案/调顺序只改这里）
  // ===================================================================
  //  每个 step:
  //    match(pathname) -> 是否命中
  //    title, body(Markdown lite: **bold**)
  //    highlight(sel)   给页面中该选择器的元素加脉冲边框（可选）
  //    nextHref(captures) → 用户点"下一步"时跳的链接
  //    actions: [{label, primary, href/onClick}]    自定义操作按钮（可选）
  //    finish: true     表示是完成态
  //
  const TOURS = [
    /* ───────── ① 创建第一个班级 ───────── */
    {
      step: 1,
      match: (p) => p === '/classes/new',
      title: '① 创建第一个班级',
      body: '填一个**班级名称**（如「三年级 2 班」），选好班级类型，然后点页面下方的「**创建班级**」按钮。',
      scrollTo: 'form',
      nextHref: () => null,  // 提交后由 routes 重定向回 /classes/<id>/detail?tour=1&step=2
      autoAdvanceDelay: 0,
    },

    /* ───────── ② 添加学生（detail 页 + add 页两个分支） ───────── */
    {
      step: 2,
      match: (p) => /^\/classes\/[^/]+\/detail$/.test(p),
      title: '② 添加学生',
      body: '点页面右上角的「**添加学生**」按钮，会跳到添加页面。',
      highlight: '.detail-actions a',
      scrollTo: '.detail-actions',
    },
    {
      step: 2,
      match: (p) => /^\/classes\/[^/]+\/students\/add$/.test(p),
      title: '② 添加学生',
      body: '一行填一个学生（**姓名**必填，**性别**下拉选，**昵称**选填）。一次加多个就点「**+ 添加一行**」，填完点右下角「**确认添加全部**」，会自动回到班级页继续下一步。',
      highlight: '.form-card',
      scrollTo: '.form-card',
    },

    /* ───────── ③ 在 detail 页让 AI 写出第一篇课评（聚合 3 子步） ───────── */
    {
      step: 3,
      match: (p) => /^\/classes\/[^/]+\/detail$/.test(p),
      title: '③ 让 AI 写出你的第一篇课评',
      isMulti: true,  // 用 subStep 切换子步骤文案
      subs: [
        {
          subtitle: '❶ 告诉 AI 这节课学了什么',
          body: '在中间区域**粘贴或上传本节课内容**（教案/课件都可以），然后点「**💾 保存课程内容**」。',
          highlight: '#course-content-input',
          scrollTo: '#course-content-input',
        },
        {
          subtitle: '❷ 写一句本节课的一句话评语',
          body: '在「**✨ 教师对本节课的一句话评语**」框里，写一句你对本节课的总结（例如「今天节奏很好，难点在 xxx」）。这句话会**一起保存到课评里**，**必填**，每节都建议写。',
          highlight: '#teacher-comment',
          scrollTo: '#teacher-comment',
        },
        {
          subtitle: '❸ 上传优秀历史课评（选填·推荐）',
          body: '看右侧「**上传优秀历史课评**」区域：把你以前写得满意的一份课评传上来（点区域选文件，或点「✏️ 或粘贴文本」直接粘进去再点「保存」）。上传后，**AI 生成时会优先模仿这个风格**，更贴合你班学生；不传就用通用模板。**整班只传一次、全班共用**，强烈推荐。',
          highlight: '#excellent-review-area',
          scrollTo: '#excellent-review-area',
        },
        {
          subtitle: '❹ 选标签 + 一键 AI 生成课评',
          body: '可选：选几个**快捷标签**（让评语更贴合学生表现），然后点中栏的「**🤖 AI 生成课评**」按钮。AI 会为当前学生写一份课评。',
          highlight: '#btn-ai-generate',
          scrollTo: '#btn-ai-generate',
        },
        {
          subtitle: '❺ 保存 → 写出你的第一篇课评',
          body: '确认「**✨ 教师一句话评语**」（必填）和下方 AI 课评都已填好，然后点「**💾 保存评语**」。**恭喜，你写出了第一篇课评！**',
          highlight: '#btn-save-review',
          scrollTo: '#btn-save-review',
        },
      ],
    },
  ];

  const DONE_VIEW = {
    step: 4,
    isDone: true,
    title: '🎉 太棒了，你写出了第一篇课评！',
    body: '完整流程你已经走通：建班级 → 加学生 → 粘贴/上传课程内容 → 写一句话评语（必填） → 上传优秀历史课评（选填·推荐） → AI 生成 → 保存。以后在班级列表页随时点导航栏「**💡 新手引导**」按钮可以重看本引导。',
  };

  // ===================================================================
  //  状态
  // ===================================================================
  const state = {
    step: 1,           // 当前步骤
    subStep: 0,        // 多子步骤里的子步骤序号
    finished: false,   // 是否已显示完成态
    observers: [],     // MutationObserver 列表（exit 时统一断开）
    highlighted: [],   // 被加高亮的元素（exit 时移除 class）
    _lastHighlight: null,  // 最近一次高亮的元素（resize/重定位用）
  };

  // 庆祝卡（"🎉 太棒了第一篇"）只弹一次，跨会话持久化。
  // autoSave 在每次 input 都会触发；同一台设备上反复触发都不应重复弹。
  // 用 localStorage 持久化：仅当用户点 💡 重新开启引导时清除（让他能再看一次）。
  const CELEBRATED_KEY = 'ekko_tour_celebrated';
  function hasSeenCelebration() { try { return !!localStorage.getItem(CELEBRATED_KEY); } catch (e) { return false; } }
  function markCelebrated()    { try { localStorage.setItem(CELEBRATED_KEY, '1'); } catch (e) {} }
  function resetCelebrated()   { try { localStorage.removeItem(CELEBRATED_KEY); } catch (e) {} }

  // ===================================================================
  //  工具
  // ===================================================================
  function qs() { return new URLSearchParams(location.search); }
  function getStep()  { return parseInt(qs().get('step') || '1', 10); }
  function inTour()  { return qs().get('tour') === '1'; }

  function findStep() {
    const p = location.pathname;
    const s = getStep();
    for (const t of TOURS) if (t.step === s && t.match(p)) return t;
    return null;
  }

  // Markdown lite：只支持 **bold** 和换行
  function renderMd(s) {
    return (s || '')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');
  }

  // ===================================================================
  //  样式（一次性注入；融入暗色玻璃主题）
  // ===================================================================
  function injectStyles() {
    if (document.getElementById('tour-styles')) return;
    const css = `
      /* 欢迎遮罩 */
      .tour-mask {
        position: fixed; inset: 0;
        background: rgba(2, 6, 23, 0.72);
        backdrop-filter: blur(8px);
        z-index: 9000;
        display: none;
        align-items: center; justify-content: center;
        padding: 24px;
        animation: tourFadeIn .2s ease;
      }
      .tour-mask.show { display: flex; }
      @keyframes tourFadeIn { from { opacity: 0; } to { opacity: 1; } }

      /* 气泡卡（玻璃风） */
      .tour-card {
        background: linear-gradient(135deg, rgba(15,23,42,.95), rgba(30,41,59,.95));
        border: 1px solid var(--border-strong, rgba(59,130,246,.35));
        border-radius: var(--radius, 16px);
        padding: 18px 20px;
        max-width: 460px;
        width: 100%;
        box-shadow: 0 20px 60px rgba(0,0,0,.55), 0 0 0 1px rgba(59,130,246,.18) inset;
        color: var(--text, #f1f5f9);
        font-size: 14px;
        line-height: 1.7;
        animation: tourSlideUp .28s ease;
      }
      @keyframes tourSlideUp {
        from { transform: translateY(10px); opacity: 0; }
        to   { transform: translateY(0);    opacity: 1; }
      }

      .tour-welcome-card { max-width: 520px; }

      .tour-tag {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 3px 10px;
        background: linear-gradient(135deg, var(--accent, #3b82f6), var(--cyan, #06b6d4));
        color: #fff;
        font-size: 11px; font-weight: 600;
        border-radius: 20px;
        letter-spacing: .4px;
        margin-bottom: 10px;
      }
      .tour-welcome-card .tour-title,
      .tour-card .tour-title {
        font-size: 16px; font-weight: 700;
        color: var(--text, #f1f5f9);
        margin: 0 0 6px;
      }
      .tour-welcome-card .tour-sub {
        font-size: 13px; color: var(--text-2, #94a3b8);
        margin: 0 0 18px;
      }
      .tour-card .tour-body { color: var(--text-2, #94a3b8); margin: 0 0 14px; }
      .tour-card .tour-body strong { color: var(--text, #f1f5f9); font-weight: 600; }

      .tour-subtitle {
        font-size: 13px;
        color: var(--accent, #3b82f6);
        font-weight: 600;
        margin-bottom: 4px;
        letter-spacing: .3px;
      }

      .tour-progress {
        font-size: 11px;
        color: var(--text-3, #64748b);
        margin-left: 8px;
        padding: 2px 8px;
        background: rgba(148,163,184,.10);
        border-radius: 10px;
      }

      .tour-steps-list {
        list-style: none; padding: 0; margin: 12px 0 22px;
        display: grid; gap: 10px;
      }
      .tour-steps-list li {
        display: flex; align-items: flex-start; gap: 10px;
        padding: 10px 12px;
        background: rgba(59,130,246,.06);
        border: 1px solid rgba(59,130,246,.20);
        border-radius: 10px;
        font-size: 13px;
        color: var(--text, #f1f5f9);
      }
      .tour-steps-list li .step-dot {
        flex-shrink: 0;
        width: 20px; height: 20px;
        background: var(--accent, #3b82f6);
        color: #fff;
        border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 11px; font-weight: 700;
      }
      .tour-steps-list li .step-text strong { color: var(--text, #f1f5f9); }

      .tour-actions {
        display: flex; gap: 8px; align-items: center;
        margin-top: 14px;
        flex-wrap: wrap;
      }
      .tour-actions .tour-skip {
        margin-left: auto;
        background: transparent;
        border: 0;
        color: var(--text-3, #64748b);
        font-size: 13px;
        cursor: pointer;
        padding: 6px 4px;
        text-decoration: none;
      }
      .tour-actions .tour-skip:hover { color: var(--text-2, #94a3b8); }

      /* 步内按钮 */
      .tour-btn {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 8px 16px;
        border-radius: 10px;
        font-size: 13px; font-weight: 600;
        cursor: pointer;
        text-decoration: none;
        transition: all .2s;
        border: 1px solid transparent;
      }
      .tour-btn-primary {
        background: linear-gradient(135deg, var(--accent, #3b82f6), var(--cyan, #06b6d4));
        color: #fff;
        box-shadow: 0 4px 12px rgba(59,130,246,.3);
      }
      .tour-btn-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(59,130,246,.4); }
      .tour-btn-ghost {
        background: transparent;
        color: var(--text-2, #94a3b8);
        border-color: rgba(148,163,184,.20);
      }
      .tour-btn-ghost:hover { color: var(--text, #f1f5f9); border-color: rgba(148,163,184,.40); }

      /* 脉冲高亮（让被指引的元素发光 + 穿透遮罩可点） */
      .tour-highlight {
        position: relative !important;
        z-index: 9100 !important;
        pointer-events: auto !important;
        border-radius: 12px;
        box-shadow: 0 0 0 3px rgba(59,130,246,.50),
                    0 0 24px rgba(59,130,246,.40) !important;
        animation: tourPulse 1.6s ease-in-out infinite;
      }
      @keyframes tourPulse {
        0%, 100% { box-shadow: 0 0 0 3px rgba(59,130,246,.50), 0 0 24px rgba(59,130,246,.40); }
        50%      { box-shadow: 0 0 0 5px rgba(59,130,246,.65), 0 0 36px rgba(59,130,246,.60); }
      }

      /* 容器：气泡卡由 JS 定位到目标按钮旁边，绝不遮挡目标 */
      .tour-bubble-host {
        position: fixed;
        left: 0; top: 0;
        z-index: 9200;
        max-width: 340px;
        width: 340px;
        transition: top .22s ease, left .22s ease;
        animation: tourSlideUp .28s ease;
      }
      @media (max-width: 768px) {
        .tour-bubble-host {
          left: 16px !important; right: 16px !important;
          bottom: 16px !important; top: auto !important;
          width: auto; max-width: none; transform: none;
        }
      }

      /* 完成态 */
      .tour-done-card {
        border-color: rgba(16,185,129,.45);
        background: linear-gradient(135deg, rgba(6,78,59,.40), rgba(15,23,42,.95));
      }
      .tour-done-tag { background: linear-gradient(135deg, var(--success, #10b981), var(--cyan, #06b6d4)); }
      .tour-done-title { color: var(--success, #10b981) !important; }
    `;
    const style = document.createElement('style');
    style.id = 'tour-styles';
    style.textContent = css;
    document.head.appendChild(style);
  }

  // ===================================================================
  //  高亮（脉冲边框 + 穿透遮罩 + 位置避让）
  // ===================================================================
  function applyHighlight(sel) {
    if (!sel) return;
    const el = document.querySelector(sel);
    if (!el) return;
    el.classList.add('tour-highlight');
    state.highlighted.push(el);

    // 让高亮元素穿透遮罩（z-index 高过 mask 9000 → 9100，pointer-events 显式开启）
    const prev = {
      position: el.style.position,
      zIndex: el.style.zIndex,
      pointerEvents: el.style.pointerEvents,
    };
    el.style.position = 'relative';
    el.style.zIndex = '9100';
    el.style.pointerEvents = 'auto';
    el.dataset._tourPrev = JSON.stringify(prev);

    state._lastHighlight = el;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    // 等滚动+渲染完成后再贴着按钮定位（避免页面滚动导致位置漂移）
    setTimeout(() => positionBubbleNear(el), 320);
  }

  // 数值夹紧到 [min, max]
  function clamp(v, min, max) { return Math.min(Math.max(v, min), max); }

  // 把气泡卡定位到目标元素旁边，绝不遮挡目标
  //   优先级：右侧 → 左侧 → 下方 → 上方；最后整体夹紧到视窗内
  //   对高元素（form 等）取垂直中心，避免气泡贴在远离文字处的边角
  function positionBubbleNear(targetEl) {
    const host = document.getElementById('tour-bubble');
    if (!host || !targetEl) return;
    if (window.innerWidth <= 768) return;   // 移动端由 CSS 固定在底部
    const r = targetEl.getBoundingClientRect();
    const margin = 14;
    const bw = host.offsetWidth || 320;
    const bh = host.offsetHeight || 160;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    // 高元素（>320px）取垂直中心做吸附点；矮元素直接贴顶
    const anchorY = r.height > 320
      ? Math.max(r.top, r.top + r.height / 2 - bh / 2)
      : r.top;

    let left, top;
    if (r.right + margin + bw <= vw) {            // 优先放右侧
      left = r.right + margin; top = anchorY;
    } else if (r.left - margin - bw >= 0) {        // 其次放左侧
      left = r.left - margin - bw; top = anchorY;
    } else if (r.bottom + margin + bh <= vh) {     // 再放下方
      left = clamp(r.left, margin, vw - bw - margin);
      top = r.bottom + margin;
    } else {                                       // 最后放上方
      left = clamp(r.left, margin, vw - bw - margin);
      top = Math.max(margin, r.top - margin - bh);
    }
    host.style.left = clamp(left, margin, vw - bw - margin) + 'px';
    host.style.top  = clamp(top, margin, vh - bh - margin) + 'px';
  }

  function clearHighlights() {
    state.highlighted.forEach((el) => {
      el.classList.remove('tour-highlight');
      try {
        const prev = el.dataset._tourPrev && JSON.parse(el.dataset._tourPrev);
        if (prev) {
          el.style.position = prev.position || '';
          el.style.zIndex = prev.zIndex || '';
          el.style.pointerEvents = prev.pointerEvents || '';
        } else {
          el.style.position = '';
          el.style.zIndex = '';
          el.style.pointerEvents = '';
        }
        delete el.dataset._tourPrev;
      } catch (e) {}
    });
    state.highlighted = [];
  }

  // ===================================================================
  //  DOM 构造
  // ===================================================================
  function ensureMask() {
    let mask = document.getElementById('tour-mask');
    if (mask) return mask;
    mask = document.createElement('div');
    mask.className = 'tour-mask';
    mask.id = 'tour-mask';
    mask.addEventListener('click', (e) => { if (e.target === mask) window.Tour.exit(); });
    document.body.appendChild(mask);
    return mask;
  }

  function ensureBubbleHost() {
    let host = document.getElementById('tour-bubble');
    if (host) {
      host.classList.remove('tour-bubble-host');
      host.classList.add('tour-bubble-host');
      return host;
    }
    host = document.createElement('div');
    host.id = 'tour-bubble';
    host.className = 'tour-bubble-host';
    document.body.appendChild(host);
    return host;
  }

  function renderWelcome() {
    const mask = ensureMask();
    const html = `
      <div class="tour-card tour-welcome-card">
        <span class="tour-tag">📚 新手引导 · 3 步</span>
        <h2 class="tour-title">欢迎使用 Ekko 课评系统</h2>
        <p class="tour-sub">跟着引导 3 分钟，写出你的第一篇 AI 课评。</p>
        <ol class="tour-steps-list">
          <li><span class="step-dot">1</span><span class="step-text"><strong>创建班级</strong>：填一个班级名（如「三年级 2 班」）</span></li>
          <li><span class="step-dot">2</span><span class="step-text"><strong>添加学生</strong>：一行填一个学生（姓名/性别/昵称）</span></li>
          <li><span class="step-dot">3</span><span class="step-text"><strong>让 AI 写课评</strong>：粘贴课程内容 → 写一句话评语(必填) → 上传优秀历史课评(选填·推荐) → AI 生成 → 保存</span></li>
        </ol>
        <div class="tour-actions">
          <a href="javascript:void(0)" class="tour-skip" onclick="Tour.exit()">跳过</a>
          <a class="tour-btn tour-btn-primary" href="/classes/new?tour=1&step=1">开启引导 →</a>
        </div>
      </div>
    `;
    mask.innerHTML = html;
    mask.classList.add('show');
    // 隐藏内嵌的 bubble host
    const host = document.getElementById('tour-bubble');
    if (host) host.innerHTML = '';
  }

  function renderStep(t) {
    // 隐藏欢迎遮罩
    const mask = document.getElementById('tour-mask');
    if (mask) mask.classList.remove('show');

    const host = ensureBubbleHost();
    clearHighlights();

    const totalSubs = t.isMulti ? t.subs.length : 1;
    const sub = t.isMulti ? t.subs[state.subStep] : null;

    // 标题（多子步时用 subStep.subtitle，否则用 t.title）
    const subtitle = sub ? sub.subtitle : '';
    const body = sub ? sub.body : t.body;
    const highlightSel = sub ? sub.highlight : t.highlight;
    const scrollTo = sub ? sub.scrollTo : t.scrollTo;

    // 进度标识
    const progress = t.isMulti
      ? `<span class="tour-progress">${state.subStep + 1} / ${totalSubs}</span>`
      : '';

    // 操作按钮
    let actionsHtml = '';
    if (t.isMulti) {
      const prevBtn = state.subStep > 0
        ? `<button class="tour-btn tour-btn-ghost" onclick="Tour.prev()">← 上一步</button>`
        : '';
      const isLast = state.subStep === totalSubs - 1;
      const nextBtn = isLast
        ? `<button class="tour-btn tour-btn-primary" onclick="Tour.finish()">完成引导 🎉</button>`
        : `<button class="tour-btn tour-btn-primary" onclick="Tour.next()">下一步 →</button>`;
      actionsHtml = `<div class="tour-actions">${prevBtn}${nextBtn}<a href="javascript:void(0)" class="tour-skip" onclick="Tour.exit()">跳过</a></div>`;
    } else if (t.step === 1) {
      // 步骤 1：表单提交自己走，exit 即可
      actionsHtml = `<div class="tour-actions"><a href="javascript:void(0)" class="tour-skip" onclick="Tour.exit()">跳过</a></div>`;
    } else {
      actionsHtml = `<div class="tour-actions"><a href="javascript:void(0)" class="tour-skip" onclick="Tour.exit()">跳过</a></div>`;
    }

    host.innerHTML = `
      <div class="tour-card">
        <span class="tour-tag">📚 新手引导${progress}</span>
        ${subtitle ? `<div class="tour-subtitle">${renderMd(subtitle)}</div>` : ''}
        <h3 class="tour-title">${renderMd(t.title)}</h3>
        <div class="tour-body">${renderMd(body)}</div>
        ${actionsHtml}
      </div>
    `;

    // 高亮目标元素
    if (highlightSel) {
      applyHighlight(highlightSel);
    } else if (scrollTo) {
      const el = document.querySelector(scrollTo);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  function renderDone() {
    const mask = ensureMask();
    const html = `
      <div class="tour-card tour-done-card tour-welcome-card">
        <span class="tour-tag tour-done-tag">🎉 完成</span>
        <h2 class="tour-title tour-done-title">${DONE_VIEW.title}</h2>
        <div class="tour-body">${renderMd(DONE_VIEW.body)}</div>
        <div class="tour-actions">
          <a class="tour-btn tour-btn-primary" href="/classes">进入我的班级</a>
          <a href="javascript:void(0)" class="tour-skip" onclick="Tour.exit()">关闭</a>
        </div>
      </div>
    `;
    mask.innerHTML = html;
    mask.classList.add('show');
    const host = document.getElementById('tour-bubble');
    if (host) host.innerHTML = '';
  }

  // ===================================================================
  //  副作用清理（exit 时统一处理）
  // ===================================================================
  function cleanup() {
    clearHighlights();
    state.observers.forEach((o) => { try { o.disconnect(); } catch (e) {} });
    state.observers = [];
    const mask = document.getElementById('tour-mask');
    if (mask) { mask.classList.remove('show'); mask.innerHTML = ''; }
    const host = document.getElementById('tour-bubble');
    if (host) host.innerHTML = '';
  }

  function clearTourParam() {
    try {
      const url = new URL(location.href);
      url.searchParams.delete('tour');
      url.searchParams.delete('step');
      history.replaceState({}, '', url.pathname + (url.search ? url.search : '') + url.hash);
    } catch (e) {}
  }

  function markDone() { try { localStorage.setItem(TOUR_KEY, '1'); } catch (e) {} }
  function isOnboarded() { try { return !!localStorage.getItem(TOUR_KEY); } catch (e) { return false; } }
  function resetOnboarded() { try { localStorage.removeItem(TOUR_KEY); } catch (e) {} }

  // ===================================================================
  //  暴露全局 API
  // ===================================================================
  window.Tour = {
    /* 开始引导（从欢迎遮罩跳到 step1） */
    start() {
      resetOnboarded();
      resetCelebrated();   // 重新走一遍引导时，可以再看一次庆祝卡
      renderWelcome();
    },
    /* 重新打开欢迎遮罩（导航栏 ?/💡 按钮调用） */
    open() { resetCelebrated(); renderWelcome(); },
    /* 退出（标记完成 + 清理副作用 + 清 URL 参数） */
    exit() {
      markDone();
      cleanup();
      clearTourParam();
    },
    /* 子步骤推进（仅 step 3 多子步流程用） */
    next() {
      const t = findStep();
      if (!t || !t.isMulti) return;
      const total = t.subs.length;
      if (state.subStep < total - 1) {
        state.subStep++;
        renderStep(t);
      }
    },
    prev() {
      const t = findStep();
      if (!t || !t.isMulti) return;
      if (state.subStep > 0) {
        state.subStep--;
        renderStep(t);
      }
    },
    /* 静默退出（用户主动点"完成引导"或"跳过"——只清理，不弹庆祝卡） */
    finish() {
      markDone();
      cleanup();
      clearTourParam();
    },
    /* 真·完成（系统检测到课评已保存——弹"太棒了第一篇"庆祝卡，但只弹一次） */
    complete() {
      markDone();
      cleanup();
      clearTourParam();
      if (hasSeenCelebration()) return;  // 已弹过，本次只清理（autoSave 多次触发不重复弹）
      markCelebrated();
      renderDone();
      // 8 秒后自动关掉完成卡
      setTimeout(() => {
        const mask = document.getElementById('tour-mask');
        if (mask) mask.classList.remove('show');
      }, 8000);
    },
    /* 调试用 */
    _state: state,
    _tours: TOURS,
  };

  // ===================================================================
  //  启动
  // ===================================================================
  document.addEventListener('DOMContentLoaded', function () {
    injectStyles();

    // 窗口尺寸变化时，重新把气泡贴到目标旁边
    let _rzT;
    window.addEventListener('resize', function () {
      clearTimeout(_rzT);
      _rzT = setTimeout(function () {
        if (state._lastHighlight) positionBubbleNear(state._lastHighlight);
      }, 120);
    });

    if (isOnboarded() && !inTour()) return;        // 已完成 + 不在流程中 → 啥也不做

    if (inTour()) {
      // 已在引导流程中
      const t = findStep();
      if (t) {
        state.step = getStep();
        state.subStep = 0;
        renderStep(t);
      }
      return;
    }

    // 未完成 + 已登录 → 自动欢迎遮罩
    // 判定已登录：导航栏有 .teacher-name 或 .topnav 的 logout 链接
    const loggedIn = !!document.querySelector('.teacher-name')
                  || !!document.querySelector('.topnav a.logout');
    if (loggedIn) renderWelcome();
  });
})();
