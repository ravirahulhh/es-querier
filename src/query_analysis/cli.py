"""
CLI：python -m query_analysis "查询" --domain video
"""
import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Query Analysis 意图解析")
    parser.add_argument("query", nargs="?", default="", help="用户查询")
    parser.add_argument("--domain", choices=["video", "book"], default="video", help="垂类")
    parser.add_argument("--config-path", default=None, help="可选，pipeline 配置文件路径（如启用 LLM）")
    parser.add_argument("--no-debug", action="store_true", help="不输出 debug 字段")
    parser.add_argument("--json", action="store_true", help="输出 JSON（默认）")
    args = parser.parse_args()

    if not args.query:
        parser.print_help()
        sys.exit(1)

    from query_analysis import parse
    result = parse(
        args.query,
        domain=args.domain,
        include_debug=not args.no_debug,
        config_path=args.config_path,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
