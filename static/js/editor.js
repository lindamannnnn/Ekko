/* 课评编辑器前端逻辑（桌面优先）。
 * 核心：4 路 Promise 池并发生成，status 作为断点续跑唯一真相。
 */
(function () {
  'use strict';
  const CONF = window.CLASS_CONF || {};
  const CLS = CONF.class_id, LSN = CONF.lesson_id;
  const api = {
    status: `/reviews/${CLS}/${LSN}/status`,
    generate: (rid) => `/reviews/${rid}/generate`,
    save: (rid) => `/reviews/${rid}/save`,
    confirm: (rid) => `/reviews/${rid}/confirm`,
    leave: (rid) => `/reviews/${rid}/leave`,
    revert: (rid) => `/reviews/${rid}/revert`,
    dedup: `/reviews/${CLS}/${LSN}/dedup`,
  };
  const state = {}; // rid -> {status, content, score, student_id, student_name}

  const $ = (sel, el) => (el || document).querySelector(sel);
  const $$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));

  function statusBadge(s) {
    const map = {
      pending: ['待生成', 'badge-pending'],
      generating: ['生成中…', 'badge-generating'],
      draft: ['可编辑', 'badge-draft'],
      confirmed: ['已确认', 'badge-confirmed'],
      leave: ['请假', 'badge-leave'],
      failed: ['失败', 'badge-failed'],
    };
    const [txt, cls] = map[s] || [s, 'badge-pending'];
    return `<span class="badge ${cls}">${txt}</span>`;
  }

  async function loadStatus() {
    const r = await fetch(api.status);
    const data = await r.json();
    data.forEach((d) => {
      state[d.id] = { ...(state[d.id] || {}), ...d, student_id: d.student_id,
                      perf_tags: d.perf_tags || [], perf_note: d.perf_note || '',
                      _name: (CONF.students && CONF.students[d.student_id]) || '' };
    });
    render();
    updateProgress();
  }

  function escapeHtml(s) {
    return (s || '').replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  function render() {
    const wrap = $('#review-list');
    wrap.innerHTML = '';
    const tags = CONF.quick_tags || [];
    Object.values(state).forEach((rev) => {
      const score = rev.score || {};
      const scoreHtml = rev.score
        ? `<div class="score">质量分 <b>${score.score}</b>/100
             ${score.checks && !score.checks.no_comparison ? '<span class="warn">⚠ 疑似横向比较</span>' : ''}
             ${score.flags && score.flags.length ? '<span class="warn">⚠ 含数字请核对</span>' : ''}</div>`
        : '';
      const errHtml = rev.status === 'failed' && rev.error_msg
        ? `<div class="err">${rev.error_msg}</div>` : '';
      const sel = rev.perf_tags || [];
      const chips = tags.length
        ? `<div class="rc-tags">${tags.map((t) =>
            `<span class="tag chip ${sel.includes(t) ? 'on' : ''}" data-tag="${escapeHtml(t)}">${escapeHtml(t)}</span>`
          ).join('')}</div>`
        : '';
      const card = document.createElement('div');
      card.className = 'review-card';
      card.dataset.rid = rev.id;
      card.innerHTML = `
        <div class="rc-head">
          <span class="rc-name">${escapeHtml(rev._name || '')}</span>
          ${statusBadge(rev.status)}
        </div>
        ${scoreHtml}
        ${errHtml}
        ${chips}
        <textarea class="rc-note" data-rid="${rev.id}" placeholder="本节课一句话评语（选填）">${escapeHtml(rev.perf_note || '')}</textarea>
        <textarea class="rc-text" data-rid="${rev.id}">${escapeHtml(rev.content || '')}</textarea>
        <div class="rc-actions">
          <button class="btn-mini" data-act="generate" data-rid="${rev.id}">生成</button>
          <button class="btn-mini" data-act="confirm" data-rid="${rev.id}">确认</button>
          <button class="btn-mini" data-act="leave" data-rid="${rev.id}">请假</button>
          <button class="btn-mini" data-act="revert" data-rid="${rev.id}">还原原稿</button>
          <button class="btn-mini" data-act="copy" data-rid="${rev.id}">复制</button>
        </div>`;
      wrap.appendChild(card);
    });
    bindTextareas();
  }

  let saveTimer = {};
  function bindTextareas() {
    $$('.rc-text').forEach((ta) => {
      ta.addEventListener('input', () => {
        const rid = ta.dataset.rid;
        if (saveTimer[rid]) clearTimeout(saveTimer[rid]);
        saveTimer[rid] = setTimeout(() => save(rid, ta.value), 800);
      });
    });
    $$('.rc-note').forEach((ta) => {
      ta.addEventListener('input', () => {
        const rid = ta.dataset.rid;
        if (saveTimer['n' + rid]) clearTimeout(saveTimer['n' + rid]);
        saveTimer['n' + rid] = setTimeout(() => saveNote(rid, ta.value), 800);
      });
    });
  }

  async function saveNote(rid, note) {
    await fetch(api.save(rid), {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `teacher_comment=${encodeURIComponent(note)}`,
    });
  }

  async function toggleTag(rid, tag) {
    const rev = state[rid];
    if (!rev) return;
    rev.perf_tags = rev.perf_tags || [];
    const i = rev.perf_tags.indexOf(tag);
    if (i >= 0) rev.perf_tags.splice(i, 1);
    else rev.perf_tags.push(tag);
    // 更新 UI 高亮
    const card = $(`.review-card[data-rid="${rid}"]`);
    if (card) {
      card.querySelectorAll('.rc-tags .chip').forEach((c) => {
        c.classList.toggle('on', rev.perf_tags.includes(c.dataset.tag));
      });
    }
    await fetch(api.save(rid), {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `perf_tags=${encodeURIComponent(JSON.stringify(rev.perf_tags))}`,
    });
  }

  async function save(rid, content) {
    await fetch(api.save(rid), {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `content=${encodeURIComponent(content)}`,
    });
  }

  async function generateOne(rid) {
    const card = $(`.review-card[data-rid="${rid}"]`);
    const ta = card && $('.rc-text', card);
    if (ta) ta.disabled = true;
    try {
      const r = await fetch(api.generate(rid), { method: 'POST' });
      const data = await r.json();
      if (data.ok) {
        state[rid] = { ...state[rid], status: data.status, content: data.content || state[rid].content, score: data.score };
      } else {
        state[rid] = { ...state[rid], status: data.status || 'failed', error_msg: data.error };
        if (data.error) flash(data.error);
      }
    } catch (e) {
      state[rid] = { ...state[rid], status: 'failed', error_msg: String(e) };
    } finally {
      if (ta) ta.disabled = false;
      render();
      updateProgress();
    }
  }

  // 4 路 Promise 池
  function pool(items, worker, concurrency = 4) {
    let i = 0;
    const runners = Array.from({ length: Math.min(concurrency, items.length) }, async () => {
      while (i < items.length) {
        const item = items[i++];
        await worker(item);
      }
    });
    return Promise.all(runners);
  }

  async function generateAll() {
    const targets = Object.values(state)
      .filter((r) => r.status === 'pending' || r.status === 'failed' || r.status === 'draft')
      .map((r) => r.id);
    if (!targets.length) return;
    setBusy(true, `正在生成 ${targets.length} 份（并发 4）…`);
    await pool(targets, generateOne, 4);
    setBusy(false, '生成完成');
  }

  async function act(action, rid) {
    if (action === 'generate') return generateOne(rid);
    const map = {
      confirm: api.confirm, leave: api.leave, revert: api.revert,
    };
    const r = await fetch(map[action](rid), { method: 'POST' });
    const data = await r.json();
    if (data.ok) {
      state[rid] = { ...state[rid], status: data.status, content: data.content || state[rid].content };
      render(); updateProgress();
    }
  }

  async function copy(rid) {
    const txt = state[rid] && state[rid].content;
    if (txt) { try { await navigator.clipboard.writeText(txt); flash('已复制'); } catch (e) {} }
  }

  async function runDedup() {
    setBusy(true, '横向去重中…');
    await fetch(api.dedup, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: 'threshold=0.35' });
    await loadStatus();
    setBusy(false, '去重完成');
  }

  function updateProgress() {
    const all = Object.values(state);
    const done = all.filter((r) => r.status === 'confirmed' || r.status === 'draft').length;
    $('#progress').textContent = `已完成 ${done} / ${all.length}`;
  }

  function setBusy(on, msg) {
    const b = $('#gen-all');
    if (b) b.disabled = on;
    $('#busy').textContent = msg || '';
  }

  let flashTimer;
  function flash(msg) {
    const f = $('#flash'); f.textContent = msg; f.style.opacity = '1';
    clearTimeout(flashTimer);
    flashTimer = setTimeout(() => (f.style.opacity = '0'), 1500);
  }

  // 事件委托
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-act]');
    if (!btn) return;
    const act = btn.dataset.act, rid = btn.dataset.rid;
    if (act === 'copy') return copy(rid);
    doAct(act, rid);
  });

  async function doAct(action, rid) {
    if (!action) return;
    if (action === 'generate') return generateOne(rid);
    const map = {
      confirm: api.confirm, leave: api.leave, revert: api.revert,
    };
    if (!map[action]) return;
    const r = await fetch(map[action](rid), { method: 'POST' });
    const data = await r.json();
    if (data.ok) {
      state[rid] = { ...(state[rid] || {}), status: data.status, content: data.content || (state[rid] && state[rid].content) };
      render(); updateProgress();
    }
  }
  const genBtn = document.getElementById('gen-all');
  if (genBtn) genBtn.addEventListener('click', generateAll);
  const dedupBtn = document.getElementById('dedup-btn');
  if (dedupBtn) dedupBtn.addEventListener('click', runDedup);

  // 每张卡片内的快捷标签：点选 = 选中/取消，落库到该生 review.perf_tags
  document.addEventListener('click', (e) => {
    const chip = e.target.closest('.rc-tags .chip');
    if (!chip) return;
    const card = chip.closest('.review-card');
    if (card) toggleTag(card.dataset.rid, chip.dataset.tag);
  });

  loadStatus();
})();
