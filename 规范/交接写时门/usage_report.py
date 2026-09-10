#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
usage_report.py —— 效率追踪 · 测量层原型（只读本机 Claude Code 会话记录；不上传、不改任何规则）
v0.1 · 2026-09-08 · 按 Codex sil-codex-20260908-03 §三 补：按消息身份去重、补输入列、比例改描述性命名、
                    搬运启发式要求整条命令每一段都是搬运、缺数据可见、今天标"非整日"

  python usage_report.py [--date YYYY-MM-DD（北京）] [--projects <~/.claude/projects>] [--json]

看什么：
  1. 按模型：assistant 消息数（按消息 uuid 去重）、输入／缓存创建／缓存读／输出 token
     "输出占比"＝输出 ÷（输入+缓存创建+0.1×缓存读+输出）——**描述性构成比，不是价值、不是费用**；费用要另按标价目版本算
  2. Agent／Task 调用：多少次没写 model（规则①）
  3. "只用读取工具的 turn 用了高级模型"粗估：该条 assistant 消息只调了 Read/Grep/Glob/LS，或 Bash 命令**每一段**都是
     ls/cat/head/tail/grep/find/wc/md5sum/sha256sum/stat/echo（按 && || ; | 切段）——启发式线索，不是难度真值
  4. 数据质量：重复消息数、缺 usage 的 assistant 消息数、解析失败行数、覆盖的记录文件数
局限：记录里没有"这一步该用什么模型"的真值；今天的数字截至运行时刻，不是整日；只覆盖本机 Claude Code，不含 Codex。
本脚本会解析完整记录（含工具参数）以识别工具调用，但只输出计数，不输出正文。
"""
import io, os, sys, json, glob, re
from datetime import datetime, timezone, timedelta

BJ = timezone(timedelta(hours=8))
CARRIER_TOOLS = {"Read", "Grep", "Glob", "LS"}
CARRIER_BASH = re.compile(r"^\s*(ls|cat|head|tail|grep|rg|find|wc|md5sum|sha256sum|stat|dir|echo)\b")
SPLIT = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")


def bash_is_carrier(cmd):
    segs = [s for s in SPLIT.split(str(cmd)) if s.strip()]
    return bool(segs) and all(CARRIER_BASH.match(s) for s in segs)


def bj_date(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(BJ).strftime("%Y-%m-%d")
    except Exception:
        return None


def main(argv):
    date = None
    projects = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    as_json = "--json" in argv
    if "--date" in argv:
        date = argv[argv.index("--date") + 1]
    if "--projects" in argv:
        projects = argv[argv.index("--projects") + 1]
    today = datetime.now(BJ).strftime("%Y-%m-%d")
    date = date or today

    per_model, carrier, seen = {}, {}, set()
    agent_calls = {"total": 0, "no_model": 0, "by_model": {}}
    q = {"files": 0, "parse_fail": 0, "dup_msgs": 0, "no_usage": 0}
    files = glob.glob(os.path.join(projects, "**", "*.jsonl"), recursive=True)
    for p in files:
        try:
            if datetime.fromtimestamp(os.path.getmtime(p), BJ).strftime("%Y-%m-%d") < date:
                continue
            fh = io.open(p, encoding="utf-8", errors="replace")
        except OSError:
            continue
        q["files"] += 1
        with fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    obj = json.loads(ln)
                except json.JSONDecodeError:
                    q["parse_fail"] += 1
                    continue
                if obj.get("type") != "assistant" or bj_date(obj.get("timestamp", "")) != date:
                    continue
                msg = obj.get("message") or {}
                ident = obj.get("uuid") or msg.get("id") or (p + str(obj.get("timestamp")))
                if ident in seen:
                    q["dup_msgs"] += 1
                    continue
                seen.add(ident)
                model = msg.get("model") or "?"
                u = msg.get("usage")
                m = per_model.setdefault(model, {"msgs": 0, "input": 0, "cache_create": 0, "cache_read": 0, "output": 0, "no_usage": 0})
                m["msgs"] += 1
                if not u:
                    m["no_usage"] += 1
                    q["no_usage"] += 1
                    u = {}
                m["input"] += int(u.get("input_tokens") or 0)
                m["cache_create"] += int(u.get("cache_creation_input_tokens") or 0)
                m["cache_read"] += int(u.get("cache_read_input_tokens") or 0)
                m["output"] += int(u.get("output_tokens") or 0)
                tools = []
                for c in (msg.get("content") or []):
                    if isinstance(c, dict) and c.get("type") == "tool_use":
                        name, inp = c.get("name") or "", c.get("input") or {}
                        tools.append((name, inp))
                        if name in ("Agent", "Task"):
                            agent_calls["total"] += 1
                            mm = inp.get("model")
                            if not mm:
                                agent_calls["no_model"] += 1
                            agent_calls["by_model"][mm or "(未写)"] = agent_calls["by_model"].get(mm or "(未写)", 0) + 1
                if tools and all((n in CARRIER_TOOLS) or (n == "Bash" and bash_is_carrier(i.get("command", ""))) for n, i in tools):
                    carrier[model] = carrier.get(model, 0) + 1

    def billed(m):
        return m["input"] + m["cache_create"] + 0.1 * m["cache_read"] + m["output"]

    out = {"date": date, "partial_day": date == today, "quality": q, "models": {}, "agent_calls": agent_calls}
    for model, m in sorted(per_model.items(), key=lambda kv: -billed(kv[1])):
        b = billed(m)
        out["models"][model] = dict(m, weighted_total=int(b), output_share=round(m["output"] / b, 4) if b else None,
                                    cache_read_share=round(m["cache_read"] / max(1, m["input"] + m["cache_create"] + m["cache_read"]), 3),
                                    carrier_turns=carrier.get(model, 0))
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    print(f"效率测量（北京 {date}{'，今天截至 ' + datetime.now(BJ).strftime('%H:%M') + '，非整日' if date == today else ''}）"
          f"：记录文件 {q['files']}，去重消息 {sum(m['msgs'] for m in per_model.values())}，重复 {q['dup_msgs']}，缺 usage {q['no_usage']}，解析失败行 {q['parse_fail']}")
    print(f"{'模型':28s} {'消息':>5s} {'输入':>8s} {'缓存创建':>10s} {'缓存读':>11s} {'输出':>8s} {'输出占比':>7s} {'缓存读占比':>9s} {'读取turn':>8s}")
    for model, m in out["models"].items():
        print(f"{model:28s} {m['msgs']:5d} {m['input']:8d} {m['cache_create']:10d} {m['cache_read']:11d} {m['output']:8d} "
              f"{(m['output_share'] or 0) * 100:6.2f}% {m['cache_read_share'] * 100:8.1f}% {m['carrier_turns']:8d}")
    a = agent_calls
    print(f"\nAgent/Task 调用 {a['total']} 次，没写 model 的 {a['no_model']} 次；按 model：{a['by_model']}")
    print("说明：输出占比＝输出÷(输入+缓存创建+0.1×缓存读+输出)，只是构成描述，不是价值或费用；读取 turn＝该条只调了读取类工具，只是线索。")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
