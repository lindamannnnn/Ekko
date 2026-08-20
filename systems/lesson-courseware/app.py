# -*- coding: utf-8 -*-
"""系统B 最小网页表单入口：填 学科/年级/课题/时长 -> 后台生成教案+课件 -> 双预览 + plan.json 下载。

本轮本地使用（127.0.0.1），部署留到后续。
运行：python app.py  然后浏览器开 http://127.0.0.1:5057
"""
import os, sys, threading, uuid, traceback
from flask import Flask, request, jsonify, send_file

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import orchestrator  # noqa: E402

app = Flask(__name__)
TASKS = {}  # task_id -> {status, result, error}
OUT_DIR = os.path.join(BASE, "out")

FORM_HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>教案→课件 一键生成</title>
<style>
:root{--bg1:#eef2ff;--bg2:#faf5ff;--ink:#1e293b;--muted:#64748b;--primary:#4f46e5;--primary2:#7c3aed;--line:#e2e8f0;--ok:#10b981}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;background:linear-gradient(135deg,var(--bg1),var(--bg2));color:var(--ink);min-height:100vh;padding:34px 16px}
.wrap{max-width:1060px;margin:0 auto}
.hero{text-align:center;margin-bottom:26px}
.hero .badge{display:inline-flex;align-items:center;gap:6px;background:#fff;color:var(--primary);font-size:12px;padding:5px 13px;border-radius:999px;box-shadow:0 4px 14px rgba(79,70,229,.12);font-weight:600}
.hero h1{font-size:30px;margin:14px 0 7px;letter-spacing:.5px;background:linear-gradient(90deg,var(--primary),var(--primary2));-webkit-background-clip:text;background-clip:text;color:transparent}
.hero p{color:var(--muted);font-size:14px}
.card{background:#fff;border-radius:18px;padding:28px;box-shadow:0 18px 50px rgba(30,27,75,.08);border:1px solid rgba(226,232,240,.7)}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.field{display:flex;flex-direction:column;gap:7px}
.field.full{grid-column:1 / -1}
label.lbl{font-size:13px;font-weight:600;color:#334155}
label.lbl span{color:var(--primary);margin-left:2px}
input,select{font-size:14px;padding:11px 13px;border:1.5px solid var(--line);border-radius:11px;background:#f8fafc;transition:.18s;color:var(--ink);width:100%;font-family:inherit}
input:focus,select:focus{outline:none;border-color:var(--primary);background:#fff;box-shadow:0 0 0 4px rgba(79,70,229,.12)}
.chips{display:flex;gap:10px;flex-wrap:wrap}
.chip{flex:1;min-width:90px;text-align:center;padding:11px;border:1.5px solid var(--line);border-radius:11px;background:#f8fafc;cursor:pointer;font-size:14px;font-weight:600;color:#475569;transition:.18s;user-select:none}
.chip:hover{border-color:var(--primary);color:var(--primary)}
.chip.active{background:linear-gradient(135deg,var(--primary),var(--primary2));color:#fff;border-color:transparent;box-shadow:0 8px 18px rgba(79,70,229,.28)}
.btn{margin-top:22px;width:100%;padding:14px;border:0;border-radius:13px;cursor:pointer;font-size:15px;font-weight:700;color:#fff;background:linear-gradient(135deg,var(--primary),var(--primary2));box-shadow:0 12px 26px rgba(79,70,229,.32);transition:.18s;display:flex;align-items:center;justify-content:center;gap:10px}
.btn:hover:not(:disabled){transform:translateY(-2px);box-shadow:0 16px 32px rgba(79,70,229,.4)}
.btn:active:not(:disabled){transform:translateY(0)}
.btn:disabled{opacity:.75;cursor:not-allowed}
.spinner{width:17px;height:17px;border:2.5px solid rgba(255,255,255,.45);border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.steps{display:flex;gap:8px;margin-top:22px}
.step{flex:1;background:#f8fafc;border:1px solid var(--line);border-radius:11px;padding:12px 6px;text-align:center;font-size:12.5px;color:var(--muted);transition:.25s}
.step .dot{width:22px;height:22px;border-radius:50%;background:#e2e8f0;color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:12px;margin-bottom:6px;transition:.25s;font-weight:700}
.step.active{background:#eef2ff;border-color:#c7d2fe;color:var(--primary);font-weight:600}
.step.active .dot{background:var(--primary)}
.step.done{background:#ecfdf5;border-color:#a7f3d0;color:#047857}
.step.done .dot{background:var(--ok)}
.progress{height:6px;border-radius:999px;background:#e2e8f0;overflow:hidden;margin-top:20px;display:none}
.progress.show{display:block}
.progress i{display:block;height:100%;width:40%;border-radius:999px;background:linear-gradient(90deg,var(--primary),var(--primary2));animation:slide 1.3s infinite}
@keyframes slide{0%{margin-left:-40%}100%{margin-left:100%}}
.msg{text-align:center;margin-top:14px;font-size:14px;color:var(--primary);min-height:20px;font-weight:600}
#result{margin-top:26px}
.panel{background:#fff;border-radius:18px;overflow:hidden;box-shadow:0 18px 50px rgba(30,27,75,.08);border:1px solid rgba(226,232,240,.7);margin-bottom:22px}
.panel .phead{display:flex;align-items:center;justify-content:space-between;padding:15px 20px;border-bottom:1px solid var(--line);background:linear-gradient(90deg,#faf5ff,#eef2ff)}
.panel .phead h2{font-size:16px;color:#1e293b;display:flex;align-items:center;gap:9px}
.panel .phead .tag{font-size:12px;background:var(--primary);color:#fff;padding:3px 11px;border-radius:999px;font-weight:600}
.panel iframe{width:100%;height:560px;border:0;background:#fff;display:block}
.dl{display:inline-flex;align-items:center;gap:8px;margin-top:4px;padding:12px 20px;background:#ecfdf5;color:#047857;border-radius:11px;font-weight:600;font-size:14px;text-decoration:none;transition:.18s;border:1px solid #a7f3d0}
.dl:hover{background:#d1fae5;transform:translateY(-1px)}
.adv{margin-top:18px;border:1px solid var(--line);border-radius:13px;padding:14px 18px;background:#f8fafc}
.adv summary{cursor:pointer;font-weight:700;color:#334155;font-size:14px;user-select:none}
.foot{text-align:center;color:#94a3b8;font-size:12px;margin-top:28px}
@media(max-width:640px){.form-grid{grid-template-columns:1fr}.hero h1{font-size:24px}.panel iframe{height:440px}}
</style></head><body><div class="wrap">
<div class="hero"><div class="badge">&#10022; K12 智能备课</div>
<h1>教案 &rarr; 课件 一键生成</h1>
<p>填写课程信息，AI 基于课标与教材原文，生成可直接上课的教案与课件</p></div>
<div class="card"><form id="f">
  <div class="form-grid">
    <div class="field full"><label class="lbl">学科</label>
      <div class="chips" id="chips">
        <div class="chip" data-v="语文">语文</div>
        <div class="chip active" data-v="数学">数学</div>
        <div class="chip" data-v="英语">英语</div>
      </div>
      <input type="hidden" name="subject" id="subject" value="数学">
    </div>
    <div class="field"><label class="lbl">年级</label><input name="grade" value="五年级" placeholder="如 五年级 / 三年级上"></div>
    <div class="field"><label class="lbl">时长（分钟）<span>*</span></label><input name="duration" type="number" value="40"></div>
    <div class="field"><label class="lbl">渲染引擎</label>
      <select name="engine">
        <option value="">默认（v3 确定性 + 免费模型）</option>
        <option value="v3">v3 确定性引擎 + 免费模型（唯一引擎）</option>
      </select>
    </div>
    <div class="field full"><label class="lbl">课题</label><input name="topic" value="分数的初步认识" placeholder="如 分数的初步认识 / 富饶的西沙群岛"></div>
  </div>
  <details class="adv" id="adv">
    <summary>⚙️ 模型配置（可选 · 升级更强模型）</summary>
    <div class="form-grid" style="margin-top:14px">
      <div class="field full"><label class="lbl">API Base URL</label><input name="AI_BASE_URL" placeholder="留空 = 默认免费模型（GLM-4-Flash）"></div>
      <div class="field"><label class="lbl">模型名</label><input name="AI_MODEL" placeholder="如 deepseek-chat / gpt-4o"></div>
      <div class="field"><label class="lbl">API Key</label><input name="AI_API_KEY" type="password" placeholder="留空 = 使用服务器配置"></div>
    </div>
    <p style="color:#64748b;font-size:12px;margin-top:10px">默认走免费弱模型（GLM-4-Flash），把生成路径做到极致；填这里可升级到更强模型。</p>
  </details>
  <button class="btn" id="btn" type="submit"><span id="btxt">生成教案 + 课件</span></button>
  <div class="progress" id="prog"><i></i></div>
  <div class="steps" id="steps">
    <div class="step" data-i="1"><div class="dot">1</div>生成教案</div>
    <div class="step" data-i="2"><div class="dot">2</div>格式适配</div>
    <div class="step" data-i="3"><div class="dot">3</div>生成课件</div>
    <div class="step" data-i="4"><div class="dot">4</div>渲染导出</div>
  </div>
  <div class="msg" id="msg"></div>
</form></div>
<div id="result"></div>
<div class="foot">本地测试环境 &middot; 仅供内测 &middot; 生成约 2&ndash;4 分钟</div>
</div>
<script>
const chips=document.getElementById('chips'),subject=document.getElementById('subject');
chips.addEventListener('click',e=>{const c=e.target.closest('.chip');if(!c)return;chips.querySelectorAll('.chip').forEach(x=>x.classList.remove('active'));c.classList.add('active');subject.value=c.dataset.v;});
const btn=document.getElementById('btn'),btxt=document.getElementById('btxt'),msg=document.getElementById('msg'),result=document.getElementById('result'),prog=document.getElementById('prog'),steps=[...document.querySelectorAll('.step')];
function resetSteps(){steps.forEach((s,i)=>{s.className='step'+(i===0?' active':'');s.querySelector('.dot').textContent=i+1;});}
document.getElementById('f').addEventListener('submit',async e=>{
  e.preventDefault();
  btn.disabled=true;btxt.textContent='生成中…';prog.classList.add('show');resetSteps();
  msg.textContent='⏳ AI 备课中…（第 1 / 4 步）';result.innerHTML='';
  try{
    const r=await fetch('/generate',{method:'POST',body:new FormData(e.target)});
    const d=await r.json();
    const start=Date.now();
    const timer=setInterval(async ()=>{
      let s;try{s=await (await fetch('/status/'+d.task_id)).json();}catch(_){return;}
      if(s.status==='running'){
        const el=Math.min(3,Math.floor((Date.now()-start)/45000));
        steps.forEach((st,i)=>{st.className='step'+(i<el?' done':(i===el?' active':''));});
        msg.textContent='⏳ AI 备课中…（第 '+Math.min(4,el+1)+' / 4 步）';
      }else if(s.status==='done'){
        clearInterval(timer);prog.classList.remove('show');
        steps.forEach(st=>{st.classList.add('done');st.querySelector('.dot').textContent='✓';});
        btn.disabled=false;btxt.textContent='再生成一次';msg.textContent=(s.result.blocked?'⚠️ 生成完成，但审核门禁未过（需人工复核）':'✅ 生成完成');
        let banner='';
        if(s.result.blocked){
          banner='<div style="background:#fef2f2;border:1px solid #fecaca;color:#991b1b;border-radius:12px;padding:14px 18px;margin-bottom:18px;font-size:13.5px"><b>⚠️ 审核门禁未过：</b>本课有确定性硬伤，建议人工复核后再用于课堂。<ul style="margin:8px 0 0 18px">'+s.result.review_issues.map(i=>'<li>'+i.replace(/</g,'&lt;')+'</li>').join('')+'</ul></div>';
        }
        result.innerHTML=banner+
          '<div class="panel"><div class="phead"><h2>📘 教案</h2><span class="tag">K12 课标 grounded</span></div><iframe src="/file/'+s.result.lesson_html+'"></iframe></div>'+
          '<div class="panel"><div class="phead"><h2>📊 课件</h2><span class="tag">'+s.result.slides+' 页 · '+s.result.engine+'</span></div><iframe src="/file/'+s.result.course_html+'"></iframe></div>'+
          '<a class="dl" href="/file/'+s.result.lesson_json+'" download>⬇ 下载 lesson.json（教案结构化数据）</a>';
      }else if(s.status==='error'){
        clearInterval(timer);prog.classList.remove('show');
        btn.disabled=false;btxt.textContent='重试';msg.textContent='⚠️ 出错：'+(s.error||'未知错误');
      }
    },3000);
  }catch(err){btn.disabled=false;btxt.textContent='生成教案 + 课件';msg.textContent='请求失败：'+err;}
});
</script>
</body></html>"""


def _worker(task_id, form):
    try:
        res = orchestrator.run(form, verbose=False)
        review = res.get("review") or {}
        TASKS[task_id] = {"status": "done", "result": {
            "lesson_html": os.path.basename(res["lesson_html"]),
            "course_html": os.path.basename(res["course_html"]),
            "lesson_json": os.path.basename(res["lesson_json"]),
            "slides": res["slides_count"],
            "engine": res.get("engine", "v1"),
            "blocked": bool(review.get("blocked")),
            "review_issues": (review.get("hard") or []) + (review.get("soft") or []),
        }}
    except Exception as e:  # noqa: BLE001
        TASKS[task_id] = {"status": "error", "error": f"{e}\n{traceback.format_exc()}"}


@app.route("/")
def index():
    return FORM_HTML


@app.route("/generate", methods=["POST"])
def generate():
    form = {
        "subject": request.form.get("subject", "").strip(),
        "grade": request.form.get("grade", "").strip(),
        "topic": request.form.get("topic", "").strip(),
        "duration": request.form.get("duration", "40").strip(),
        "engine": request.form.get("engine", os.environ.get("COURSEWARE_ENGINE", "")).strip(),
        "AI_BASE_URL": request.form.get("AI_BASE_URL", "").strip(),
        "AI_MODEL": request.form.get("AI_MODEL", "").strip(),
        "AI_API_KEY": request.form.get("AI_API_KEY", "").strip(),
    }
    task_id = uuid.uuid4().hex[:8]
    TASKS[task_id] = {"status": "running"}
    threading.Thread(target=_worker, args=(task_id, form), daemon=True).start()
    return jsonify({"task_id": task_id})


@app.route("/status/<task_id>")
def status(task_id):
    return jsonify(TASKS.get(task_id, {"status": "unknown"}))


@app.route("/file/<path:fn>")
def file(fn):
    return send_file(os.path.join(OUT_DIR, fn))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5057, debug=False)
