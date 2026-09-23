"""行首/行尾禁则字符表。

文件里用注释分两节：包含「行首禁则」的注释之后是行首禁则字符，
包含「行尾禁则」的注释之后是行尾禁则字符，字符之间用空白分隔。
"""


def load_kinsoku(path):
    with open(path, encoding="utf-8") as fh:
        return parse_kinsoku(fh.read())


def parse_kinsoku(text):
    no_line_start = set()
    no_line_end = set()
    section = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            if "行首禁则" in line:
                section = no_line_start
            elif "行尾禁则" in line:
                section = no_line_end
            continue
        if not line or section is None:
            continue
        for char in line.split():
            section.add(char)
    return frozenset(no_line_start), frozenset(no_line_end)
