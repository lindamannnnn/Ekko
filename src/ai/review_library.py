"""同类别课评库（兜底范文）。

仅在「该同学无历史课评 且 班级未上传优秀历史课评」时作为风格/结构参考，
避免 AI 凭空编造风格。样本来自 seeds/excellent_reviews/ 下按机构类型分类的范文。

分类映射：班级 type_code → 课评库文件。未知/自定义类型回退到学科(语数英)库。
"""
import os

_LIB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "seeds", "excellent_reviews",
)

# 班级类型码 → 课评库文件（可多个，按顺序拼接）
_TYPE_FILES = {
    "art": ["art.md"],
    "dance": ["dance.md"],
    "sports": ["sports.md"],
    "calligraphy": ["calligraphy.md"],
    "coding": ["coding_code.md", "coding_graphical.md"],
    "english": ["subjects.md"],
    "tutoring": ["tutoring.md"],
}
_DEFAULT_FILES = ["subjects.md"]  # 未知/通用类型回退到学科(语数英)课评库

_LABEL = {
    "art": "美术", "dance": "舞蹈", "sports": "体育",
    "calligraphy": "书法", "coding": "编程", "english": "学科(语数英)",
    "tutoring": "辅导班", "other": "通用",
}


def _load_file(name):
    path = os.path.join(_LIB_DIR, name)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read().strip()


def get_library_example(type_code, type_name_custom=None):
    """返回对应类别的课评库范文文本（兜底参考）。无匹配返回空串。"""
    files = _TYPE_FILES.get(type_code)
    if not files and type_name_custom:
        # 自定义类型：用中文类别名尝试匹配
        for code, files_ in _TYPE_FILES.items():
            if type_name_custom in (_LABEL.get(code) or ""):
                files = files_
                break
    if not files:
        files = _DEFAULT_FILES
    parts = [_load_file(f) for f in files]
    parts = [p for p in parts if p]
    return "\n\n---\n\n".join(parts)


def library_category(type_code, type_name_custom=None):
    """返回当前班级命中的课评库类别中文名（用于日志/调试）。"""
    if type_code in _LABEL:
        return _LABEL[type_code]
    if type_name_custom:
        for code, label in _LABEL.items():
            if type_name_custom in label:
                return label
    return _LABEL["other"]
