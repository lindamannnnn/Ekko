"""课件上传安全校验：扩展名白名单 + 文件头魔数校验 + 解析文本长度上限。

防两类绕过：
1) 改名绕过：把 evil.exe 改名成 evil.pdf 上传。白名单只查扩展名，
   必须用文件头（magic number）确认内容真的是该类型。
2) 解析炸弹：恶意 docx / pptx（本质是 zip）/ pdf 解压或解析出超长文本，
   拖垮内存与 CPU。对抽取出的文本长度设上限。

注意：上传目录本身不对外静态托管（见 lessons / classes 路由），已上传文件
无法通过 URL 被直接访问，因此不存在"上传 html/svg 触发存储型 XSS"的路径。
本模块进一步堵住"内容伪造 + 解析 DoS"两面。
"""
import os

ALLOWED_EXT = {".txt", ".pptx", ".docx", ".doc", ".pdf"}
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10MB
MAX_EXTRACTED_CHARS = 1_500_000        # 抽取文本上限 ~1.5MB（防解析炸弹）

# 各类型合法的文件头签名（前若干字节）
_SIGNATURES = {
    ".pdf": (b"%PDF",),
    ".docx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".pptx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".doc": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08", b"\xd0\xcf\x11\xe0"),
    ".txt": None,  # 纯文本不校验二进制签名
}


def validate_upload(file_storage, max_bytes=DEFAULT_MAX_BYTES):
    """校验扩展名 + 文件头魔数 + 大小。不通过抛 ValueError（文案可直接回用户）。

    会重置 file_stream 指针到开头，调用方可直接 file_storage.save()。
    """
    filename = getattr(file_storage, "filename", "") or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"不支持的文件类型：{ext or '未知'}（支持 txt / docx / pptx / pdf）")

    stream = file_storage.stream
    # 大小校验（先看大小，避免对超大文件做多余读取）
    try:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(0)
    except Exception:  # noqa: BLE001
        size = 0
    if size > max_bytes:
        raise ValueError("文件过大：课件不能超过 10MB，请压缩或分卷后再传。")

    # 文件头魔数校验（防改名绕过白名单）
    sigs = _SIGNATURES.get(ext)
    if sigs is not None:
        head = stream.read(8192)
        stream.seek(0)
        if not any(head.startswith(s) for s in sigs):
            raise ValueError(f"文件内容与扩展名（{ext}）不符，疑似被篡改，已拒绝。")
    return ext


def check_extracted_text(text, max_chars=MAX_EXTRACTED_CHARS):
    """解析出的文本过长时拒绝，防解析炸弹 / 内存耗尽。"""
    if text and len(text) > max_chars:
        raise ValueError(
            f"课件解析出的文本内容过长（>{max_chars // 1024}KB），"
            f"可能为异常文件，已拒绝。请拆分或精简后重试。"
        )
