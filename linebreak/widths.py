"""码位宽度表。

宽度单位是半角：半角字符 1 个单位，全角字符 2 个单位。
表文件每行一个闭区间：``起始码位 结束码位 宽度``，码位写成 ``U+XXXX``；
以 ``#`` 开头的是注释，``默认 N`` 给出表外码位的默认宽度。

区间不做拆分合并，按文件中出现的顺序构建索引；查表时命中起始码位
不大于目标码位的最后一个区间。样例表的区间互不重叠，结果与顺序无关，
因此同一份表重复加载得到完全一致的宽度。
"""

import bisect
import re

_CODEPOINT = re.compile(r"U\+([0-9A-Fa-f]+)")


class WidthTable:
    """码位 -> 半角宽度 的查询表。"""

    def __init__(self, intervals, default=1):
        self._intervals = sorted(intervals, key=lambda iv: (iv[0], iv[1]))
        self._starts = [iv[0] for iv in self._intervals]
        self.default = default

    @classmethod
    def from_file(cls, path):
        with open(path, encoding="utf-8") as fh:
            return cls.from_string(fh.read())

    @classmethod
    def from_string(cls, text):
        intervals = []
        default = 1
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("默认"):
                default = int(line.split()[1])
                continue
            codes = _CODEPOINT.findall(line)
            width = int(line.split()[2])
            intervals.append((int(codes[0], 16), int(codes[1], 16), width))
        return cls(intervals, default)

    def width_of(self, char):
        code = ord(char)
        idx = bisect.bisect_right(self._starts, code) - 1
        if idx >= 0:
            start, end, width = self._intervals[idx]
            if start <= code <= end:
                return width
        return self.default
