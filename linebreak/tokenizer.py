"""把文本切成排版单元。

单元类型：

- 单词单元：连续的半角字母、数字、连字符（``state-of-the-art``、``32``），
  内部永远不可断；
- CJK 单字单元：宽度为 2 的单个码位（汉字、假名、全角标点等），以及
  半角片假名（宽度表给 1 但属于日文，两侧都允许断行）；
- 普通单字单元：其余单码位（半角标点等），两侧不允许断行；
- ASCII 空格不单独成单元，记为后续单元的「前导空格」：行首的空格丢弃，
  行内的空格保留并占 1 个单位宽度。
"""

WORD_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "-"
)

HALFWIDTH_KATAKANA_START = 0xFF61
HALFWIDTH_KATAKANA_END = 0xFF9F

# 单元种类
WORD = "word"
CJK = "cjk"
CHAR = "char"


def _is_halfwidth_katakana(char):
    code = ord(char)
    return HALFWIDTH_KATAKANA_START <= code <= HALFWIDTH_KATAKANA_END


def tokenize(text, width_table):
    """返回单元列表，每个单元是 (文本, 宽度, 种类, 前导空格)。"""
    units = []
    i = 0
    length = len(text)
    pending_space = False
    while i < length:
        char = text[i]
        if char == " ":
            pending_space = True
            i += 1
            continue
        if char in WORD_CHARS:
            j = i + 1
            while j < length and text[j] in WORD_CHARS:
                j += 1
            segment = text[i:j]
            units.append((segment, len(segment), WORD, pending_space))
            pending_space = False
            i = j
            continue
        width = width_table.width_of(char)
        kind = CJK if width == 2 or _is_halfwidth_katakana(char) else CHAR
        units.append((char, width, kind, pending_space))
        pending_space = False
        i += 1
    return units
