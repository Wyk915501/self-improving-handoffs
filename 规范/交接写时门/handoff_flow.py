#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""handoff_flow.py —— 工作传递「何时写、何时改」规范的机检（G-W1~W3，report-only，v0.3 · 2026-10-02）

来历：负责人 09-20 定「项目—任务—动作」三层规范（见 docs/工作传递/README.md），要求自我改进循环学习并监督。
本脚本只报告、不拦人。v0.3 按 10-02 全面审查改五点：
  ①回流路径写成对端机器绝对路径（如 /root/<项目>/…）的，按前缀映射表（配置 flow.path_prefix_map）映射回本机再照常核对——
    原来一律报"写坏了"且不核对，9 条里 6 条是这种：回流其实做了，冻结件又改不了，条目永远消不掉；
  ②不带前缀的回流路径依次试 docs 根、工作区根、报告所在目录（原来只试 docs 根，工作区根下的文件也报"不存在"）；
  ③frontmatter 用 YAML 解析（带引号的 frozen_at 原来整件跳过，约四分之一的冻结件从没被查过）；
  ④W3 碎片化按**文件名里的写作时刻**（YYYY-MM-DD_HHMM，北京时间）判窗口，不再按文件改动时刻——镜像端的改动时刻
    是同步落盘的时刻，一次同步就会把整批老件数成"近 2 天改了 N 份"；
  ⑤读目标遇非 UTF-8 不再整次崩；清单原子写、内容没变不重写、首行写状态词；出错返回 2，与"有发现"（1）分开。

  scan <docs_root> [--days 2] [--todo <输出md>] [--writer <名>] [--since-date 2026-09-20] [--w1]
    W1 只改没写（默认关）：窗口内 docs/项目情况/** 有改动，而工作传递整树一份报告都没动（无映射表前几乎不可能命中）
    W2 只写没回流：报告 ready_for_review 且冻结日 ≥ since-date、冻结满 2 个日历日，canonical_backflow.path 指向的正本
        存在、但其「更新记录」（或 updated:）没有一条日期 ≥ 冻结日 → 提醒；指向不存在的文件也算
    W3 碎片化：同一来源目录、文件名时刻在窗口内的**任务报告** ≥3 份（回签/签收/转达等对话件豁免）→ 提醒考虑并进 draft
  退出码：0 无发现 · 1 有发现（只报告）· 2 用法、IO 或内部错误
"""
import io, os, re, sys, glob, json, datetime

sys.dont_write_bytecode = True  # 不在正本目录（docs 同步域）里留 __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import handoff_common as C  # noqa: E402

VERSION = "0.3"
BJ = C.BJ
FN_TIME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})_")
EXEMPT = ("回签", "签收", "指令转达", "收件", "转发", "前向更正", "监督反馈", "负责人指令",
          "负责人拍板", "任务转达", "任务改派", "升级指令", "流程固化", "对照竞赛回执")


def now_bj():
    return C.now_bj()


def die(msg):
    print(msg)
    return 2


def read_lenient(path, limit=None):
    with io.open(path, encoding="utf-8", errors="replace") as f:
        return f.read(limit) if limit else f.read()


def parse_date(s):
    m = re.match(r"\s*['\"]?(\d{4})-(\d{2})-(\d{2})", str(s or ""))
    return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def fn_time(path):
    """文件名开头的写作时刻（北京时间）；没有就返回 None。"""
    m = FN_TIME.match(os.path.basename(path))
    if not m:
        return None
    try:
        return datetime.datetime(*(int(x) for x in m.groups()), tzinfo=BJ)
    except ValueError:
        return None


def is_dialog(p):
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}_\d{4}_", "", os.path.basename(p))
    return any(t in stem[:16] for t in EXEMPT)


def backflow_path(fm):
    cb = fm.get("canonical_backflow")
    if isinstance(cb, dict):
        v = cb.get("path")
    elif isinstance(cb, str):
        v = cb
    else:
        v = None
    if isinstance(v, (list, tuple)):
        v = "；".join(str(x) for x in v if x)
    return C.fm_str(v)


def candidates(raw, report_path, docs_root, ws_root, prefix_map):
    """回流路径的候选落点：前缀映射（配置里的对端绝对路径前缀 → 本机工作区根）、docs/ 前缀、相对报告的 ./ ../、裸路径依次试三个根。"""
    out = []
    for one in re.split(r"[；;]", raw):
        one = one.strip().strip('"').strip("'")
        if not one:
            continue
        bare = re.sub(r"\s*[（(][^（()）]*[)）]\s*$", "", one).strip()
        for v in ([one, bare] if bare and bare != one else [one]):
            if C.is_remote_path(v):
                continue  # //主机/共享：不碰文件系统（会去连 SMB，复核 R2-2-2），当作找不到
            vv = v.replace("\\", "/")
            if vv.startswith("/") or re.match(r"^[A-Za-z]:/", vv):
                out.append(os.path.normpath(v))
                for pre, dst in prefix_map.items():
                    if vv.startswith(pre):
                        out.append(os.path.normpath(os.path.join(dst.replace("{ws_root}", ws_root), vv[len(pre):])))
                continue
            if vv.startswith("docs/"):
                out.append(os.path.normpath(os.path.join(ws_root, vv)))
            if vv.startswith("."):
                out.append(os.path.normpath(os.path.join(os.path.dirname(report_path), vv)))
            out += [os.path.normpath(os.path.join(docs_root, vv)), os.path.normpath(os.path.join(ws_root, vv)),
                    os.path.normpath(os.path.join(os.path.dirname(report_path), vv))]
    seen, res = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            res.append(c)
    return res


def scan(docs_root, days, todo_path, writer, since_date=None, w1=False):
    now = now_bj()
    since = parse_date(since_date or C.cfg("flow", "since_date", "2026-09-20"))
    if since is None:
        return die(f"--since-date 认不出：{since_date}")
    docs_root = os.path.abspath(docs_root)
    ws_root = os.path.dirname(docs_root)
    prefix_map = dict(C.cfg("flow", "path_prefix_map", {}) or {})
    wt = os.path.join(docs_root, "工作传递")
    canon_root = os.path.join(docs_root, "项目情况")
    if not os.path.isdir(wt):
        return die(f"找不到 {wt}")
    window_start = now - datetime.timedelta(days=days)
    findings, keys = [], []

    def add(tag, key, msg):
        """key＝稳定键（类别:路径），不含天数、条数这类会自己变的字；看门狗据此判断"是不是新发现"。"""
        findings.append((tag, msg))
        keys.append(f"{tag}:{key}")

    reports_all = [p for p in glob.glob(os.path.join(wt, "**", "*_交接报告.md"), recursive=True)
                   if not any(seg == "_archive" for seg in p.replace("\\", "/").split("/"))]

    def written_in_window(p):
        t = fn_time(p)
        if t is None:  # 文件名不带时刻的老件：退回看改动时刻
            t = datetime.datetime.fromtimestamp(os.path.getmtime(p), BJ)
        return t >= window_start and t.date() >= since

    # ---- W1 只改没写（默认关）----
    if w1:
        cutoff_ts = window_start.timestamp()
        canon_changed = [p for p in glob.glob(os.path.join(canon_root, "**", "*.md"), recursive=True)
                         if os.path.getmtime(p) >= cutoff_ts and "_archive" not in p and not os.path.basename(p).startswith("README")]
        reports_changed = [p for p in reports_all if os.path.getmtime(p) >= cutoff_ts]
        if canon_changed and not reports_changed:
            names = "、".join(os.path.relpath(p, docs_root).replace("\\", "/") for p in sorted(canon_changed)[:5])
            more = f" 等 {len(canon_changed)} 份" if len(canon_changed) > 5 else ""
            add("W1", "canon-without-report", f"近 {days} 天正本区改了 {names}{more}，工作传递却一份报告都没动——按三层规范，改正本的任务要留报告（纯格式修补或机器生成除外）")

    # ---- W2 只写没回流 ----
    for p in reports_all:
        rp = os.path.relpath(p, docs_root).replace("\\", "/")
        try:
            fm = C.fm_dict(read_lenient(p, 60000))
        except OSError:
            continue
        if C.fm_str(fm.get("status")) != "ready_for_review":
            continue
        fz = parse_date(C.fm_str(fm.get("frozen_at")))
        if not fz or (now.date() - fz).days < 2 or fz < since:
            continue
        raw = backflow_path(fm)
        if not raw or raw.lower().startswith(("none", "无", "not_applicable", "n/a")):
            continue
        if re.match(r"^(pending|待|tbd|todo)", raw, re.I):
            add("W2", rp, f"{rp} 冻结于 {fz}，回流目标还是占位值（{raw[:40]}）——回流没做")
            continue
        cands = candidates(raw, p, docs_root, ws_root, prefix_map)
        target = next((c for c in cands if os.path.isfile(c)), None)
        if target is None:
            if any(os.path.isdir(c) for c in cands):
                continue  # 指向目录：没法核对更新记录，不算发现
            add("W2", rp, f"{rp} 声明回流到 {raw[:80]}，但该文件不存在（试过 docs 根、工作区根、报告目录与配置里的路径映射）")
            continue
        try:
            ttext = read_lenient(target)
        except OSError:
            continue
        dates = [parse_date(d) for d in re.findall(r"^- (\d{4}-\d{2}-\d{2})", ttext, re.M)]
        dates += [parse_date(d) for d in re.findall(r"^updated:\s*['\"]?(\d{4}-\d{2}-\d{2})", ttext, re.M)]
        dates = [d for d in dates if d]
        if not dates:  # 台账/日志类文件没有「更新记录」节——用文件改动日（北京时间）兜底
            dates = [datetime.datetime.fromtimestamp(os.path.getmtime(target), BJ).date()]
        if max(dates) < fz:
            add("W2", rp, f"{rp} 冻结于 {fz}，回流正本 {raw[:80]} 的更新记录没有对应新条目（最后 {max(dates)}）")

    # ---- W3 碎片化（对话件豁免；按文件名里的写作时刻判窗口）----
    from collections import Counter
    tasks = [p for p in reports_all if not is_dialog(p) and written_in_window(p)]
    cnt = Counter(os.path.dirname(p) for p in tasks)
    for d, n in cnt.items():
        if n >= 3:
            names = "、".join(os.path.basename(p) for p in sorted(tasks) if os.path.dirname(p) == d)
            rd = os.path.relpath(d, docs_root).replace("\\", "/")
            add("W3", rd, f"{rd} 近 {days} 天新写了 {n} 份任务报告（{names}）——同主题的推进按规范应并进同一份 draft，先确认不是碎片化（回签/签收类对话件已不计）")

    # ---- 输出 ----（--todo 落全量；stdout 只显示前 20 条，末行 #keys 给出全量稳定键供看门狗比新增）
    head = ["现役", "", "# 工作传递规范扫描 · 待处理（脚本生成，勿手改）", "",
            f"生成：{now:%Y-%m-%d %H:%M} 北京 · {writer} · handoff_flow.py v{VERSION}",
            f"窗口：{days} 天 · 扫描根：{docs_root} · 起算：只查 {since} 之后冻结或写作的件（负责人 09-21 裁定）",
            "性质：**只提醒不拦人**（规范见 docs/工作传递/README.md「何时写、何时改」）；被点名的来源开工先看自己的条目。", ""]
    body = (["无发现。"] if not findings else [f"共 {len(findings)} 条：", ""] + [f"- **{t}** {m}" for t, m in findings])
    tail = ["", "## 更新记录", "", f"- {now:%Y-%m-%d %H:%M}：由 handoff_flow.py 自动重写（内容不变不重写）。"]
    text = "\n".join(head + body + tail) + "\n"
    shown = "\n".join(body[:22]) + (f"\n- ……其余 {len(findings) - 20} 条见 --todo 清单文件" if len(findings) > 20 else "")
    print(f"# 工作传递规范扫描（G-W，report-only）\n{shown}")
    print("#keys " + json.dumps(sorted(set(keys)), ensure_ascii=False))
    if todo_path:
        def _stable(s):
            return [x for x in s.split("\n") if not x.startswith(("生成：", "- 20"))]
        try:
            old = read_lenient(todo_path) if os.path.isfile(todo_path) else None
            if old is None or _stable(old) != _stable(text):
                C.atomic_write(todo_path, text, newline="\n")
                print(f"已写 {todo_path}（全量 {len(findings)} 条）")
            else:
                print(f"清单内容没变，未重写 {todo_path}（全量 {len(findings)} 条）")
        except (OSError, ValueError) as e:
            print(f"! 清单写入失败：{todo_path}：{e}")
            return 2
    return 1 if findings else 0


def main(a):
    if len(a) < 3 or a[1] != "scan":
        print(__doc__)
        return 2
    opt = lambda k, d: a[a.index(k) + 1] if k in a and len(a) > a.index(k) + 1 else d
    try:
        return scan(a[2], int(opt("--days", "2")), opt("--todo", None), opt("--writer", "handoff_flow.py"),
                    since_date=opt("--since-date", None), w1="--w1" in a)
    except Exception as e:  # 内部错误与"有发现"分开：看门狗据退出码 2 报"没跑成"
        import traceback
        print(f"! 规范扫描内部错误：{type(e).__name__}: {e}")
        traceback.print_exc(file=sys.stdout)
        return 2


if __name__ == "__main__":
    C.stdio_safe()
    sys.exit(main(sys.argv))
