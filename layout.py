"""命令行入口：python layout.py --width 24 [文件...]"""

import argparse
import sys

from linebreak_engine import layout_text, load_rules

DEFAULT_RULES_DIR = "samples"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="把 Markdown 文本按全局最优断行排成打印稿。"
    )
    parser.add_argument("files", nargs="*", help="输入文件；缺省读标准输入")
    parser.add_argument("--width", type=int, required=True, help="行宽上限 W")
    parser.add_argument("--widths", default=None, help="宽度表路径")
    parser.add_argument("--kinsoku", default=None, help="禁则表路径")
    args = parser.parse_args(argv)

    import os
    here = os.path.dirname(os.path.abspath(__file__))
    widths_path = args.widths or os.path.join(
        here, DEFAULT_RULES_DIR, "widths.txt"
    )
    kinsoku_path = args.kinsoku or os.path.join(
        here, DEFAULT_RULES_DIR, "kinsoku.txt"
    )
    rules = load_rules(widths_path, kinsoku_path)

    if not args.files:
        sys.stdout.write(layout_text(sys.stdin.read(), rules, args.width))
        return 0
    for path in args.files:
        with open(path, "r", encoding="utf-8") as f:
            sys.stdout.write(layout_text(f.read(), rules, args.width))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
