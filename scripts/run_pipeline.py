#!/usr/bin/env python3
"""
群友炼化机 CLI — 无 GUI 模式运行完整分析 Pipeline。

用法:
    python scripts/run_pipeline.py --files chat1.json chat2.json --target-uin 123456789 --api-key sk-xxx

完整帮助:
    python scripts/run_pipeline.py --help
"""
import argparse
import json
import os
import sys

# 确保项目根目录在 sys.path 中
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.config import load_config, save_config, DEFAULT_CONFIG
from core.pipeline.runner import HeadlessPipelineRunner
from core.pipeline.utils import estimate_analysis
from core.data_processor import extract_chat_context, format_for_ai


def parse_args():
    parser = argparse.ArgumentParser(
        prog="run_pipeline",
        description="群友炼化机 CLI — 从 QQ 聊天记录 JSON 中提取目标人物画像并蒸馏为 Skill 包。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础用法
  python scripts/run_pipeline.py \\
      --files records/group_a.json records/group_b.json \\
      --target-uin 1778531385 \\
      --api-key sk-xxxx

  # 指定 API 与模型
  python scripts/run_pipeline.py \\
      --files chat.json \\
      --target-uin 123456 \\
      --api-base https://openrouter.ai/api/v1 \\
      --api-key sk-xxxx \\
      --model google/gemini-2.0-flash-001

  # 开启 Agent 审计 + 自定义配置文件
  python scripts/run_pipeline.py \\
      --files chat.json \\
      --target-uin 123456 \\
      --api-key sk-xxxx \\
      --agent-mode \\
      --config my_config.json

  # 仅导出脱水文本 (不运行 AI 分析)
  python scripts/run_pipeline.py \\
      --files chat.json \\
      --target-uin 123456 \\
      --export-txt output.txt

  # 断点续传
  python scripts/run_pipeline.py \\
      --resume logs/123456-20240101_120000
        """,
    )

    # 必选参数
    parser.add_argument(
        "--files", nargs="+", required=False,
        help="QQ 聊天记录 JSON 文件路径 (可多个)。使用 --resume 时可省略。"
    )
    parser.add_argument(
        "--target-uin", required=False,
        help="目标人物的 QQ 号 (UIN)。使用 --resume 时可省略。"
    )

    # API 配置
    api = parser.add_argument_group("API 配置")
    api.add_argument("--api-key", help="API Key (覆盖配置文件)")
    api.add_argument("--api-base", help="API Base URL (覆盖配置文件)")
    api.add_argument("--model", help="模型名称 (覆盖配置文件)")

    # 行为选项
    opts = parser.add_argument_group("行为选项")
    opts.add_argument("--config", help="自定义配置文件路径 (默认使用项目根目录 config.json)")
    opts.add_argument("--agent-mode", action="store_true", help="开启 Agent 深度审计模式")
    opts.add_argument("--no-sample", action="store_true", help="禁用智能抽样")
    opts.add_argument("--only-target", action="store_true", help="仅提取目标人发言 (无上下文)")
    opts.add_argument("--export-txt", metavar="FILE", help="仅导出脱水 TXT 文本，不运行 AI 分析")
    opts.add_argument("--resume", metavar="LOG_DIR", help="从指定的会话目录断点续传")
    opts.add_argument("--estimate", action="store_true", help="仅输出资源消耗预估，不运行分析")
    opts.add_argument("--quiet", action="store_true", help="静默模式，仅输出最终结果路径")

    return parser.parse_args()


def load_merged_config(args) -> dict:
    """加载并合并配置：默认 < 配置文件 < 命令行参数"""
    if args.config:
        if not os.path.exists(args.config):
            print(f"Error: 配置文件不存在: {args.config}", file=sys.stderr)
            sys.exit(1)
        with open(args.config, "r", encoding="utf-8") as f:
            cfg = DEFAULT_CONFIG.copy()
            cfg.update(json.load(f))
    else:
        cfg = load_config()

    # 命令行覆盖
    if args.api_key:
        cfg["api_key"] = args.api_key
    if args.api_base:
        cfg["api_base"] = args.api_base
    if args.model:
        cfg["model"] = args.model
    if args.agent_mode:
        cfg["agent_mode"] = True
    if args.no_sample:
        cfg["sample_enabled"] = False
    if args.only_target:
        cfg["only_target"] = True

    return cfg


def do_export_txt(args, cfg):
    """仅导出脱水文本"""
    if not args.files or not args.target_uin:
        print("Error: --export-txt 需要 --files 和 --target-uin", file=sys.stderr)
        sys.exit(1)

    for f in args.files:
        if not os.path.exists(f):
            print(f"Error: 文件不存在: {f}", file=sys.stderr)
            sys.exit(1)

    messages = extract_chat_context(
        args.files, args.target_uin,
        cfg.get("only_target", False),
        cfg.get("sample_enabled", True),
        cfg.get("sample_limit", 5000),
        cfg.get("context_window", 2),
    )
    if not messages:
        print(f"Error: 未找到 QQ 号 {args.target_uin} 的聊天记录。", file=sys.stderr)
        sys.exit(1)

    text = format_for_ai(messages, args.target_uin, cfg.get("only_target", False))
    out_path = args.export_txt
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(json.dumps({"status": "ok", "messages": len(messages),
                       "chars": len(text), "output": out_path}))
    sys.exit(0)


def do_estimate(args, cfg):
    """仅输出资源预估"""
    if not args.files or not args.target_uin:
        print("Error: --estimate 需要 --files 和 --target-uin", file=sys.stderr)
        sys.exit(1)

    messages = extract_chat_context(
        args.files, args.target_uin,
        cfg.get("only_target", False),
        cfg.get("sample_enabled", True),
        cfg.get("sample_limit", 5000),
        cfg.get("context_window", 2),
    )
    if not messages:
        print(f"Error: 未找到 QQ 号 {args.target_uin} 的聊天记录。", file=sys.stderr)
        sys.exit(1)

    text = format_for_ai(messages, args.target_uin, cfg.get("only_target", False))
    est = estimate_analysis(len(text), cfg)
    est["message_count"] = len(messages)
    est["text_chars"] = len(text)
    print(json.dumps(est, ensure_ascii=False, indent=2))
    sys.exit(0)


def do_resume(args, cfg):
    """断点续传"""
    log_dir = args.resume
    cp_path = os.path.join(log_dir, "checkpoint.json")
    if not os.path.exists(cp_path):
        print(f"Error: 找不到检查点文件: {cp_path}", file=sys.stderr)
        sys.exit(1)

    with open(cp_path, "r", encoding="utf-8") as f:
        state = json.load(f)

    if not state.get("target_uin"):
        print("Error: checkpoint 损坏 — 缺少 target_uin", file=sys.stderr)
        sys.exit(1)

    target_uin = state["target_uin"]
    merged_cfg = state.get("config", cfg)

    if not args.quiet:
        print(f"[Resume] 恢复会话: {log_dir}", file=sys.stderr)
        print(f"[Resume] 目标 QQ: {target_uin}  阶段: {state.get('current_stage', '?')}", file=sys.stderr)

    runner = HeadlessPipelineRunner(
        files=None, target_uin=target_uin, config=merged_cfg,
        preloaded_state=state,
        on_progress=None if args.quiet else None,
    )
    result = runner.run()
    _output_result(result, args.quiet)


def _output_result(result, quiet=False):
    """将最终结果输出到 stdout。"""
    if result.get("error"):
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    output = {
        "status": "ok",
        "skill_dir": result.get("skill_dir"),
        "report_length": len(result.get("report", "")),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    if not quiet and result.get("skill_dir"):
        print(f"\n分析完成！Skill 包已保存至: {result['skill_dir']}", file=sys.stderr)


def main():
    args = parse_args()
    cfg = load_merged_config(args)

    # 切换工作目录到项目根 (确保 prompts/ 等相对路径正确)
    os.chdir(PROJECT_ROOT)

    # 分支: 仅导出 TXT
    if args.export_txt:
        do_export_txt(args, cfg)

    # 分支: 仅预估
    if args.estimate:
        do_estimate(args, cfg)

    # 分支: 断点续传
    if args.resume:
        do_resume(args, cfg)
        sys.exit(0)

    # 正常流程: 需要 files 和 target-uin
    if not args.files:
        print("Error: 需要 --files 参数 (或使用 --resume 断点续传)", file=sys.stderr)
        sys.exit(1)
    if not args.target_uin:
        print("Error: 需要 --target-uin 参数", file=sys.stderr)
        sys.exit(1)
    if not cfg.get("api_key"):
        print("Error: 需要 API Key (通过 --api-key 或 config.json 提供)", file=sys.stderr)
        sys.exit(1)

    # 验证文件存在
    for f in args.files:
        if not os.path.exists(f):
            print(f"Error: 文件不存在: {f}", file=sys.stderr)
            sys.exit(1)

    if not args.quiet:
        # 先输出预估
        messages = extract_chat_context(
            args.files, args.target_uin,
            cfg.get("only_target", False),
            cfg.get("sample_enabled", True),
            cfg.get("sample_limit", 5000),
            cfg.get("context_window", 2),
        )
        if not messages:
            print(f"Error: 未找到 QQ 号 {args.target_uin} 的聊天记录。", file=sys.stderr)
            sys.exit(1)

        text = format_for_ai(messages, args.target_uin, cfg.get("only_target", False))
        est = estimate_analysis(len(text), cfg)
        print(f"[预估] 消息: {len(messages)} 条 | 文本: {len(text):,} 字符 | "
              f"分段: {est['num_chunks']} | API调用: ~{est['total_api_calls']} 次 | "
              f"耗时: ~{est['estimated_minutes']} 分钟 | 费用: ~${est['estimated_cost']}",
              file=sys.stderr)

    # 启动 pipeline
    runner = HeadlessPipelineRunner(
        files=args.files,
        target_uin=args.target_uin,
        config=cfg,
        on_progress=None if args.quiet else HeadlessPipelineRunner._default_progress,
    )

    result = runner.run()
    _output_result(result, args.quiet)


if __name__ == "__main__":
    main()
