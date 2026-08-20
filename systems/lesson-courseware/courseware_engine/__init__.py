# -*- coding: utf-8 -*-
"""courseware_engine：教案→课件 v3 引擎（确定性引擎 + 免费模型层 + 自审闭环）。

v3 引擎：KB 原料 → auto_kb 确定性适配 → enrich_llm 免费模型表达层 → teach_expand
教学专家协议 → reviewer 自审闭环 → content_fill → validate_deck → render.build_deck。

旧 v2 多智能体引擎（pipeline/agents/subjects/pipelines/quality/enrich）与 v1 vendor
单模板引擎（vendor/scripts/courseware_gen.py）已删除。

公开 API：render.build_deck / kb.retrieve_kb / llm.LLMClient / __version__。
"""
from . import schemas, layouts, style, render, kb, llm, util  # noqa: F401
from .render import build_deck  # noqa: F401
from .style import seeded_recipe  # noqa: F401

__version__ = "3.0.0"
