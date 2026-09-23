"""命令行入口：python -m linebreak -w 行宽 [选项] [输入文件]。"""

import argparse
import sys

from .engine import layout_text
from .kinsoku import load_kinsoku
from .widths import WidthTable


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m linebreak",
        description="把 Markdown 文本按全局最优断行排成打印稿（只管断行）。",
    )
    parser.add_argument("input", nargs="?", help="输入文件，缺省读标准输入")
    parser.add_argument("-w", "--width", type=int, required=True,
                        help="行宽 W（半角单位）")
    parser.add_argument("--widths", default="samples/widths.txt",
                        help="宽度表路径（默认 samples/widths.txt）")
    parser.add_argument("--kinsoku", default="samples/kinsoku.txt",
                        help="禁则表路径（默认 samples/kinsoku.txt）")
    parser.add_argument("-o", "--output", help="输出文件，缺省写标准输出")
    args = parser.parse_args(argv)

    width_table = WidthTable.from_file(args.widths)
    no_start, no_end = load_kinsoku(args.kinsoku)
    with open(args.input, encoding="utf-8") if args.input else _stdin() as fh:
        text = fh.read()
    result = layout_text(text, args.width, width_table, no_start, no_end)
    with open(args.output, "w", encoding="utf-8", newline="") if args.output else _stdout() as fh:
        fh.write(result)
    return 0


class _stdin:
    def __enter__(self):
        return sys.stdin

    def __exit__(self, *exc):
        return False


class _stdout:
    def __enter__(self):
        return sys.stdout

    def __exit__(self, *exc):
        return False


if __name__ == "__main__":
    raise SystemExit(main())
