from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

from .calculator import InputError, calculate, serialize_result


def _load_json(path: str) -> Dict[str, Any]:
    if path == "-":
        raw = sys.stdin.read()
        return json.loads(raw)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="PrepayLab 提前还贷计算器")
    parser.add_argument("--input", required=True, help="输入 JSON 文件路径，或 '-' 读取 stdin")
    parser.add_argument("--schedule", action="store_true", help="输出还款计划表")
    parser.add_argument("--pretty", action="store_true", help="美化 JSON 输出")
    parser.add_argument("--output", help="输出到文件（默认 stdout）")

    args = parser.parse_args()

    try:
        payload = _load_json(args.input)
        result = calculate(payload, include_schedule=args.schedule)
        output = serialize_result(result)
    except (json.JSONDecodeError, InputError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
