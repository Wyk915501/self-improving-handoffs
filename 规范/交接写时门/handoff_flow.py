#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""handoff_flow.py —— 工作传递「何时写、何时改」规范的机检（G-W1~W3，report-only 试运行 v0.2.2 · 2026-09-21）

来历：负责人 09-20 定「项目—任务—动作」三层规范（见 docs/工作传递/README.md 新节），
要求自我改进循环学习并监督。本脚本只报告、不拦人。
v0.2 按负责人裁定与 fable 09-21 核查（2026-09-21_0235 件）改四点：
  ①W2/W3 只查 **--since-date（默认 2026-09-20）之后冻结**的件——旧存量一次性赦免
    （74/78 是 codex 冻结旧件、按纪律不能回改，全量查＝清单只增不减）；
  ②回流路径一格可能写多个（分号分隔）→ 拆开逐个试，都不在才算"不存在"（原口径 31 条误报）；
  ③W3 豁免"对话件"（回签／签收／指令转达／收件／转发／前向更正开头）——那是纪律要求的件，不是碎片化；
  ④--todo 落**全量**清单（stdout 仍精简），W1 默认关（--w1 开）：无子任务→正本映射前它实际不可能命中。

v0.2.2 按 fable 09-21 复验（2026-09-21_1210 件）改四点：
  ①每条发现带**稳定键**（类别＋报告或目录路径），stdout 末行 `#keys [...]` 输出全量键——看门狗按键比新增，
    既不吃显示截断的亏（v0.2 的指纹取自截断后的 stdout，超过 20 条后新发现 12 次漏 8 次），也不因
    "冻结已 N 天"这类每天会变的措辞天天误报；②显示截断按**发现条数**截 20 条（v0.2 按行数截，实际只显示 16 条）；
  ③frontmatter 读取上限 6000→60000 字符（真树最长约一万；原上限会把超长的静默跳过）；④台账兜底的文件改动日按北京时间取
    （原按本机时区，US3 会差一天）；回流路径后面带括号说明的，剥掉说明再试一次。

  scan <docs_root> [--days 2] [--todo <输出md>] [--writer <名>] [--since-date 2026-09-20] [--w1]
    W1 只改没写（默认关）：窗口内 docs/项目情况/** 有改动，而工作传递整树一份报告都没动 → 提醒
        （粗粒度代理版：树里几乎总有报告在动，实际不可能命中——待子任务→正本映射表立起来再启用）
    W2 只写没回流：报告 ready_for_review 且 **冻结日 ≥ since-date**、冻结超 48h，frontmatter 里
        canonical_backflow.path 指向的正本存在、但其「更新记录」没有一条日期 ≥ 冻结日 → 提醒；
        path 指向不存在的文件也算；US3 绝对路径（/root/…）单列
    W3 碎片化：同一来源目录窗口内 ≥3 份**任务报告**改动（对话件豁免）→ 提醒考虑并进 draft
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
        text = io.open(path, encoding="utf-8").read(60000)  # 真树最长的 frontmatter 约一万字符；6000 会静默漏件
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[3:end] if end > 0 else ""


def parse_date(s):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s or "")
    return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def scan(docs_root, days, todo_path, writer, since_date=None, w1=False):
    now = now_bj()
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    since = parse_date(since_date or "2026-09-20")  # 负责人 09-21 裁定：只查此日之后冻结的件（存量赦免）
    wt = os.path.join(docs_root, "工作传递")
    canon_root = os.path.join(docs_root, "项目情况")
    if not os.path.isdir(wt):
        return die(f"找不到 {wt}")
    findings, keys = [], []

    def add(tag, key, msg):
        """key＝稳定键（类别:路径），不含天数、条数这类会自己变的字；看门狗据此判断"是不是新发现"。"""
        findings.append((tag, msg))
        keys.append(f"{tag}:{key}")

    # 对话件（fable 09-21：回签/签收/转达这类，纪律要求的件，不算任务报告、不计碎片化）。
    # 头部 16 字内含任一标记即认——主题常带前缀（"负责人指令转达…"不以"指令转达"开头）
    EXEMPT = ("回签", "签收", "指令转达", "收件", "转发", "前向更正", "监督反馈", "负责人指令",
              "负责人拍板", "任务转达", "任务改派", "升级指令", "流程固化", "对照竞赛回执")

    def is_dialog(p):
        stem = re.sub(r"^\d{4}-\d{2}-\d{2}_\d{4}_", "", os.path.basename(p))
        return any(t in stem[:16] for t in EXEMPT)

    # 报告枚举排除 _archive（v0.2.1，fable 09-21：克隆件＋刚归档的旧件会被数成两份碎片；归档件也不该再查回流）
    reports_all = [p for p in glob.glob(os.path.join(wt, "**", "*_交接报告.md"), recursive=True)
                   if not any(seg == "_archive" for seg in p.replace("\\", "/").split("/"))]
    reports_changed = [p for p in reports_all if os.path.getmtime(p) >= cutoff.timestamp()]

    # ---- W1 只改没写（v0.2 默认关：树里几乎总有报告在动，无映射表前不可能命中）----
    if w1:
        canon_changed = [p for p in glob.glob(os.path.join(canon_root, "**", "*.md"), recursive=True)
                         if os.path.getmtime(p) >= cutoff.timestamp()
                         and "_archive" not in p and not os.path.basename(p).startswith("README")]
        if canon_changed and not reports_changed:
            names = "、".join(os.path.relpath(p, docs_root).replace("\\", "/") for p in sorted(canon_changed)[:5])
            more = f" 等 {len(canon_changed)} 份" if len(canon_changed) > 5 else ""
            add("W1", "canon-without-report", f"近 {days} 天正本区改了 {names}{more}，工作传递却一份报告都没动——按三层规范，改正本的任务要留报告（纯格式修补或机器生成除外）")

    # ---- W2 只写没回流 ----
    w2 = 0
    for p in reports_all:
        rp = os.path.relpath(p, docs_root).replace(chr(92), '/')
        fm = fm_of(p)
        if not fm or re.search(r"^status:\s*ready_for_review", fm, re.M) is None:
            continue
        fz = parse_date((re.search(r"^frozen_at:\s*(\S+)", fm, re.M) or [None, ""])[1])
        if not fz or (now.date() - fz).days < 2:
            continue
        if fz < since:  # 负责人 09-21 裁定：存量赦免，只查 since-date 之后冻结的件
            continue
        m = re.search(r"^canonical_backflow:\s*\n(?:  .*\n)*?  path:\s*(.+?)\s*$", fm, re.M)
        target = None
        raw = m.group(1).strip().strip('"') if m else ""
        if m and raw and raw.startswith("/root/"):
            w2 += 1
            add("W2", rp, f"{rp} 回流路径写的是 US3 绝对路径（{raw[:60]}…）——跨机不可核验，应写仓内相对路径")
            continue
        if m and raw and not raw.lower().startswith("none"):
            # 一格可能写了多个路径（分号分隔，fable 抓的 31 条误报来源）→ 拆开逐个解析；
            # 口径三种：相对工作区根（docs/ 前缀）、相对 docs 根（裸路径）、相对报告自身（../…）
            ws_root = os.path.dirname(os.path.abspath(docs_root))
            cands = []
            for one in re.split(r"[；;]", raw):
                one = one.strip()
                if not one:
                    continue
                # 路径后面带括号说明的（"x.md（已回流某节）"）：原样先试，再剥掉说明试一次
                bare = re.sub(r"\s*[（(][^（()）]*[)）]\s*$", "", one).strip()
                for v in ([one, bare] if bare and bare != one else [one]):
                    rel = v.replace("/", os.sep)
                    cands += ([os.path.normpath(os.path.join(ws_root, rel))] if v.startswith("docs/") else []) \
                             + ([os.path.normpath(os.path.join(os.path.dirname(p), rel))] if v.startswith(".") else []) \
                             + [os.path.join(docs_root, rel)]
            target = next((c for c in cands if os.path.isfile(c)), cands[-1] if cands else None)  # 命中目录不算找到
        if not target:
            continue  # v1 只查声明了回流目标的件；none（含带说明文字）先不追
        if not os.path.isfile(target):
            w2 += 1
            add("W2", rp, f"{rp} 声明回流到 {raw}，但该文件不存在")
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
            d0 = datetime.datetime.fromtimestamp(os.path.getmtime(target), BJ).date()  # 冻结日是北京时间，这里也按北京时间取
            dates = [d0]
        if not dates or max(dates) < fz:
            w2 += 1
            add("W2", rp, f"{rp} 冻结已 {(now.date()-fz).days} 天，回流正本 {raw} 的更新记录没有对应新条目（最后 {max(dates) if dates else '无'}）")

    # ---- W3 碎片化（对话件豁免）----
    from collections import Counter
    tasks_changed = [p for p in reports_changed if not is_dialog(p)]
    cnt = Counter(os.path.dirname(p) for p in tasks_changed)
    for d, n in cnt.items():
        if n >= 3:
            names = "、".join(os.path.basename(p) for p in sorted(tasks_changed) if os.path.dirname(p) == d)
            rd = os.path.relpath(d, docs_root).replace(chr(92), '/')
            add("W3", rd, f"{rd} 近 {days} 天改了 {n} 份任务报告（{names}）——同主题的推进按规范应并进同一份 draft，先确认不是碎片化（回签/签收类对话件已不计）")

    # ---- 输出 ----（--todo 落全量；stdout 只显示前 20 条发现，末行 #keys 给出**全量**稳定键供看门狗比新增）
    out = [f"# 工作传递规范扫描（G-W，report-only）\n\n- 生成：{now:%Y-%m-%d %H:%M} 北京 · {writer}\n"
           f"- 窗口：{days} 天 · 扫描根：{docs_root} · 起算：只查 {since} 之后冻结的件（负责人 09-21 裁定）\n"
           f"- 性质：**只提醒不拦人**（试运行，规范见 docs/工作传递/README.md「何时写、何时改」）\n"]
    if not findings:
        out.append("无发现。\n")
    else:
        out.append(f"共 {len(findings)} 条：\n")
        for tag, msg in findings:
            out.append(f"- **{tag}** {msg}")
    text = "\n".join(out) + "\n"
    if len(findings) <= 20:
        shown = text
    else:  # 按发现条数截，不按行数截（页首自己占好几行）
        shown = "\n".join(out[:2] + [f"- **{t}** {m}" for t, m in findings[:20]]) + f"\n- ……其余 {len(findings) - 20} 条见 --todo 清单文件\n"
    print(shown)
    import json
    print("#keys " + json.dumps(sorted(set(keys)), ensure_ascii=False))
    if todo_path:
        os.makedirs(os.path.dirname(os.path.abspath(todo_path)), exist_ok=True)
        io.open(todo_path, "w", encoding="utf-8", newline="\n").write(text)
        print(f"已写 {todo_path}（全量 {len(findings)} 条）")
    return 1 if findings else 0


def main(a):
    if len(a) < 3 or a[1] != "scan":
        print(__doc__)
        return 2
    docs_root = a[2]
    opt = lambda k, d: a[a.index(k) + 1] if k in a else d
    return scan(docs_root, int(opt("--days", "2")), opt("--todo", None), opt("--writer", "handoff_flow.py"),
                since_date=opt("--since-date", "2026-09-20"), w1="--w1" in a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
