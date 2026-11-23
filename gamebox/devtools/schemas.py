from __future__ import annotations

import argparse
import json
from pathlib import Path

from gamebox.common.schemas import config_schema

TARGET = Path(__file__).parents[1] / "common" / "schemas" / "config.schema.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = json.dumps(config_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != content:
            raise SystemExit("Схема устарела: выполните make schemas")
        print("config.schema.json актуальна")
    else:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_text(content, encoding="utf-8")
        print(TARGET)


if __name__ == "__main__":
    main()
