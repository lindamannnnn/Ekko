# -*- coding: utf-8 -*-
"""串联编排（系统B 一键链路）：

  用户表单 ──▶ 脚本化 K12 教案生成(k12_generate, 课标 grounding)
           ──▶ adapter(k12_adapter: lesson.json → form["plan"])
           ──▶ 课件生成(v3 引擎：确定性引擎 + 免费模型层 + 自审闭环)
           ──▶ 渲染课件 HTML

教案端严格基于 k12-lesson-planning SKILL 的课标知识库（脚本化调用）。
课件端唯一引擎为 v3（courseware_engine 确定性 + 免费模型 + 自审闭环），旧 v2/v1 引擎已删除。

用法（CLI）：
  python orchestrator.py --subject 数学 --grade 五年级 --topic 分数的初步认识 --duration 40

作为库：
  from orchestrator import run
  res = run({"subject": "数学", "grade": "五年级", "topic": "分数的初步认识", "duration": "40"})
"""
import os
import sys
import re
import json
import time
import argparse
import html as _html

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import k12_generate  # noqa: E402  # 脚本化 K12 教案生成（基于 k12-lesson-planning SKILL）
import k12_adapter   # noqa: E402  # lesson.json → courseware form["plan"]


def load_env(path=None):
    path = path or os.path.join(BASE, ".env")
    env = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def make_client(env):
    # 统一用 courseware_engine.llm.LLMClient：支持 retries 指数退避 + 代理 + AI_*/COURSEWARE_* 统一读取。
    from courseware_engine.llm import LLMClient
    return LLMClient(
        api_key=env.get("AI_API_KEY") or env.get("COURSEWARE_API_KEY"),
        base_url=env.get("AI_BASE_URL") or env.get("COURSEWARE_BASE_URL"),
        model=env.get("AI_MODEL") or env.get("COURSEWARE_MODEL"),
        proxy=env.get("AI_PROXY") or env.get("COURSEWARE_PROXY"),
    )


def render_lesson_html(lesson):
    """轻量教案预览（仅 lesson_plan 文档，供网页 iframe 展示）。"""
    lp = next((d for d in lesson.get("documents", []) if d.get("id") == "lesson_plan"), None)
    shared = lesson.get("shared", {})
    parts = [
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>教案预览</title><style>"
        "body{font-family:-apple-system,'Microsoft YaHei',sans-serif;max-width:860px;"
        "margin:24px auto;padding:0 20px;color:#1f2937;line-height:1.7}"
        "h1{font-size:22px;margin:0 0 4px}.meta{color:#6b7280;font-size:13px;margin-bottom:18px}"
        ".sec{margin:18px 0}.sec h2{font-size:17px;border-left:4px solid #b45309;"
        "padding-left:10px;margin-bottom:8px}.blk{margin:6px 0;padding-left:4px}"
        ".lbl{font-weight:700;color:#92400e}.ph{background:#fef3c7;border-radius:6px;"
        "padding:4px 10px;display:inline-block;margin:4px 0;font-weight:700}"
        "table{border-collapse:collapse;margin:6px 0}td,th{border:1px solid #e5e7eb;"
        "padding:4px 8px;font-size:13px}</style></head><body>"
    ]
    title = lp.get("title", shared.get("topic", "教案")) if lp else shared.get("subject", "教案")
    meta = lp.get("meta", "") if lp else ""
    parts.append(f"<h1>{_html.escape(title)}</h1>")
    parts.append(f"<div class='meta'>{_html.escape(meta)}</div>")
    if lp:
        for sec in lp.get("sections", []):
            parts.append(f"<div class='sec'><h2>{_html.escape(sec.get('heading',''))}</h2>")
            for b in sec.get("blocks", []):
                # 兼容：部分教案块可能是裸字符串（非 dict），直接当纯文本渲染
                if not isinstance(b, dict):
                    t = k12_adapter.block_to_text(b, shared)
                    if t:
                        parts.append(f"<div class='blk'>{_html.escape(t)}</div>")
                    continue
                t = k12_adapter.block_to_text(b, shared)
                if not t:
                    continue
                if b.get("type") == "phase_header":
                    parts.append(f"<div class='ph'>{_html.escape(t)}</div>")
                elif b.get("type") in ("labeled", "callout") and b.get("label"):
                    lbl = b.get("label", "")
                    txt = t
                    # 模型有时把文本写成「重点：…」自带前缀，渲染会叠成「重点：重点：」，剥掉重复前缀
                    if lbl and txt.startswith(lbl):
                        rest = txt[len(lbl):]
                        if rest[:1] in ("：", ":", " "):
                            rest = rest[1:].lstrip()
                        txt = rest
                    parts.append(f"<div class='blk'><span class='lbl'>{_html.escape(lbl)}：</span>{_html.escape(txt)}</div>")
                else:
                    parts.append(f"<div class='blk'>{_html.escape(t)}</div>")
            parts.append("</div>")
    parts.append("</body></html>")
    return "".join(parts)


def run(form, out_dir=None, env=None, verbose=True):
    """一键：输入表单 -> 脚本化 K12 教案 -> adapter -> 课件。

    form: {subject, grade, topic, duration}
    返回 {lesson_json, lesson_html, course_html, plan, slides_count}
    """
    out_dir = out_dir or os.path.join(BASE, "out")
    os.makedirs(out_dir, exist_ok=True)
    env = env or load_env()
    # 升级 API 路径：用户在网页表单填 base_url/model/api_key 时，覆盖 .env 的免费模型配置
    for key in ("AI_BASE_URL", "AI_MODEL", "AI_API_KEY"):
        val = (form.get(key) or "").strip()
        if val:
            env[key] = val
    client = make_client(env)
    subj = form.get("subject", "教案")
    review_info = {"ok": None, "blocked": False, "hard": [], "soft": [], "expert": ""}
    # 课题打标签：避免「同 subject 同秒生成」文件名碰撞（如 语文《山行》与《秋天的雨》同秒互相覆盖）
    raw_topic = form.get("topic", "")
    topic_tag = re.sub(r"[^\w一-鿿-]+", "_", str(raw_topic)).strip("_")[:40] or "topic"
    ts = time.strftime("%Y%m%d_%H%M%S")

    # 1) 脚本化 K12 教案生成（课标 grounding，根治超纲）
    if verbose:
        print("== 生成教案（脚本化 K12 SKILL，课标 grounding） ==", flush=True)
    lesson = k12_generate.generate_lesson(form, client, verbose=verbose)
    lesson_json_path = os.path.join(out_dir, f"lesson_{subj}_{topic_tag}_{ts}.json")
    lesson_html_path = os.path.join(out_dir, f"lesson_{subj}_{topic_tag}_{ts}.html")
    with open(lesson_json_path, "w", encoding="utf-8") as f:
        json.dump(lesson, f, ensure_ascii=False, indent=2)
    with open(lesson_html_path, "w", encoding="utf-8") as f:
        f.write(render_lesson_html(lesson))
    if verbose:
        print(f"  教案 JSON -> {lesson_json_path}", flush=True)
        print(f"  教案 HTML -> {lesson_html_path}", flush=True)

    # 2) adapter：lesson.json → courseware form["plan"]
    if verbose:
        print("== adapter：教案 → 课件输入 ==", flush=True)
    ident, plan = k12_adapter.k12_lesson_to_form(lesson_json_path)

    # 3) 据教案生成课件（KB grounded + 后置过滤）
    if verbose:
        print("== 据教案生成课件 ==", flush=True)
    form_cw = {
        "mode": "subject",
        "subject": ident.get("subject") or form.get("subject"),
        "grade": ident.get("grade") or form.get("grade"),
        "topic": ident.get("topic") or form.get("topic"),
        "duration": int(ident.get("duration") or form.get("duration") or 40),
        "plan": plan,
    }
    # 引擎：v3 = 确定性引擎 + 免费模型层 + 自审闭环（唯一路径，免费路径做到顶）。
    engine = (form.get("engine") or os.environ.get("COURSEWARE_ENGINE") or "v3").lower()
    if engine == "v3":
        try:
            from courseware_engine.kb import retrieve_kb
            from courseware_engine.kb_adapter import auto_kb
            from courseware_engine.content import content_fill
            from courseware_engine.validator import validate_deck
            from courseware_engine import render as eng_render
            from courseware_engine.schemas import StyleRecipe
            from courseware_engine.enrich_llm import enrich_chinese
            from courseware_engine.teach_expand import expand_math, expand_chinese, expand_english

            kb_entry = retrieve_kb(form_cw)
            if kb_entry is None:
                raise RuntimeError("KB 未命中该课题")
            kb = dict(kb_entry)
            # 强/弱模型分离路径（彻底分离）：
            #   强模型：基于 KB 原料一次调用生成整份课件 segments（跳过确定性引擎 auto_kb），
            #           程序只保留词卡音标、数学答案验算等精确件。
            #   弱模型：auto_kb 确定性引擎 + 教学专家协议展开 + 自审闭环（为 GLM-4-Flash 设计）。
            strong = client.is_strong() if hasattr(client, "is_strong") else False
            if strong:
                # 强模型双 agent 闭环：
                #   内容 agent 全自主（retrieve_kb 检索课文→规划→生成→check_fact 自检）产 LessonContent
                #   → 程序确定性映射 segments → 审核 agent 独立审核（通过/打回+理由）
                #   → 打回则内容 agent 拿理由重做（最多 max_review 次）。客户端不支持 tool-calling 回退单次。
                from courseware_engine.kb_adapter import _derive_subject_cat, _derive_stage, _derive_lesson_type
                kb["subject_cat"] = _derive_subject_cat(kb.get("subject", ""))
                kb["stage"] = _derive_stage(kb.get("grade", ""))
                kb["lesson_type"] = _derive_lesson_type(kb, kb["subject_cat"])
                from courseware_engine.strong_agent import (
                    generate_content_agent, review_segments_agent)
                from courseware_engine.strong_gen import content_to_segments
                max_review = int(os.environ.get("AGENT_MAX_REVIEW", "2"))
                feedback = ""
                for attempt in range(max_review + 1):
                    lc = generate_content_agent(kb, client, feedback=feedback)
                    if lc is None:
                        raise RuntimeError("强模型内容 agent 未产出有效教学内容")
                    segs = content_to_segments(lc, kb)
                    approved, feedback, score = review_segments_agent(kb, segs, client)
                    if approved:
                        kb["segments"] = segs
                        if attempt > 0:
                            print(f"  [闭环] 第{attempt}次打回重做后审核通过（score={score}）", flush=True)
                        break
                    if attempt < max_review:
                        print(f"  [闭环] 审核打回（第{attempt+1}次），内容 agent 按意见重做", flush=True)
                else:
                    # 超过打回次数仍不通过：用最后一版放行（保底出片），但在 review_info 标记
                    kb["segments"] = segs
                    print(f"  [闭环] 超 {max_review} 次打回仍未通过，用最后一版保底放行", flush=True)
            else:
                # 弱模型分流（方案A，搬自 G:\test 镜像的改良链路）：
                #   数学：一次大调用 max_tokens=6000（内容短，已验证够用）
                #   语文/英语：分段生成 opening → concepts → analysis(语文) → closing（3-4 段，
                #             解决单次 6000 token 装不下整课导致缩水/截断）
                # 两条路都保留「语义审核 → 带反馈修正重生成」闭环（最多2轮）。
                from courseware_engine.kb_adapter import _derive_subject_cat, _derive_stage, _derive_lesson_type
                kb["subject_cat"] = _derive_subject_cat(kb.get("subject", ""))
                kb["stage"] = _derive_stage(kb.get("grade", ""))
                kb["lesson_type"] = _derive_lesson_type(kb, kb["subject_cat"])
                from courseware_engine.strong_gen import (
                    generate_content, generate_content_segmented, content_to_segments)
                from courseware_engine.reviewer import llm_review
                _cat = kb.get("subject_cat") or ""
                if _cat == "math":
                    lc = generate_content(kb, client, max_attempts=4, max_tokens=6000)
                    if lc is None:
                        raise RuntimeError("弱模型一次大调用未产出有效教学内容")
                    for _round in range(2):
                        kb["segments"] = content_to_segments(lc, kb)
                        _issues = llm_review(kb, client)
                        if not _issues:
                            break
                        if verbose:
                            print(f"  [修正] 第{_round+1}轮：审核发现 {len(_issues)} 处语义问题，带反馈重生成", flush=True)
                        kb["_fix_feedback"] = _issues
                        lc2 = generate_content(kb, client, max_attempts=2, max_tokens=6000)
                        if lc2 is not None:
                            lc = lc2
                    kb.pop("_fix_feedback", None)
                else:
                    # 语文/英语：分段生成（opening → concepts → analysis → closing）
                    # 分段失败时再试一次分段（不是直接回退一次大调用——6000 token 不够语文用）
                    lc = generate_content_segmented(kb, client, max_attempts=3)
                    if lc is None:
                        if verbose:
                            print("  [分段] 第1次分段生成失败，再试一次", flush=True)
                        lc = generate_content_segmented(kb, client, max_attempts=2)
                    if lc is None:
                        if verbose:
                            print("  [分段] 第2次分段也失败，回退一次大调用", flush=True)
                        lc = generate_content(kb, client, max_attempts=3, max_tokens=6000)
                    if lc is None:
                        raise RuntimeError("弱模型分段生成+一次大调用兜底均未产出有效教学内容")
                    for _round in range(2):
                        kb["segments"] = content_to_segments(lc, kb)
                        _issues = llm_review(kb, client)
                        if not _issues:
                            break
                        if verbose:
                            print(f"  [修正] 第{_round+1}轮：审核发现 {len(_issues)} 处语义问题，带反馈重生成", flush=True)
                        kb["_fix_feedback"] = _issues
                        lc2 = generate_content_segmented(kb, client, max_attempts=2)
                        if lc2 is not None:
                            lc = lc2
                    kb.pop("_fix_feedback", None)
                kb["segments"] = content_to_segments(lc, kb)

            # 样式 recipe：
            #   ① 用户在备课页选了风格（form["style"] 为 11 风格 id）→ 优先用 style_map
            #      映射的固定配色+字体（保版式，只换皮肤），强/弱模型路径都生效；
            #   ② 未选风格：强模型走样式 agent（palette_hint/mood/density 由 agent 决策，
            #      色值仍程序确定性映射合法 hex）；弱模型按课题取模的确定性 recipe。
            from courseware_engine.style_map import recipe_for_style
            recipe = recipe_for_style(form.get("style"))
            if recipe is not None:
                if verbose:
                    print(f"  [风格] 应用用户选定风格：{form.get('style')}", flush=True)
            elif strong:
                from courseware_engine.schemas import DesignDNA
                from courseware_engine.strong_agent import generate_recipe_agent
                dna = DesignDNA(subject_cat=kb.get("subject_cat", "general"),
                                stage=kb.get("stage", "mid"),
                                lesson_type=kb.get("lesson_type", "standard"))
                recipe = generate_recipe_agent(dna, kb, client)
            else:
                _palettes = [
                    {"primary": "#9a3412", "primary700": "#7c2d12", "accent": "#0f766e",
                     "bg": "#f7f3ec", "surface": "#fffdf8", "ink": "#292524", "muted": "#78716c",
                     "line": "#e7ddcb", "cover1": "#b45309", "cover2": "#7c2d12"},
                    {"primary": "#0f766e", "primary700": "#115e59", "accent": "#b45309",
                     "bg": "#f3f7f4", "surface": "#ffffff", "ink": "#1c2b27", "muted": "#5f7a72",
                     "line": "#d6e6df", "cover1": "#0f766e", "cover2": "#134e4a"},
                    {"primary": "#3730a3", "primary700": "#1e1b4b", "accent": "#0f766e",
                     "bg": "#f4f5fb", "surface": "#ffffff", "ink": "#1a1a2e", "muted": "#6b6b8a",
                     "line": "#dadaea", "cover1": "#3730a3", "cover2": "#1e1b4b"},
                ]
                _h = sum(ord(c) for c in (kb.get("topic") or "")) % len(_palettes)
                recipe = StyleRecipe(
                    palette=dict(_palettes[_h]),
                    fonts={"head": '"Noto Serif SC","Songti SC","SimSun",serif',
                           "body": '"PingFang SC","Microsoft YaHei","sans-serif"'},
                    decorations=["seal"],
                    illustration={"style": "line_art", "diagram_kinds": []},
                    layout_prefs={},
                )
            pages = content_fill(kb)
            pages, _ = validate_deck(pages, kb, cat=kb.get("subject_cat"))
            # 最终审核报告：确定性门禁必跑；LLM 语义审核仅在弱模型路径跑
            #（强模型一次产出质量已达标，且强模型再审核一次是额外 token/时间浪费）
            from courseware_engine.reviewer import review_report, llm_review
            _ok, _issues, _expert = review_report(kb)
            _llm_issues = [] if strong else llm_review(kb, client)
            # 阻断出片：确定性硬伤（无例题/分层同题/截断/模板套话/品析三要素缺/核心句型缺）→ blocked
            review_info = {
                "ok": _ok and not _llm_issues,
                "blocked": bool(_issues),          # 确定性门禁失败 = 阻断
                "hard": _issues,                   # 确定性门禁（可程序化判定，阻断）
                "soft": _llm_issues,               # LLM 语义审核（弱模型路径专用，强模型跳过）
                "expert": _expert,
            }
            if verbose:
                _all = _issues + _llm_issues
                if not _all:
                    print(f"  [审核] {_expert}专家：通过（{'强模型免语义自审' if strong else '含 LLM 语义审核'}）", flush=True)
                else:
                    print(f"  [审核] {_expert}专家：残留 {len(_all)} 处问题（确定性 {len(_issues)} + 语义 {len(_llm_issues)}）", flush=True)
                    for _i in _all[:8]:
                        print(f"      · {_i}", flush=True)
                    if _issues:
                        print("  [阻断] 确定性门禁未过，课件标记为 blocked（需人工复核/修 KB/修引擎）", flush=True)
            ident = {"subject": kb.get("subject"), "grade": kb.get("grade"), "topic": kb.get("topic")}
            course_html = eng_render.build_deck(
                pages, recipe, identity=ident, title=kb.get("topic"),
                meta=f'{kb.get("grade")} · {kb.get("subject")}')
            slides_n = len(pages)
            if verbose:
                print(f"  [渲染] v3 确定性引擎 + 免费模型层（{slides_n} 页）", flush=True)
        except Exception as e:
            raise RuntimeError(f"v3 课件生成失败：{e}")
    else:
        raise RuntimeError(f"未知引擎：{engine}（当前仅支持 v3）")

    course_path = os.path.join(out_dir, f"course_{subj}_{topic_tag}_{ts}.html")
    with open(course_path, "w", encoding="utf-8") as f:
        f.write(course_html)
    if verbose:
        print(f"  课件 HTML -> {course_path}（{slides_n}页，engine={engine}）", flush=True)

    return {
        "lesson_json": lesson_json_path,
        "lesson_html": lesson_html_path,
        "course_html": course_path,
        "plan": plan,
        "slides_count": slides_n,
        "engine": engine,
        "review": review_info,   # 审核门禁结果（阻断出片 + 报告）
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="教案→课件 一键生成（系统B，K12 SKILL 脚本化）")
    ap.add_argument("--subject", required=True)
    ap.add_argument("--grade", required=True)
    ap.add_argument("--topic", required=True)
    ap.add_argument("--duration", default="40")
    ap.add_argument("--out", default=None)
    ap.add_argument("--style", default=None, help="课件风格 id（graffiti/magazine/swiss/ink/devblue/apple/brutalist/glass/dracula/serif/business），选了则覆盖默认配色")
    args = ap.parse_args()
    form = {"subject": args.subject, "grade": args.grade,
            "topic": args.topic, "duration": args.duration,
            "style": args.style}
    res = run(form, out_dir=args.out)
    print("\n=== 完成 ===")
    print("教案 JSON:", res["lesson_json"])
    print("教案 HTML:", res["lesson_html"])
    print("课件 HTML:", res["course_html"])
