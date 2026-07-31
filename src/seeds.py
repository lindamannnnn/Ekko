"""类型预置载入：把 seeds/class_type_presets.yaml 幂等 upsert 进 class_type_presets 表。"""
import os
from pathlib import Path

import yaml

from extensions import db
from models.class_type_preset import ClassTypePreset


_SEED_PATH = Path(__file__).resolve().parent.parent / 'seeds' / 'class_type_presets.yaml'


def load_class_type_presets(force: bool = False) -> int:
    """载入/刷新机构类型预置。force=True 时覆盖已存在的字段。

    返回本次新增或更新的记录数。
    """
    if not _SEED_PATH.exists():
        return 0
    with open(_SEED_PATH, 'r', encoding='utf-8') as f:
        presets = yaml.safe_load(f) or []

    count = 0
    for p in presets:
        existing = ClassTypePreset.query.filter_by(code=p['code']).first()
        if existing and not force:
            continue
        if not existing:
            existing = ClassTypePreset(code=p['code'])
            db.session.add(existing)
        existing.name = p['name']
        existing.dimensions = p.get('dimensions')
        existing.tone = p.get('tone')
        existing.length_min = p.get('length_min', 180)
        existing.length_max = p.get('length_max', 320)
        existing.emoji_min = p.get('emoji_min', 2)
        existing.emoji_max = p.get('emoji_max', 5)
        existing.prompt_hints = p.get('prompt_hints')
        existing.quick_tags = p.get('quick_tags')
        existing.card_template = p.get('card_template', 'general')
        count += 1
    db.session.commit()
    return count
