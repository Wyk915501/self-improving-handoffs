#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""handoff_flow.py —— 工作传递「何时写、何时改」规范的机检（G-W1~W3，report-only 试运行 v0.1 · 2026-09-20）

来历：负责人 09-20 定「项目—任务—动作」三层规范（见 docs/工作传递/README.md 新节），
要求自我改进循环学习并监督。本脚本只报告、不拦人——按 README 的约定先 report-only 跑一周。

  scan <docs_root> [--days 2] [--todo <输出md>] [--writer <名>]
    W1 只改没写：窗口内 docs/项目情况/** 有改动，而工作传递整树一份报告都没动 → 提醒
        （粗粒度代理版：暂无子任务→正本的正式映射表，映射表立起来后升级）
    W2 只写没回流：报告 ready_for_review 冻结超 48h，frontmatter 里 canonical_backflow.path
        指向的正本存在、但其「更新记录」没有一条日期 ≥ 冻结日 → 提醒（规矩③的机检化）；
        path 指向不存在的文件也算
    W3 碎片化：同一来源目录窗口内 ≥3 份报告改动 → 提醒考虑并进 draft
  退出码：0 无发现 · 1 有发现（只报告）· 2 用法或 IO 错
"""
import io, os, re, sys, glob, datetime

BJ = datetime.timezone(datetime.timedelta(hours=8))


def now_bj():
    return datetime.datetime.now(datetime.timezone.utc).astimezone(BJ)


def die(msg):
    print(msg)
    return 2


def fm_of(path):
    try:
        text = io.open(path, encoding="utf-8").read(6000)
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[3:end] if end > 0 else ""


def parse_date(s):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s or "")
    return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def scan(docs_root, days, todo_path, writer):
    now = now_bj()
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    wt = os.path.join(docs_root, "工作传递")
    canon_root = os.path.join(docs_root, "项目情况")
    if not os.path.isdir(wt):
        return die(f"找不到 {wt}")
    findings = []

    # ---- W1 只改没写 ----
    canon_changed = [p for p in glob.glob(os.path.join(canon_root, "**", "*.md"), recursive=True)
                     if os.path.getmtime(p) >= cutoff.timestamp()
                     and "_archive" not in p and not os.path.basename(p).startswith("README")]
    reports_all = glob.glob(os.path.join(wt, "**", "*_交接报告.md"), recursive=True)
    reports_changed = [p for p in reports_all if os.path.getmtime(p) >= cutoff.timestamp()]
    if canon_changed and not reports_changed:
        names = "、".join(os.path.relpath(p, docs_root).replace("\\", "/") for p in sorted(canon_changed)[:5])
        more = f" 等 {len(canon_changed)} 份" if len(canon_changed) > 5 else ""
        findings.append(("W1", f"近 {days} 天正本区改了 {names}{more}，工作传递却一份报告都没动——按三层规范，改正本的任务要留报告（纯格式修补或机器生成除外）"))

    # ---- W2 只写没回流 ----
    w2 = 0
    for p in reports_all:
        fm = fm_of(p)
        if not fm or re.search(r"^status:\s*ready_for_review", fm, re.M) is None:
            continue
        fz = parse_date((re.search(r"^frozen_at:\s*(\S+)", fm, re.M) or [None, ""])[1])
        if not fz or (now.date() - fz).days < 2:
            continue
        m = re.search(r"^canonical_backflow:\s*\n(?:  .*\n)*?  path:\s*(.+?)\s*$", fm, re.M)
        target = None
        raw = m.group(1).strip().strip('"') if m else ""
        if m and raw and raw.startswith("/root/"):
            w2 += 1
            if w2 <= 20:
                findings.append(("W2", f"{os.path.relpath(p, docs_root).replace(chr(92), '/')} 回流路径写的是 US3 绝对路径（{raw[:60]}…）——跨机不可核验，应写仓内相对路径"))
            continue
        if m and raw and not raw.lower().startswith("none"):
            # 路径口径三种都存在：相对工作区根（docs/ 前缀，模板示例）、相对 docs 根（裸路径）、
            # 相对报告自身（../…，codex 惯用）——按前缀分派，都试一遍再判不存在
            rel = raw.replace("/", os.sep)
            ws_root = os.path.dirname(os.path.abspath(docs_root))
            cands = ([os.path.normpath(os.path.join(ws_root, rel))] if raw.startswith("docs/") else []) \
                    + ([os.path.normpath(os.path.join(os.path.dirname(p), rel))] if raw.startswith(".") else []) \
                    + [os.path.join(docs_root, rel)]
            target = next((c for c in cands if os.path.exists(c)), cands[-1])
        if not target:
            continue  # v1 只查声明了回流目标的件；none（含带说明文字）先不追
        if not os.path.exists(target):
            w2 += 1
            if w2 <= 20:
                findings.append(("W2", f"{os.path.relpath(p, docs_root).replace(chr(92), '/')} 声明回流到 {raw}，但该文件不存在"))
            continue
        try:
            ttext = io.open(target, encoding="utf-8").read()
        except OSError:
            continue
        # 两种"最后更新"口径：正文「更新记录」的日期行；索引类 README 的 frontmatter updated:
        dates = [parse_date(d) for d in re.findall(r"^- (\d{4}-\d{2}-\d{2})", ttext, re.M)]
        dates += [parse_date(d) for d in re.findall(r"^updated:\s*(\d{4}-\d{2}-\d{2})", ttext, re.M)]
        dates = [d for d in dates if d]
        if not dates:
            # 台账/日志类文件没有「更新记录」节（内容本身就是记录）——用文件改动时刻兜底
            import time as _t
            d0 = datetime.date.fromtimestamp(os.path.getmtime(target))
            dates = [d0]
        if not dates or max(dates) < fz:
            w2 += 1
            if w2 <= 20:
                findings.append(("W2", f"{os.path.relpath(p, docs_root).replace(chr(92), '/')} 冻结已 {(now.date()-fz).days} 天，回流正本 {raw} 的更新记录没有对应新条目（最后 {max(dates) if dates else '无'}）"))
    if w2 > 20:
        findings.append(("W2", f"……另有 {w2 - 20} 份同类，完整清单跑 --todo 落文件"))

    # ---- W3 碎片化 ----
    from collections import Counter
    cnt = Counter(os.path.dirname(p) for p in reports_changed)
    for d, n in cnt.items():
        if n >= 3:
            names = "、".join(os.path.basename(p) for p in sorted(reports_changed) if os.path.dirname(p) == d)
            findings.append(("W3", f"{os.path.relpath(d, docs_root).replace(chr(92), '/')} 近 {days} 天改了 {n} 份报告（{names}）——同主题的推进按规范应并进同一份 draft，先确认不是碎片化"))

    # ---- 输出 ----
    out = [f"# 工作传递规范扫描（G-W，report-only）\n\n- 生成：{now:%Y-%m-%d %H:%M} 北京 · {writer}\n- 窗口：{days} 天 · 扫描根：{docs_root}\n- 性质：**只提醒不拦人**（试运行，规范见 docs/工作传递/README.md「何时写、何时改」）\n"]
    if not findings:
        out.append("无发现。\n")
    else:
        out.append(f"共 {len(findings)} 条：\n")
        for tag, msg in findings:
            out.append(f"- **{tag}** {msg}")
    text = "\n".join(out) + "\n"
    print(text)
    if todo_path:
        os.makedirs(os.path.dirname(os.path.abspath(todo_path)), exist_ok=True)
        io.open(todo_path, "w", encoding="utf-8", newline="\n").write(text)
        print(f"已写 {todo_path}")
    return 1 if findings else 0


def main(a):
    if len(a) < 3 or a[1] != "scan":
        print(__doc__)
        return 2
    docs_root = a[2]
    opt = lambda k, d: a[a.index(k) + 1] if k in a else d
    return scan(docs_root, int(opt("--days", "2")), opt("--todo", None), opt("--writer", "handoff_flow.py"))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
