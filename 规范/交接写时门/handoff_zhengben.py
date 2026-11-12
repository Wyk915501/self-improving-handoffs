#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""handoff_zhengben.py —— 正本写法检查（docs/项目情况，只报告不拦人，v1.1 · 2026-11-12）

来历：项目情况的正本容易越写越乱（状态篇上万字、经过往后堆、更新记录上百行），而自我改进循环原来只读交接报告，
看不到正本。这一块由自我改进循环兼管，不另起一套巡检；汇报方式：变差就弹一条知会，另有每周一条汇总。

分三层，判定都用 handoff_common 里同一套 zb_* 函数：
  ① 写的时候：写时门钩子（handoff_gate）对刚写进去的那几行给不拦人的提示，写的窗口当场就能改；
  ② 每 4 小时：看门狗调本脚本全量查一遍，写《正本写法-待处理》，记下每篇的类型、量值与每条发现；
  ③ 比一天前新写出来的（内容造成的，不含"放久了过期"），看门狗弹一条知会；每周一条汇总。

「变差」怎么算（v1.1，按 Fable 11-12 复查重写；v1.0 按每篇每条规则的处数比，改名、改登记类型、某轮读不到都会误弹，
一边清账一边新写又会互相抵消）：
  - 逐句的规则：按「规则＋原句」在全库数，比 20 小时以前那一轮多出来的才算新写的——与路径无关，挪篇改名不算；
    篇的类型变了（篇章表改登记）的篇这一轮只重建基线；读不到的篇沿用上一轮的记录，不记成 0。
  - 整篇的量（状态篇字数、篇幅、更新记录行数）：这一天里过了线，或已经超线又涨了一截（300 字／5KB／3 行）。
  - 规则版本（common.ZB_RULES_VERSION）变了：这一轮只重建基线，不判变差。
  - 近 7 天判出的变差留一份清单（现在改了没有），给处理页列出来。

只查脚本查得准的几条（规则表见 handoff_common.ZB_RULES）；要语义判断的（经过句式、跨篇重复）不查。
不查的地方：台账、历程只查篇幅与更新记录行数，历史篇（类型「历史」或文件头写冻结、作废）不查，
更新记录那一节、代码块、文件头不查写法。

  scan <docs_root> [--todo <清单md>] [--state <状态json>] [--writer <名>] [--now <带时区的时刻>] [--no-state]
       --now 给看门狗与测试用：按这个时刻算"一天前""今天"（默认现在）
  check <文件.md> [--docs <docs_root>]      只查一篇，打印发现（排查用）
退出码：0 无发现 · 1 有发现（只报告）· 2 用法、IO 或内部错误
scan 末行 `#zb {json}`：总数、各项目计数、比一天前新写出来的（regress）、近 7 天的变差与现状（recent）、一周对比（week）。
"""
import io, os, re, sys, glob, json, hashlib
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import handoff_common as C  # noqa: E402

VERSION = "1.1"
REGRESS_BASE_HOURS = 20   # 「变差」跟多久以前比：看门狗每 4 小时一轮，20 小时前那一轮约等于"一天前"
SNAP_KEEP_HOURS = 30      # 快照只留 30 小时（判变差只用 20 小时前那轮；周对比用每天的计数；一轮约 60KB）
DAILY_KEEP_DAYS = 60
NEW_DAYS = 7
RECENT_MAX = 30
METRIC = {"statesize": (0, "字"), "size": (1, "字节"), "log": (2, "行")}  # 整篇的量：在量值里的位置、单位
GROW = C.ZB_GROW                                                           # 已超线的篇一天里又涨了这么多才算变差
LIMIT = {"statesize": C.ZB_STATE_CHARS, "size": C.ZB_SIZE_KB * 1024, "log": C.ZB_LOG_LINES}


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def qid_of(rule, quote):
    """逐句发现的身份：规则＋原句（与路径无关）。"""
    return f"{rule}|{norm(quote)}"


def fp_of(key, rule, quote):
    """清单「近 7 天新出现」用的指纹：逐句的按规则＋原句（挪篇不算新），整篇的按规则＋篇。"""
    ident = f"{rule}|{norm(quote)}" if quote else f"{rule}|@{key}"
    return hashlib.sha1(ident.encode("utf-8", "replace")).hexdigest()[:12]


def metric_rules(kind):
    if kind == "历史":
        return ()
    return ("statesize", "log") if kind == "状态" else ("size", "log")


def fmt_metric(rule, v):
    return f"{v / 1024:,.0f}KB" if rule == "size" else f"{v:,} {METRIC[rule][1]}"


def load_done(docs):
    """读《正本写法-已处置》「## 已处置」节的表：| 篇 | 规则 | 原句短引 | 理由 |。
    篇写项目情况下的相对路径（某项目/0-当前状态.md），或指过去的 markdown 链接；规则写名字或代号。返回 [(篇, 规则代号, 短引)]。"""
    p = os.path.join(docs, "工作传递", C.ZB_DONE_NAME)
    if not os.path.isfile(p):
        return []
    names = {v[0]: k for k, v in C.ZB_RULES.items()}
    out, on = [], False
    for ln in C.read_text(p).split("\n"):
        if ln.startswith("## "):
            on = ln.strip().startswith("## 已处置")
            continue
        if not on or not ln.lstrip().startswith("|") or C.ZB_SEP_ROW.match(ln):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        page = cells[0].strip("`")
        ml = re.match(r"^\[[^\]]*\]\(<?([^)>]+)>?\)$", page)
        if ml:
            page = ml.group(1)
        page = page.replace("\\", "/")
        if "项目情况/" in page:
            page = page.split("项目情况/", 1)[1]
        rule = names.get(cells[1], cells[1] if cells[1] in C.ZB_RULES else None)
        if not rule or page in ("篇", ""):
            continue
        out.append((page, rule, norm(cells[2].strip("「」\"`")).rstrip("…")))
    return out


def exempted(done, key, rule, quote):
    q = norm(quote).rstrip("…")
    for page, r, short in done:
        if page != key or r != rule:
            continue
        if not short or short in ("—", "-", "无"):
            if not quote:
                return True
            continue
        if short in q or (q and q in short):
            return True
    return False


def collect(docs, today, prev_files=None):
    """全量查。返回 (发现列表, 每篇记录, 被已处置豁免的条数)。
    发现：dict(proj, key, rel, kind, rule, line, quote, detail, fp, qid)；每篇记录：{篇: {kind, m:[状态篇字数, 字节, 更新记录行数], q:[qid…]}}。
    读不到的篇沿用上一轮的记录（prev_files），标 carried——不记成 0，免得下一轮把它的问题当成新写的（Fable F3）。"""
    root = os.path.join(docs, "项目情况")
    if not os.path.isdir(root):
        raise FileNotFoundError(f"找不到 {root}")
    infos, found, files, n_ex = {}, [], {}, 0
    done = load_done(docs)
    for p in sorted(glob.glob(os.path.join(root, "**", "*.md"), recursive=True)):
        proj, rel, name = C.zb_project_of(p, docs)
        if not proj:
            continue
        key = rel if name == "总目录" else f"{name}/{rel}"
        if name not in infos:
            infos[name] = C.zb_readme_info(proj) if name != "总目录" else ({}, None)
        try:
            with io.open(p, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            if prev_files and key in prev_files:
                files[key] = dict(prev_files[key], carried=True)
            continue
        kind = C.zb_kind(rel, text[:2000], infos[name])
        rec = {"kind": kind, "m": list(C.zb_metrics(text, kind)), "q": []}
        for rule, line, quote, detail in C.zb_check(text, kind, os.path.dirname(p), today, docs):
            if exempted(done, key, rule, quote):
                n_ex += 1
                continue
            q = qid_of(rule, quote) if (quote and rule not in METRIC) else None
            if q:
                rec["q"].append(q)
            found.append({"proj": name, "key": key, "rel": rel, "kind": kind, "rule": rule, "line": line,
                          "quote": quote, "detail": detail, "fp": fp_of(key, rule, quote), "qid": q})
        files[key] = rec
    return found, files, n_ex


def proj_of(key):
    return key.split("/", 1)[0] if "/" in key else "总目录"


def hook_hits(hours=24, now_utc=None):
    """写时门近 N 小时对每篇正本当场提示了几次（logs/gate_hits.jsonl 里 kind=zhengben 的行，file＝项目/篇）。"""
    now_utc = now_utc or datetime.now(timezone.utc)
    out = Counter()
    try:
        with io.open(C.P.gate_hits, encoding="utf-8") as f:
            for ln in f:
                try:
                    h = json.loads(ln)
                except ValueError:
                    continue
                t = C.to_bj(h.get("utc")) if isinstance(h, dict) else None
                if t and h.get("kind") == "zhengben" and now_utc - t <= timedelta(hours=hours):
                    out[str(h.get("file", ""))] += 1
    except OSError:
        pass
    return out


def find_regress(found, files, base_files):
    """比一天前那一轮新写出来的。返回变差条目列表（每篇每条规则一条）。"""
    changed = {k for k, v in files.items() if k in base_files and base_files[k].get("kind") != v.get("kind")}
    content = lambda q: C.ZB_RULES.get(q.split("|", 1)[0], ("", "", False))[2]
    base_ms = Counter(q for k, v in base_files.items() if k not in changed for q in v.get("q") or [] if content(q))
    cur_ms = Counter(q for k, v in files.items() if k not in changed for q in v.get("q") or [] if content(q))
    per_file = lambda fs, k, q: sum(1 for x in (fs.get(k) or {}).get("q") or [] if x == q)
    out = {}
    for q, n in cur_ms.items():
        extra = n - base_ms.get(q, 0)
        if extra <= 0:
            continue
        inst = [f for f in found if f["qid"] == q and f["key"] not in changed]
        # 先算到"这一篇里这句变多了"或"新出现的篇"头上
        inst.sort(key=lambda f: not (f["key"] not in base_files or per_file(files, f["key"], q) > per_file(base_files, f["key"], q)))
        for f in inst[:extra]:
            it = out.setdefault((f["key"], f["rule"]), {"proj": f["proj"], "key": f["key"], "rule": f["rule"], "type": "line",
                                                        "name": C.ZB_RULES[f["rule"]][0], "n_new": 0, "line": f["line"],
                                                        "eg": f["quote"], "ids": []})
            it["n_new"] += 1
            it["ids"].append(f"{q}|{f['key']}")
    for (key, rule), it in out.items():
        it["before"] = sum(1 for x in (base_files.get(key) or {}).get("q") or [] if x.startswith(rule + "|"))
        it["now"] = sum(1 for x in files[key].get("q") or [] if x.startswith(rule + "|"))
    items = list(out.values())
    vanished = [k for k in base_files if k not in files]
    for key, v in files.items():
        if key in changed or v.get("carried") or v.get("kind") in ("台账", "历程"):  # 只增的台账天天在长，不按"涨了"判写坏
            continue
        bm = (base_files.get(key) or {}).get("m")
        if bm is None:  # 新出现的篇：同样大小的篇刚好消失了＝改名挪位置，跟它比
            twin = next((k for k in vanished if (base_files[k].get("m") or [None, None])[1] == v["m"][1]), None)
            bm = base_files[twin]["m"] if twin else [0, 0, 0]
        for rule in metric_rules(v["kind"]):
            i = METRIC[rule][0]
            now_v, b_v = v["m"][i], bm[i]
            if now_v > LIMIT[rule] and (b_v <= LIMIT[rule] or now_v - b_v >= GROW[rule]):
                items.append({"proj": proj_of(key), "key": key, "rule": rule, "type": "metric", "name": C.ZB_RULES[rule][0],
                              "before": b_v, "now": now_v, "line": 0, "eg": f"{fmt_metric(rule, b_v)}→{fmt_metric(rule, now_v)}",
                              "ids": [f"m|{rule}|{key}"]})
    return sorted(items, key=lambda x: (x["key"], x["rule"]))


def still_there(item, found, files):
    """近 7 天判出的一条变差，现在还在不在。"""
    if item.get("type") == "metric":
        v = files.get(item["key"])
        if not v:
            return False
        now_v = v["m"][METRIC[item["rule"]][0]]
        return now_v > LIMIT[item["rule"]] and now_v > item.get("before", 0)
    cur = {f"{f['qid']}|{f['key']}" for f in found if f["qid"]}
    cur |= {f"{q}|{k}" for k, v in files.items() if v.get("carried") for q in v.get("q") or []}  # 读不到的篇按上一轮算
    return any(i in cur for i in item.get("ids") or [])


def update_state(st, found, files, now_utc, today):
    """记这一轮并判变差。返回 (regress, week, new_fps, recent, rebased)。"""
    snaps = [s for s in (st.get("snaps") or []) if isinstance(s, dict) and s.get("at") and isinstance(s.get("files"), dict)]
    base = None
    for s in snaps:
        t = C.to_bj(s["at"])
        if t and t <= now_utc - timedelta(hours=REGRESS_BASE_HOURS) and (base is None or t > C.to_bj(base["at"])):
            base = s
    rebased = bool(base) and base.get("v") != C.ZB_RULES_VERSION  # 规则版本变了：这一轮只重建基线
    regress = find_regress(found, files, base["files"]) if base and not rebased else []
    hits = hook_hits(24, now_utc)
    for it in regress:
        it["hook_hits"] = hits.get(it["key"], 0)
    # 近 7 天的变差：新判出的加进去，每条看现在还在不在
    recent = [r for r in (st.get("recent") or []) if isinstance(r, dict) and str(r.get("date", "")) >= f"{today - timedelta(days=NEW_DAYS)}"]
    known = {i for r in recent for i in r.get("ids") or []}
    for it in regress:
        if not set(it["ids"]) <= known:
            recent.append({k: it[k] for k in ("proj", "key", "rule", "type", "name", "before", "now", "line", "eg", "ids", "hook_hits")}
                          | {"date": f"{today}", "at": f"{now_utc.astimezone(C.BJ):%m-%d %H:%M}"})
    for r in recent:
        r["fixed"] = not still_there(r, found, files)
    st["recent"] = recent[-RECENT_MAX:]
    snaps.append({"at": now_utc.isoformat(), "v": C.ZB_RULES_VERSION, "files": files})
    dated = sorted((s for s in snaps if C.to_bj(s["at"])), key=lambda s: C.to_bj(s["at"]))
    cut_t = now_utc - timedelta(hours=SNAP_KEEP_HOURS)
    older = [s for s in dated if C.to_bj(s["at"]) < cut_t]
    # 30 小时内的都留，再多留一轮更早的兜底：机器关过一天，下一轮也还有"一天前"可比（不然变差整轮漏判）
    st["snaps"] = older[-1:] + [s for s in dated if C.to_bj(s["at"]) >= cut_t]
    # 每天的各项目计数（周汇总用）：内容造成的、全部
    daily = st.get("daily") if isinstance(st.get("daily"), dict) else {}
    day = {}
    for f in found:
        d = day.setdefault(f["proj"], {"content": 0, "all": 0})
        d["all"] += 1
        d["content"] += bool(C.ZB_RULES[f["rule"]][2])
    daily[f"{today}"] = day
    st["daily"] = {d: v for d, v in daily.items() if d >= f"{today - timedelta(days=DAILY_KEEP_DAYS)}"}
    # 第一次出现的日子；第一轮建基线（那天就有的算存量，不算新出现）
    fs = st.get("first_seen") if isinstance(st.get("first_seen"), dict) else {}
    st.setdefault("base_date", f"{today}")
    if rebased:
        st["base_date"] = f"{today}"
    cur = {f["fp"] for f in found}
    for f in found:
        fs.setdefault(f["fp"], f"{today}")
    st["first_seen"] = {k: v for k, v in fs.items() if k in cur}
    new_fps = {k for k, v in st["first_seen"].items() if v > st["base_date"] and v >= f"{today - timedelta(days=NEW_DAYS)}"}
    week = None
    for back in (7, 6, 8, 9, 10):
        d0 = f"{today - timedelta(days=back)}"
        if d0 in st["daily"]:
            then, now_ = st["daily"][d0], st["daily"][f"{today}"]
            week = {"since": d0, "projects": {p: {"then": then.get(p, {}).get("content", 0), "now": now_.get(p, {}).get("content", 0)}
                                              for p in sorted(set(then) | set(now_))},
                    "then": sum(v.get("content", 0) for v in then.values()), "now": sum(v.get("content", 0) for v in now_.values())}
            break
    return regress, week, new_fps, st["recent"], rebased


def md_link(key, text=None):
    path = "../项目情况/" + key
    tgt = f"<{path}>" if re.search(r"[\s()]", path) else path
    return f"[{text or key.rsplit('/', 1)[-1]}]({tgt})"


def render(found, new_fps, n_ex, writer, now, base_date):
    projs = sorted({f["proj"] for f in found}, key=lambda p: (p == "总目录", p))
    head = ["现役", "", "# 正本写法 · 待处理（脚本生成，勿手改）", "",
            f"生成：{now:%Y-%m-%d %H:%M} 北京 · {writer} · handoff_zhengben.py v{VERSION}", "",
            "这是线索，不是结论：回原文看那一行再改。规则见文末「规则说明」；"
            "只查脚本查得准的几条，见文末「规则说明」。",
            "",
            "谁看：各项目正本的写者，开工先看自己项目那一节，「近 7 天新出现」的先改。"
            f"存量（{base_date} 开始查那天就有的）不催，清账或顺手时改。",
            "",
            f"不成立的：在[正本写法-已处置]({C.ZB_DONE_NAME})的表里登记一行（哪篇、哪条规则、原句短引、理由），下一轮就不再列。", ""]
    body = []
    if not found:
        body += ["无发现。", ""]
    else:
        body += ["## 总览", "", "| 项目 | 现存（其中超 14 天没重核的） | 近 7 天新出现 |", "|---|---|---|"]
        for p in projs:
            fp_ = [f for f in found if f["proj"] == p]
            st_ = sum(1 for f in fp_ if f["rule"] == "stale")
            nw = sum(1 for f in fp_ if f["fp"] in new_fps)
            body.append(f"| {p} | {len(fp_)}" + (f"（{st_}）" if st_ else "") + f" | {nw or '—'} |")
        body.append("")
        for p in projs:
            fp_ = [f for f in found if f["proj"] == p]
            body += [f"## {p}", ""]
            nw = [f for f in fp_ if f["fp"] in new_fps]
            if nw:
                body.append("近 7 天新出现：")
                body.append("")
                for f in nw[:30]:
                    where = f"第 {f['line']} 行 · " if f["line"] else ""
                    q = f"「{f['quote']}」" if f["quote"] else f["detail"]
                    body.append(f"- {md_link(f['key'])} {where}{C.ZB_RULES[f['rule']][0]}：{q} → {C.ZB_RULES[f['rule']][3]}")
                if len(nw) > 30:
                    body.append(f"- ……另有 {len(nw) - 30} 条")
                body.append("")
            old = [f for f in fp_ if f["fp"] not in new_fps]
            if old:
                body.append("存量：")
                body.append("")
                groups = {}
                for f in old:
                    groups.setdefault((f["key"], f["rule"]), []).append(f)
                for (key, rule), fs in sorted(groups.items(), key=lambda kv: (kv[0][0], list(C.ZB_RULES).index(kv[0][1]))):
                    name = C.ZB_RULES[rule][0]
                    if not fs[0]["quote"]:  # 整篇的事（篇幅、更新记录行数）：写补充说明
                        body.append(f"- {md_link(key)} · {name}：{fs[0]['detail']}")
                        continue
                    egs = "、".join(f"第 {f['line']} 行「{f['quote']}」" for f in fs[:2])
                    body.append(f"- {md_link(key)} · {name} × {len(fs)}：{egs}" + ("等" if len(fs) > 2 else ""))
                body.append("")
    if n_ex:
        body += [f"另有 {n_ex} 条已登记为不成立、不再列出（见[正本写法-已处置]({C.ZB_DONE_NAME})）。", ""]
    body += ["## 规则说明", "", "| 规则 | 出处 | 怎么改 |", "|---|---|---|"]
    body += [f"| {v[0]} | {v[1]} | {v[3]} |" for v in C.ZB_RULES.values()]
    body += ["", "台账、历程只查篇幅与更新记录行数；类型为「历史」或文件头写冻结、作废的篇不查；更新记录那一节、代码块、文件头不查写法"
                 "。", ""]
    tail = ["## 更新记录", "", f"- {now:%Y-%m-%d %H:%M}：由 handoff_zhengben.py 自动重写（内容不变不重写）。"]
    return "\n".join(head + body + tail) + "\n"


def write_todo(todo_path, text):
    def _stable(s):
        return [x for x in s.split("\n") if not x.startswith(("生成：", "- 20"))]
    old = C.read_text(todo_path) if os.path.isfile(todo_path) else None
    if old is None or _stable(old) != _stable(text):
        C.atomic_write(todo_path, text, newline="\n")
        return True
    return False


def scan(docs, todo_path=None, state_path=None, writer="handoff_zhengben.py", today=None, use_state=True, now_utc=None):
    docs = os.path.abspath(docs)
    now_utc = now_utc or datetime.now(timezone.utc)
    now = now_utc.astimezone(C.BJ)
    today = today or now.date()
    st = C.load_json(state_path, {}) if (use_state and state_path and os.path.isfile(state_path)) else {}
    st = st if isinstance(st, dict) else {}
    prev = max((x for x in st.get("snaps") or [] if isinstance(x, dict) and isinstance(x.get("files"), dict)),
               key=lambda x: str(x.get("at", "")), default=None)
    found, files, n_ex = collect(docs, today, prev["files"] if prev else None)
    regress, week, new_fps, recent, rebased = update_state(st, found, files, now_utc, today)
    text = render(found, new_fps, n_ex, writer, now, st.get("base_date", f"{today}"))
    wrote = None
    if todo_path:
        wrote = write_todo(todo_path, text)
    if use_state and state_path:
        os.makedirs(os.path.dirname(os.path.abspath(state_path)), exist_ok=True)
        C.save_json(state_path, st)
    projects = {}
    for f in found:
        d = projects.setdefault(f["proj"], {"n": 0, "stale": 0, "new7": 0})
        d["n"] += 1
        d["stale"] += f["rule"] == "stale"
        d["new7"] += f["fp"] in new_fps
    n_stale = sum(1 for f in found if f["rule"] == "stale")
    summary = {"n": len(found), "n_stale": n_stale, "n_content": len(found) - n_stale, "new7": len(new_fps), "exempt": n_ex,
               "projects": projects, "regress": regress[:20], "n_regress": len(regress), "week": week,
               "recent": recent, "rebased": rebased, "rules_version": C.ZB_RULES_VERSION, "base_date": st.get("base_date")}
    print(f"# 正本写法检查（report-only）：{len(found)} 条（其中超 14 天没重核 {n_stale}），近 7 天新出现 {len(new_fps)}，"
          f"比一天前新写出来 {len(regress)} 处" + (f"；已处置豁免 {n_ex}" if n_ex else "")
          + ("；规则版本变了，这一轮只重建基线" if rebased else ""))
    for p, d in sorted(projects.items(), key=lambda kv: -kv[1]["n"]):
        print(f"  {p}：{d['n']}" + (f"（新 {d['new7']}）" if d["new7"] else ""))
    if todo_path:
        print(("已写 " if wrote else "清单内容没变，未重写 ") + todo_path)
    print("#zb " + json.dumps(summary, ensure_ascii=False))
    return 1 if found else 0


def main(a):
    opt = lambda k, d: a[a.index(k) + 1] if k in a and len(a) > a.index(k) + 1 else d
    try:
        if len(a) >= 3 and a[1] == "scan":
            nw = opt("--now", None)
            now_utc = datetime.fromisoformat(nw).astimezone(timezone.utc) if nw else None
            return scan(a[2], opt("--todo", None), opt("--state", C.P.zb_state), opt("--writer", "handoff_zhengben.py"),
                        use_state="--no-state" not in a, now_utc=now_utc)
        if len(a) >= 3 and a[1] == "check":
            r = C.zb_check_file(a[2], docs=opt("--docs", None))
            if r is None:
                print(f"不在检查范围（docs/项目情况 下、不在 _archive/ 里的 .md）：{a[2]}")
                return 2
            name, rel, kind, found = r
            print(f"{name}/{rel}（类型：{kind}）：{len(found)} 条")
            for rule, line, quote, detail in found:
                print(f"  第 {line} 行 · {C.ZB_RULES[rule][0]}：{quote or detail}")
            return 1 if found else 0
    except Exception as e:  # 内部错误与"有发现"分开：看门狗据退出码 2 报"没跑成"
        import traceback
        print(f"! 正本写法检查内部错误：{type(e).__name__}: {e}")
        traceback.print_exc(file=sys.stdout)
        return 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    C.stdio_safe()
    sys.exit(main(sys.argv))
