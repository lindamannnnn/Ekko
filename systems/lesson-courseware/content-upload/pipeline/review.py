# -*- coding: utf-8 -*-
"""LLM 审核：检查 segment 切出的 slides 连贯性，把切碎的内容重新合并/调整。

输入：slides（JSON 数组，segment 的输出）
输出：修正后的 slides（结构调整，文字内容不改写）

设计原则：
- LLM 只做「结构审核」（合并/移动页），不改写、不润色文字
- 代码块占位符 §§CODE_BLOCK_N§§ 必须原样保留
- LLM 失败/超时/输出非法 → 原样返回 segment 结果（不阻塞生成）
"""
import json
import re


def _extract_json_array(out: str) -> list:
    """从 LLM 输出中提取 JSON 数组（兼容 ```json 围栏和首尾解释文字）。"""
    if not out:
        return []
    s = out.strip()
    # 去 ```json ... ``` 围栏
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    if m:
        s = m.group(1).strip()
    # 找第一个 [ 到最后一个 ]
    i, j = s.find("["), s.rfind("]")
    if i >= 0 and j > i:
        s = s[i:j + 1]
    try:
        arr = json.loads(s)
        return arr if isinstance(arr, list) else []
    except Exception:
        return []


def _split_multi_exercises(slides: list) -> list:
    """规则拆分：一页里有多个「练习/例题」标记 → 拆分成多页。

    识别标记：`练习 1`、`练习 2`、`例题 1`、`例 1`、`Example 1` 等。
    """
    _EXERCISE_RE = re.compile(r"^(?:练习|例题|例|Example|EXAMPLE)\s*[0-9一二三四五六七八九十]+")
    out = []
    for s in slides:
        bullets = s.get("bullets") or []
        # 找所有练习标记的位置
        split_points = []
        for i, b in enumerate(bullets):
            if _EXERCISE_RE.match(str(b).strip()):
                split_points.append(i)

        if len(split_points) <= 1:
            out.append(s)
            continue

        # 按练习标记拆分成多页
        code = s.get("code") or ""
        # code 可能是多个代码块合并的字符串，按 \n\n 分割成块
        code_blocks = [c.strip() for c in code.split("\n\n") if c.strip()]
        for idx, start in enumerate(split_points):
            end = split_points[idx + 1] if idx + 1 < len(split_points) else len(bullets)
            chunk = bullets[start:end]
            # 第一页保留原标题，后续页用练习标记作为标题
            title = s.get("title") or ""
            if idx > 0:
                title = str(chunk[0]).strip()
            # code 按占位符索引分配：bullets 里有 §§CODE_BLOCK_N§§ 的页，取第 N 个代码块
            chunk_code = ""
            for b in chunk:
                m = re.search(r"§§CODE_BLOCK_(\d+)§§", str(b))
                if m and code_blocks:
                    block_idx = int(m.group(1))
                    if block_idx < len(code_blocks):
                        chunk_code = code_blocks[block_idx]
                    break
            out.append({
                "title": title,
                "bullets": chunk,
                "code": chunk_code
            })
    return out


def review_slides(slides: list, env: dict = None, max_slides: int = 24) -> list:
    """LLM 审核 slides 连贯性，返回修正后的 slides。

    流程：
    1. 规则拆分：一页里有多个「练习/例题」标记 → 拆分成多页
    2. LLM 审核：检查连贯性，切碎的内容重新合并/调整（不改写文字；失败则原样）
    """
    if not slides or len(slides) <= 1:
        return slides

    # 第 1 步：规则拆分多个练习
    slides_after_split = _split_multi_exercises(slides)
    # 如果规则拆分增加了页数，说明 LLM 把多个练习合并了，跳过 LLM 审核（防再次合并）
    if len(slides_after_split) > len(slides):
        return slides_after_split

    # 第 2 步：LLM 审核（可选，失败不阻塞）
    from pipeline.llm import make_client

    prompt = (
        "你是一个「课件结构审核员」。下面是一个已切好页的幻灯片 JSON 数组。"
        "请检查并修正结构问题，但**绝不改写任何文字内容**（一个字都不能改）。\n"
        "审核点：\n"
        "1. **多个练习被合并**：`### 练习 1`、`### 练习 2` 等多个练习被合并到同一页 → "
        "拆分成独立页（一个练习一页）；\n"
        "2. **连贯内容被切碎**：同一例题的「题目描述、分析、代码、输入样例、输出样例、答案」"
        "被拆到不同页 → 合并到同一页（或调整到相邻页）；\n"
        "3. **标题单独成页**：某页只有标题没有正文，而正文在下一页 → 合并；\n"
        "4. **碎片页**：某页只有一两个明显是被误拆的残片要点 → 合并到相邻页；\n"
        "5. 合并后总页数不得超过 "
        f"{max_slides} 页。\n"
        "规则：\n"
        "- 每页结构：{\"title\":\"...\",\"bullets\":[\"...\"],\"code\":\"...\"}（code 可选）；\n"
        "- §§CODE_BLOCK_N§§ 占位符必须原样保留在对应页的 bullets 里，不要展开、不要删除；\n"
        "- 只做「合并页 / 移动要点 / 调整顺序」，不改写、不润色、不新增文字；\n"
        "- 如果原结构没有明显问题，原样返回；\n"
        "- 只输出修正后的 JSON 数组，不要任何解释。\n"
        "输入 JSON："
    )

    try:
        client = make_client(env or {})
        payload = json.dumps(slides, ensure_ascii=False)
        out = client.complete(
            [{"role": "system", "content": prompt},
             {"role": "user", "content": payload[:16000]}],
            temperature=0.1, max_tokens=4000, retries=2)
        arr = _extract_json_array(out)
        if not arr:
            return slides

        # 基本校验：每项必须是 dict 且有 title/bullets
        fixed = []
        for i, item in enumerate(arr):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "")
            bullets = item.get("bullets") or []
            if not isinstance(bullets, list):
                bullets = [str(bullets)]
            code = str(item.get("code") or "")
            # 如果 LLM 丢了 code，用原 slides 的 code 回填（按顺序对应）
            if not code and i < len(slides):
                code = slides[i].get("code") or ""
            if title or bullets:
                fixed.append({"title": title, "bullets": [str(b) for b in bullets], "code": code})

        # 占位符完整性校验：修正后必须保留所有原占位符
        def _placeholders(ss):
            ph = set()
            for s in ss:
                for b in [s.get("title", "")] + (s.get("bullets") or []):
                    ph.update(re.findall(r"§§CODE_BLOCK_\d+§§", str(b)))
            return ph

        if _placeholders(fixed) != _placeholders(slides):
            return slides  # 占位符丢了，回退原结果

        if fixed and len(fixed) <= max_slides:
            return fixed
        return slides
    except Exception:
        return slides
