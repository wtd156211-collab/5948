"""按 samples/widths.txt 的区间表查码位宽度。

宽度单位是半角：半角 1，全角 2。区间按起始码位排序后二分查找，
表里没有的码位按默认宽度算。
"""


class WidthTable:
    def __init__(self, ranges, default=1):
        # ranges: [(start, end, width), ...]，按 start 排序，区间互不重叠
        self._ranges = tuple(sorted(ranges, key=lambda r: r[0]))
        self._starts = tuple(r[0] for r in self._ranges)
        self.default = default

    def width_of(self, ch):
        cp = ord(ch)
        lo, hi = 0, len(self._starts)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._starts[mid] <= cp:
                lo = mid + 1
            else:
                hi = mid
        idx = lo - 1
        if idx >= 0:
            start, end, width = self._ranges[idx]
            if start <= cp <= end:
                return width
        return self.default


def parse_codepoint(token):
    token = token.strip()
    if token.startswith("U+") or token.startswith("u+"):
        return int(token[2:], 16)
    return int(token, 16)


def parse_width_file(text):
    """解析宽度表文件，返回 (WidthTable, 默认宽度)。"""
    ranges = []
    default = 1
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("默认") or line.lower().startswith("default"):
            parts = line.split()
            default = int(parts[-1])
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        start, end, width = (
            parse_codepoint(parts[0]),
            parse_codepoint(parts[1]),
            int(parts[2]),
        )
        ranges.append((start, end, width))
    return WidthTable(ranges, default), default
