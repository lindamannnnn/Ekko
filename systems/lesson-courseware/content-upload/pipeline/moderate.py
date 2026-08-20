# -*- coding: utf-8 -*-
"""pipeline/moderate.py —— 合规层：敏感/违规内容拦截。

定位（v3 计划 Q5「需要合规兜底」）：本功能「不为用户内容负责」（不纠错、不润色），
但仍需拦截**明显违法违规**内容（与「负责」不冲突，属法律红线兜底）。
  - 规则层：内置敏感词表（违禁品/赌博诈骗/色情低俗/暴力恐怖/政治敏感红线）；
  - 可选 API 层：免费模型二分类（合规 / 不合规 + 原因），默认关闭、可开。

命中规则或 API 判不合规 → 返回 {"ok": False, "reason": ...}；否则 {"ok": True}。
词表为示例性、可扩展；生产可替换为更全的词库或服务。
"""
import re
from .llm import make_client

# 示例性敏感词（命中即拦截）。可按需扩充。
RULE_WORDS = {
    "违禁品交易": ["毒品", "冰毒", "摇头丸", "海洛因", "管制刀具贩卖", "军火交易"],
    "赌博诈骗": ["网络赌博", "博彩平台", "私彩", "杀猪盘", "洗钱教程"],
    "色情低俗": ["色情网站", "裸聊", "成人影片下载", "招嫖"],
    "暴力恐怖": ["恐怖袭击教程", "制造爆炸物", "人体炸弹"],
    # 政治敏感红线（按中国法律）：命中即拦截
    "政治敏感": ["分裂国家", "颠覆国家政权", "煽动暴乱", "台独", "港独", "藏独", "疆独"],
}


def _rule_check(text: str):
    hits = []
    for cat, words in RULE_WORDS.items():
        for w in words:
            if w and w in text:
                hits.append(f"{cat}:{w}")
    if hits:
        return {"ok": False, "reason": "命中敏感词规则 → " + "；".join(hits[:5])}
    return {"ok": True}


def _api_check(text: str, env: dict) -> dict:
    prompt = (
        "你是内容安全审核员。判断下面这段用户上传内容是否包含明显违法违规信息"
        "（色情低俗、暴力恐怖、违禁品交易、赌博诈骗、或违反中国法律的政治敏感内容）。"
        "只输出 JSON：{\"unsafe\": true/false, \"reason\": \"简短原因(若unsafe)\"}。"
        "不要纠正知识性错误，只判断违法违规。"
    )
    try:
        client = make_client(env)
        out = client.complete(
            [{"role": "system", "content": prompt},
             {"role": "user", "content": text[:6000]}],
            temperature=0.0, max_tokens=400, retries=1)
        import json
        m = re.search(r"\{.*\}", out or "", re.S)
        if m:
            d = json.loads(m.group(0))
            if d.get("unsafe"):
                return {"ok": False, "reason": "模型判定不合规 → " + str(d.get("reason", ""))}
    except Exception:
        pass
    return {"ok": True}


def moderate(text: str, env: dict = None, use_api: bool = False) -> dict:
    """入口：返回 {"ok": bool, "reason": str}。"""
    text = (text or "").strip()
    if not text:
        return {"ok": True}
    res = _rule_check(text)
    if not res["ok"]:
        return res
    if use_api:
        return _api_check(text, env or {})
    return {"ok": True}
