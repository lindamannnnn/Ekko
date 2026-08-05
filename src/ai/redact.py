"""姓名脱敏与还原。

发送 AI 前把**其他同学**的姓名替换成占位符，返回后还原。
few-shot 样本同样需要脱敏，避免 AI 套用样本里的真名。

关于「当前学生本人」的姓名（redact_self）：
  历史实现把本人姓名也换成 {{STU}} 占位符，寄望模型原样回显后再还原。
  实测（2026-08-03 全量走查 30/30）模型几乎从不回显占位符，而是自行编造一个
  名字（涵涵/小明/小丽…），还原只对 {{STU}} 生效 → 课评里 100% 叫错孩子名字。
  因此默认 redact_self=False：当前学生的昵称直接明文传给模型（这是写他本人课评
  的必要信息，风险最小），其他同学姓名仍然脱敏。需要严格合规时可显式传 True。
"""
import re

# 占位符约定
STU = "{{STU}}"           # 当前学生本名
STU_NICK = "{{STU_NICK}}" # 当前学生昵称
# 同学姓名占位符，n 从 1 递增。
# 注意：这里用 % 而不是 str.format —— 旧版写作 "{{PEER_{}}}}" 再 .format(i)，
# 会抛 ValueError: Single '}' encountered in format string（因为从未传过
# peer_names 所以一直没被触发，2026-08-03 加同班脱敏时才暴露）。
PEER_TPL = "{{PEER_%d}}"


class Redactor:
    def __init__(self, student_name, student_nick=None, peer_names=None,
                 redact_self=False):
        self.student_name = student_name or ""
        self.student_nick = student_nick or ""
        self.redact_self = redact_self
        self.peers = [p for p in (peer_names or [])
                      if p and p != self.student_name and p != self.student_nick]
        self._map = {}   # 真名 -> 占位符
        self._inv = {}   # 占位符 -> 真名

    def _register(self, real, placeholder):
        self._map[real] = placeholder
        self._inv[placeholder] = real

    def redact(self, text: str) -> str:
        if not text:
            return text
        out = text
        # 先注册，按长度从长到短替换，避免短名误伤长名子串
        # 同学姓名（无论是否脱敏本人，同班其他学生一律脱敏）
        for i, p in enumerate(self.peers, start=1):
            self._register(p, PEER_TPL % i)
        # 本人：先昵称后本名（昵称通常更短，避免本名是其子串时冲突）
        if self.redact_self:
            if self.student_nick and self.student_nick != self.student_name:
                self._register(self.student_nick, STU_NICK)
            if self.student_name:
                self._register(self.student_name, STU)

        for real in sorted(self._map.keys(), key=len, reverse=True):
            out = out.replace(real, self._map[real])
        return out

    def restore(self, text: str) -> str:
        if not text:
            return text
        out = text
        # 还原同样按占位符长度从长到短
        for ph in sorted(self._inv.keys(), key=len, reverse=True):
            out = out.replace(ph, self._inv[ph])
        # 兜底：即使本轮未脱敏本人，模型也可能从历史课评/范文里学到占位符
        # 并原样吐出来，这里统一还原，避免 {{STU}} 泄漏到家长看到的文本里。
        if STU_NICK in out:
            out = out.replace(STU_NICK, self.student_nick or self.student_name or "")
        if STU in out:
            out = out.replace(STU, self.student_name or self.student_nick or "")
        # 未映射的同学占位符残留 → 去掉花括号，避免出现 {{PEER_1}} 这种乱码
        out = re.sub(r"\{\{PEER_\d+\}?\}?", "同学", out)
        return out


def redact_student_text(text, student_name, student_nick=None, peer_names=None):
    return Redactor(student_name, student_nick, peer_names).redact(text)


def restore_student_text(text, student_name, student_nick=None, peer_names=None):
    # 还原时占位符映射与脱敏一致
    return Redactor(student_name, student_nick, peer_names).restore(text)
