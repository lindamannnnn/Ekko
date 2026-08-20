# -*- coding: utf-8 -*-
"""pipeline/ingest.py —— 解析层：把用户上传内容转纯文本。

设计原则（对齐 v3 计划）：
  - 内容类型不限（学科/辅导班/培训机构讲义、Word/PPT/PDF/图片文本均可）；
  - 优先用 markitdown 通吃格式，无 markitdown 时降级纯文本读取；
  - 也支持用户直接粘贴文本。
不负责内容正确性，只做「格式 → 文本」的机械转换。
"""
import os

try:
    from markitdown import MarkItDown
    _MID = MarkItDown()
    HAVE_MID = True
except Exception:
    _MID = None
    HAVE_MID = False

# 直接按纯文本读取（无需重量级解析）的扩展名
_PLAIN_EXT = {".txt", ".csv", ".md", ".markdown"}


def ingest_text(text: str) -> str:
    """用户直接粘贴的文本。"""
    return (text or "").strip()


def ingest_file(path: str) -> str:
    """文件 → 纯文本。失败抛异常，由上层转友好提示。"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    ext = os.path.splitext(path)[1].lower()

    if ext in _PLAIN_EXT:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().strip()

    if HAVE_MID:
        try:
            res = _MID.convert(path)
            return (res.text_content or "").strip()
        except Exception as e:
            raise RuntimeError(f"markitdown 解析失败({ext}): {e}")

    raise RuntimeError(
        f"无法解析 {ext}：项目 venv 未安装 markitdown。"
        f"请先 `pip install markitdown`（当前 HAVE_MID={HAVE_MID}）。"
    )
