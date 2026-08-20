# -*- coding: utf-8 -*-
"""courseware_engine/layouts/base.py —— 版式契约与槽位校验。

LayoutDef：每个版式 = {id, label, slot_schema, applicable, css, render(slots, theme)->html}
  - render 是纯函数，全程 _esc，内部 class 前缀 .ly-<id>，只消费 var(--*)；
  - applicable 描述「适用 cats/kinds/stages」，pager/coerce 据此过滤非法版式选择。

check_slots(schema, slots)：裁剪超长 / 补缺省 / 类型矫正；
  必填字段缺失 → 返回 None（触发骨架页兜底）。
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..util import _esc

# 引号集合（弯引号），用于截断时保持引号平衡，避免硬截断出孤立开引号。
_OPEN_Q = {"“", "‘", "＂", "\u201c", "\u2018"}
_CLOSE_Q = {"”", "’", "＂", "\u201d", "\u2019"}


def _close_quotes(s):
    """若字符串结尾仍开着引号，在末尾补上对应闭引号，保持引号平衡。

    用于 check_slots 的硬截断：被截断处之后才闭合的引号若不加闭引号，
    会让整页/整课件引号失衡（开≠闭）。"""
    s = s or ""
    depth = 0
    stack = []
    for ch in s:
        if ch in _OPEN_Q:
            depth += 1
            stack.append(ch)
        elif ch in _CLOSE_Q:
            if depth > 0:
                depth -= 1
                if stack:
                    stack.pop()
    if depth > 0:
        for op in stack:
            s = s + ("”" if op in "“\u201c" else "’")
    return s


def check_slots(schema, slots):
    """按 slot_schema 校验+裁剪 slots；必填缺失返回 None。

    schema 字段格式：{field: {"type":"str|list[str]|list[dict]",
                              "req":bool, "max_chars":int,
                              "max_items":int, "min_items":int,
                              "keys":{k:{type,max_chars}}}}。
    """
    if not isinstance(slots, dict):
        return None
    out = {}
    for fname, spec in schema.items():
        typ = spec.get("type", "str")
        req = bool(spec.get("req", False))
        present = fname in slots and slots[fname] not in (None, "", [], {})
        if not present:
            if req:
                return None
            continue
        val = slots[fname]
        if typ == "str":
            s = str(val)
            mc = spec.get("max_chars")
            if mc and len(s) > mc:
                # 关键：硬截断到 max_chars 时补上被截断处之后才闭合的孤立开引号，
                # 否则"在牛肚子里旅行"这类含引号的目标会被切出失衡开引号。
                s = _close_quotes(s[:mc])
            out[fname] = s
        elif typ == "list[str]":
            arr = [str(x) for x in val] if isinstance(val, list) else [str(val)]
            mc = spec.get("max_chars")
            if mc:
                arr = [_close_quotes(x[:mc]) for x in arr]
            ma = spec.get("max_items")
            if ma:
                arr = arr[:ma]
            if req and not arr:
                return None
            out[fname] = arr
        elif typ == "list[dict]":
            arr = [x for x in val if isinstance(x, dict)] if isinstance(val, list) else []
            keys = spec.get("keys", {}) or {}
            cleaned = []
            for d in arr:
                nd = {}
                for kk, ks in keys.items():
                    if kk not in d:
                        continue
                    vv = d[kk]
                    if ks.get("type") == "raw":
                        # 透传：保留嵌套 dict/list/数值，不被裁剪（diagram 渲染器所需）
                        nd[kk] = vv
                    elif ks.get("type") == "list[str]":
                        vv = [str(x) for x in vv] if isinstance(vv, list) else [str(vv)]
                        mc = ks.get("max_chars")
                        if mc:
                            vv = [x[:mc] for x in vv]
                    else:
                        vv = str(vv)
                        mc = ks.get("max_chars")
                        if mc and len(vv) > mc:
                            vv = vv[:mc]
                    nd[kk] = vv
                cleaned.append(nd)
            ma = spec.get("max_items")
            if ma:
                cleaned = cleaned[:ma]
            if req and not cleaned:
                return None
            out[fname] = cleaned
        else:
            out[fname] = val
    return out


@dataclass
class LayoutDef:
    layout_id: str
    label: str
    slot_schema: dict
    applicable: dict = field(default_factory=lambda: {"cats": "*", "kinds": "*", "stages": "*"})
    css: str = ""
    _render: Optional[Callable] = None

    def render(self, slots, theme):
        if self._render is None:
            return f'<div class="ly ly-{self.layout_id}">（版式 {self.layout_id} 未实现）</div>'
        return self._render(slots, theme)

    def check_slots(self, slots):
        return check_slots(self.slot_schema, slots)

    def is_applicable(self, cat, kind, stage):
        ap = self.applicable or {}
        cats = ap.get("cats", "*")
        kinds = ap.get("kinds", "*")
        stages = ap.get("stages", "*")
        ok_cat = (cats == "*") or (cat in cats)
        ok_kind = (kinds == "*") or (kind in kinds)
        ok_stage = (stages == "*") or (stage in stages)
        return ok_cat and ok_kind and ok_stage
