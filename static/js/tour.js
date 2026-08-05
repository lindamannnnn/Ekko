/* 新手引导控制器（独立文件，base 页与编辑器页共用）。
 * 流程用 URL 参数贯穿：?tour=1&step=N
 *   step1 /classes/new        → 建班级
 *   step2 /classes/<id>/detail → 加学生（气泡引导点「+ 添加学生」）
 *         /classes/<id>/students/add → 保存学生（提交后自动回 detail?step=3）
 *   step3 /classes/<id>/detail → 建课次
 *         /classes/<id>/new    → 创建课次（提交后自动回 detail?step=4）
 *   step4 /classes/<id>/detail → 进编辑器
 *         /classes/<id>/<lid>/editor → 一键生成 + 确认 → 完成
 * 气泡始终挂在当前页面顶部，用户跟着气泡点页面真实按钮即可，自动跳下一步。
 */
(function () {
  'use strict';
  var KEY = 'crs_onboarded';

  function inTour() { return new URLSearchParams(location.search).get('tour') === '1'; }
  function getStep() { return parseInt(new URLSearchParams(location.search).get('step') || '1', 10); }
  function onBase() { return !!document.querySelector('.topnav'); }
  function isLoggedIn() { return !!document.querySelector('.teacher-name') || !!document.querySelector('.topnav .logout'); }
  function firstLesson() {
    var el = document.getElementById('tour-first-lesson');
    return el ? el.dataset.id : null;
  }

  // 注入气泡样式（两页通用）
  (function injectStyle() {
    var css =
      '.tour-bubble{background:#eef4ff;border:1px solid #c7d8ff;border-left:4px solid #2f6fed;' +
      'border-radius:12px;padding:14px 16px;margin-bottom:16px;box-shadow:0 4px 16px rgba(47,111,237,.08);}' +
      '.tour-bubble .tb-step{display:inline-block;background:#2f6fed;color:#fff;font-size:11px;' +
      'padding:2px 9px;border-radius:10px;margin-bottom:8px;letter-spacing:.5px;}' +
      '.tour-bubble .tb-title{font-size:16px;font-weight:700;color:#1f2933;margin-bottom:6px;}' +
      '.tour-bubble .tb-body{font-size:14px;line-height:1.7;color:#374151;margin-bottom:12px;}' +
      '.tour-bubble .tb-actions{display:flex;gap:12px;align-items:center;}' +
      '.tour-bubble .tb-skip{font-size:13px;color:#9aa3b2;text-decoration:none;}' +
      '.tour-bubble .tb-skip:hover{color:#6b7280;}' +
      '.tour-done{background:#ecfdf3;border:1px solid #a7f3d0;border-left:4px solid #1f9d57;' +
      'border-radius:12px;padding:16px 18px;margin-bottom:16px;}' +
      '.tour-done .tb-title{color:#1f9d57;}';
    var s = document.createElement('style');
    s.textContent = css;
    document.head.appendChild(s);
  })();

  /* ===== 欢迎弹窗 ===== */
  function showWelcome() {
    var mask = document.getElementById('tour-mask');
    var box = document.getElementById('tour-box');
    if (!mask || !box) return;
    box.innerHTML =
      '<h2>👋 欢迎使用 Ekko课评系统</h2>' +
      '<p>这是一个给老师用的课评工作台。接下来我会<b>一步一步带着你</b>走完' +
      '「建班级 → 加学生 → 传课件 → AI 写课评 → 确认写出第一篇课评」的完整流程，' +
      '跟着做就行，不用自己找入口。</p>' +
      '<div style="display:flex;gap:10px;justify-content:space-between;align-items:center">' +
      '<a href="javascript:void(0)" onclick="Tour.exit()" style="font-size:13px;color:#9aa3b2;text-decoration:none;">跳过引导</a>' +
      '<a class="btn" href="/classes/new?tour=1&step=1">开始引导 →</a>' +
      '</div>';
    mask.classList.add('show');
  }

  /* ===== 根据当前页面 + step 返回气泡配置 ===== */
  function bubble() {
    var step = getStep();
    var p = location.pathname;
    var m;
    if (p === '/classes/new' && step === 1) {
      return {
        title: '① 新建你的第一个班级',
        body: '在这里填写<b>班级名称</b>（如「三年级 2 班」）和<b>班级类型</b>，然后点页面下方的【<b>创建班级</b>】按钮。',
        fix: [], next: null,
      };
    }
    if ((m = p.match(/^\/classes\/([^/]+)\/detail$/))) {
      var cid = m[1];
      if (step === 2) {
        return {
          title: '② 把学生加进班级',
          body: '点下方的【<b>+ 添加学生</b>】按钮，把学生姓名批量加进来。',
          fix: [['a[href$="/students/add"]', '?tour=1&step=2']],
          nextLabel: '去添加学生 →', nextHref: '/classes/' + cid + '/students/add?tour=1&step=2',
        };
      }
      if (step === 3) {
        return {
          title: '③ 上传课程内容创建课次',
          body: '在中间区域把课程内容粘贴到文本框，或点【📎 上传文件】。系统会自动转成 Markdown，转换完成后点【确认创建课次】即可。',
          fix: [['#course-content-input', '?tour=1&step=3']],
          nextLabel: '创建课次 →', nextHref: '/classes/' + cid + '/detail?tour=1&step=3',
        };
      }
      if (step === 4) {
        var card = document.querySelector('a[href*="/editor"]');
        var href = card ? card.getAttribute('href') : null;
        var full = href
          ? (href + (href.indexOf('?') >= 0 ? '&' : '?') + 'tour=1&step=4')
          : ('/reviews/' + cid + '/' + (firstLesson() || '') + '/editor?tour=1&step=4');
        return {
          title: '④ 进入 AI 课评编辑器',
          body: '点下方的【<b>🤖 AI 课评编辑器</b>】卡片，进入为每个学生写课评的页面。',
          fix: [['a[href*="/editor"]', '?tour=1&step=4']],
          nextLabel: '进入课评编辑器 →', nextHref: full,
        };
      }
    }
    if ((m = p.match(/^\/classes\/([^/]+)\/students\/add$/))) {
      return {
        title: '② 添加学生',
        body: '把学生姓名按行或逗号分隔贴进文本框，然后点【<b>保存学生</b>】。保存后会自动回到班级页，进入下一步。',
        fix: [], next: null,
      };
    }
    if ((m = p.match(/^\/classes\/([^/]+)\/new$/))) {
      return {
        title: '③ 新建课次',
        body: '填写<b>课次标题</b>、上课日期、知识点，可把课件正文粘贴进文本框，然后点【<b>创建课次</b>】。',
        fix: [], next: null,
      };
    }
    if ((m = p.match(/^\/reviews\/([^/]+)\/([^/]+)\/editor$/))) {
      return {
        title: '⑤ 让 AI 写出第一个课评',
        body: '点顶部【<b>一键生成全部</b>】，AI 会为每个学生自动写一段评语。生成完成后，再逐份点每张卡片上的【<b>确认</b>】按钮，写出你的第一个课评。',
        editor: true, fix: [], next: null,
      };
    }
    return null;
  }

  function hostFor() {
    if (onBase()) { var c = document.querySelector('.container'); if (c) return c; }
    var tb = document.querySelector('.topbar');
    return tb ? tb : document.body;
  }
  function insertBubble(el) {
    var host = hostFor();
    if (!host) { document.body.appendChild(el); return; }
    if (host === document.body) { document.body.insertBefore(el, document.body.firstChild); return; }
    if (host.classList && host.classList.contains('topbar')) { host.parentNode.insertBefore(el, host.nextSibling); return; }
    host.insertBefore(el, host.firstChild);
  }

  function mountBubble() {
    var b = bubble();
    if (!b) return;
    (b.fix || []).forEach(function (pair) {
      var sel = pair[0], qs = pair[1];
      document.querySelectorAll(sel).forEach(function (a) {
        var h = a.getAttribute('href');
        if (h && h.indexOf('tour=1') < 0) {
          a.setAttribute('href', h + (h.indexOf('?') >= 0 ? '&' : '?') + qs);
        }
      });
    });
    var el = document.getElementById('tour-bubble');
    if (!el) { el = document.createElement('div'); el.id = 'tour-bubble'; }
    el.className = '';
    el.innerHTML =
      '<div class="tour-bubble">' +
        '<span class="tb-step">新手引导</span>' +
        '<div class="tb-title">' + b.title + '</div>' +
        '<div class="tb-body">' + b.body + '</div>' +
        '<div class="tb-actions">' +
          (b.nextHref ? '<a class="btn" href="' + b.nextHref + '">' + b.nextLabel + '</a>' : '') +
          '<a href="javascript:void(0)" class="tb-skip" onclick="Tour.exit()">跳过引导</a>' +
        '</div>' +
      '</div>';
    insertBubble(el);
    if (b.editor) bindEditorTour();
  }

  function bindEditorTour() {
    var genBtn = document.getElementById('gen-all');
    if (genBtn) {
      genBtn.addEventListener('click', function () {
        var t = setInterval(function () {
          if (document.querySelector('.badge-draft') || document.querySelector('.badge-confirmed')) {
            clearInterval(t);
            var body = document.querySelector('#tour-bubble .tb-body');
            if (body) body.innerHTML = '✅ 课评已生成！现在逐份点每张卡片上的【<b>确认</b>】按钮，写出你的第一个课评。';
          }
        }, 1000);
      });
    }
    var list = document.getElementById('review-list');
    if (list) {
      var obs = new MutationObserver(function () {
        if (document.querySelector('.badge-confirmed')) finishTour();
      });
      obs.observe(list, { childList: true, subtree: true, characterData: true });
    }
  }

  function markDone() { try { localStorage.setItem(KEY, '1'); } catch (e) {} }
  function clearTourParam() {
    var url = new URL(location.href);
    url.searchParams.delete('tour');
    url.searchParams.delete('step');
    history.replaceState({}, '', url.pathname + url.search);
  }
  function finishTour() {
    var el = document.getElementById('tour-bubble');
    if (el) {
      el.innerHTML =
        '<div class="tour-done">' +
          '<span class="tb-step" style="background:#1f9d57">完成</span>' +
          '<div class="tb-title">🎉 太棒了，你写出了第一个课评！</div>' +
          '<div class="tb-body">完整流程你已经走通了。以后随时点左上角「?」可以再看一遍引导。</div>' +
          '<div class="tb-actions"><a class="btn" href="/classes">进入我的班级</a></div>' +
        '</div>';
    }
    markDone();
    clearTourParam();
  }

  window.Tour = {
    start: function () { location.href = '/classes/new?tour=1&step=1'; },
    // 点击「?」随时打开引导欢迎窗（不限制首次）
    open: function () { showWelcome(); },
    exit: function () {
      markDone();
      var el = document.getElementById('tour-bubble'); if (el) el.remove();
      var mask = document.getElementById('tour-mask'); if (mask) mask.classList.remove('show');
      clearTourParam();
    },
  };

  document.addEventListener('DOMContentLoaded', function () {
    try {
      if (localStorage.getItem(KEY)) return;          // 已完成引导，不再弹
      if (inTour()) { mountBubble(); return; }         // 已在引导流程中 → 显示当前步气泡
      if (isLoggedIn()) { showWelcome(); }             // 首次登录 → 弹欢迎
    } catch (e) {}
  });

  // 点欢迎遮罩空白 = 跳过
  document.addEventListener('DOMContentLoaded', function () {
    var mask = document.getElementById('tour-mask');
    if (mask) {
      mask.addEventListener('click', function (e) { if (e.target === this) window.Tour.exit(); });
    }
  });
})();
