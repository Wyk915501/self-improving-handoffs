# -*- coding: utf-8 -*-
"""正本写法检查（handoff_common.zb_* ＋ handoff_zhengben.py ＋ 写时门钩子的正本分支）离线用例。临时 docs 树，不碰真树。
日期纪律：夹具里的时点一律相对固定的「现在」生成，不依赖真实今天。"""
import io, os, re, sys, json, shutil, tempfile, subprocess, importlib.util
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
for _k in [k for k in os.environ if k.upper().startswith(("HANDOFF_", "HN_", "HL_", "HZ_"))]:
    os.environ.pop(_k)
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
ROOT = tempfile.mkdtemp(prefix="hz_")
os.environ["HANDOFF_TOOLS_DIR"] = os.path.join(ROOT, "tools")
os.environ["HZ_STATE_PATH"] = os.path.join(ROOT, "zb_state.json")
sys.path.insert(0, SRC)


def load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SRC, fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = load("handoff_common", "handoff_common.py")
sys.modules["handoff_common"] = C
Z = load("zb", "handoff_zhengben.py")
G = load("gate", "handoff_gate.py")

NOW = datetime(2026, 11, 12, 4, 0, tzinfo=timezone.utc)   # 北京 11-12 12:00
TODAY = NOW.astimezone(C.BJ).date()
DOCS = os.path.join(ROOT, "docs")
PQ = os.path.join(DOCS, "项目情况")
STATE = os.environ["HZ_STATE_PATH"]
TODO = os.path.join(DOCS, "工作传递", C.ZB_TODO_NAME)
results = []


def ok(name, cond):
    results.append((name, bool(cond)))
    print(("  PASS " if cond else "  FAIL ") + name)


def w(rel, text):
    p = os.path.join(DOCS, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="utf-8", newline="\n").write(text)
    return p


def md(days_ago):
    d = TODAY - timedelta(days=days_ago)
    return f"{d:%m-%d}"


def rules(found):
    return [f[0] for f in found]


README = """现役

# 甲项目

project_state_owner: 0-当前状态.md

| 篇 | 类型 | 给谁看、只管什么 | 不写什么 |
|---|---|---|---|
| [0-当前状态](0-当前状态.md) | 状态 | 现状 | 经过 |
| [决定记录](决定记录.md) | 台账 | 定过什么 | 细节 |
| [附件/](附件/README.md) | 历史 | 冻结原文 | 现状 |
| [附件/明细-附/](附件/明细-附/README.md) | 台账 | 随明细 | 现状 |
"""

print("== K 类型识别 ==")
w("项目情况/甲项目/README.md", README)
w("项目情况/甲项目/工具.py", "print(1)\n")
info = C.zb_readme_info(os.path.join(PQ, "甲项目"))
ok("K1 读到篇章表与 project_state_owner；子目录整行登记认成目录", info[1] == "0-当前状态.md" and info[0].get("附件/") == "历史"
   and info[0].get("附件/明细-附/") == "台账")
ok("K2 README、状态、台账、子目录最长前缀", C.zb_kind("README.md", "", info) == "README" and C.zb_kind("0-当前状态.md", "", info) == "状态"
   and C.zb_kind("决定记录.md", "", info) == "台账" and C.zb_kind("附件/旧稿.md", "", info) == "历史"
   and C.zb_kind("附件/明细-附/一段.md", "", info) == "台账")
ok("K3 文件头冻结／作废、名字带整合前原文的当历史；没登记的当专题", C.zb_kind("x.md", "冻结\n\n# x", info) == "历史"
   and C.zb_kind("x.md", "---\nstatus: 作废\n---", info) == "历史" and C.zb_kind("2-方案整合前全文（某日版）.md", "", info) == "历史"
   and C.zb_kind("方案.md", "现役\n", info) == "专题" and C.zb_kind("历程.md", "", info) == "历程")
ok("K4 范围：项目情况下的 md 才算，_archive 与别处不算", C.is_zb_target(os.path.join(PQ, "甲项目", "方案.md"))
   and not C.is_zb_target(os.path.join(PQ, "甲项目", "_archive", "x.md"))
   and not C.is_zb_target(os.path.join(DOCS, "工作传递", "x.md"))
   and C.zb_project_of(os.path.join(PQ, "速览.md"), DOCS)[2] == "总目录")

print("== R 规则 ==")
fdir = os.path.join(PQ, "甲项目")
t = "现役\n\n# 方案\n\n引用 `../甲项目/工具.py` 和 `工具.py` 和 `docs/项目情况/` 和 `/root/x/y.py` 和 `py -X utf8 工具.py`\n"
f = C.zb_check(t, "专题", fdir, TODAY, DOCS)
ok("R1 反引号路径：只报本机实存、带目录的文件；裸文件名、目录、/ 开头、带空格的命令不报", rules(f) == ["path"] and "工具.py" in f[0][2])
t = "现役\n\n# 方案\n\n本篇是唯一入口。\n价格以本篇为准。\n见[总方案](x.md)。\n标签表（唯一真源）。\n"
f = C.zb_check(t, "专题", fdir, TODAY, DOCS)
ok("R2 自称唯一：本篇是唯一、以本篇为准报；链接文字、说别的东西是唯一真源不报", rules(f) == ["self", "self"])
ok("R2b README 可以宣布唯一", C.zb_check(t, "README", fdir, TODAY, DOCS) == [])
t = "现役\n\n# 方案\n\n- 结论甲（10-08 更正：原数错了）。\n- 10-10 新增：一条任务\n"
f = C.zb_check(t, "专题", fdir, TODAY, DOCS)
ok("R3 往后堆：「MM-DD 更正：」报，「MM-DD 新增：」不报", rules(f) == ["pile"])
t = "现役\n\n# 方案\n\n## 甲（10-14 提出；10-15 完成）\n\n## 乙（09-21 至 09-23）\n\n## 丙 v1→v2 变更\n\n## 丁 最终版\n\n## 戊（10-10）\n"
f = C.zb_check(t, "专题", fdir, TODAY, DOCS)
ok("R4 标题：两个日期、版本流水、最终版报；日期区间、单个日期不报", [x[1] for x in f] == [5, 9, 11])
st_text = f"""现役

# 当前状态

- 训练跑完（{md(1)} 查）
  - 子条目跟着父条目的时点
- 没写时点的一条
- 待核：没写时点但标了待核
- 很久以前的一条（{md(20)} 查）

## 部署（{md(2)} 查）

| 项 | 现状 |
|---|---|
| 网站 | 跑着 |

还要做的（{md(1)} 重排）：

按顺序：
1. 第一步做什么事情
2. 第二步做什么事情

```
- 代码块里的不算
```

## 更新记录

- {TODAY - timedelta(days=30)}：建档
"""
f = C.zb_check(st_text, "状态", fdir, TODAY, DOCS)
ok("R5 状态篇：缺时点报一条，子条目、标题与说明段带时点的、待核、代码块、更新记录不报", rules(f).count("notime") == 1
   and [x for x in f if x[0] == "notime"][0][2].startswith("没写时点的一条"))
ok("R6 状态篇：超 14 天的报 stale，带天数", rules(f).count("stale") == 1 and "20 天前" in [x for x in f if x[0] == "stale"][0][3])
big_state = "现役\n\n# 当前状态\n\n" + "".join(f"- 第{i}条现状说明文字写得很长很长很长（{md(1)} 查）\n" for i in range(150))
ok("R7 状态篇超 2,000 字（只数汉字）报 statesize", "statesize" in rules(C.zb_check(big_state, "状态", fdir, TODAY, DOCS)))
log_text = "现役\n\n# 专题\n\n正文。\n\n## 更新记录\n\n" + "".join(f"- 2026-10-{i:02d}：改了一处\n" for i in range(1, 13))
f = C.zb_check(log_text, "专题", fdir, TODAY, DOCS)
ok("R8 更新记录超 10 行报 log（行号＝那一节标题）", rules(f) == ["log"] and f[0][1] == 7 and "12 行" in f[0][3])
big = "现役\n\n# 台账\n\n" + ("| 1 | 本篇是唯一入口 | `工具.py` |\n" * 3000)
f = C.zb_check(big, "台账", fdir, TODAY, DOCS)
ok("R9 台账：只查篇幅与更新记录，不查写法", rules(f) == ["size"])
ok("R10 历史：什么都不查", C.zb_check(big, "历史", fdir, TODAY, DOCS) == [])
fm = "---\nstatus: 现役\nnote: 本篇是唯一入口\n---\n\n# x\n"
ok("R11 文件头里的字不查", C.zb_check(fm, "专题", fdir, TODAY, DOCS) == [])
ok("R12 编号「0-36」不当时点；10-08、2026-10-08、截至算", not C.ZB_TIMEPT.search("任务 0-36 没做")
   and C.ZB_TIMEPT.search("10-08 查") and C.ZB_TIMEPT.search("截至本周"))
ok("R13 每条规则都有名字、出处、怎么改", all(len(v) == 4 and v[0] and v[1] and v[3] for v in C.ZB_RULES.values()))

print("== S 扫描、清单、变差 ==")
w("项目情况/甲项目/0-当前状态.md", f"现役\n\n# 当前状态\n\n- 训练跑完（{md(1)} 查）\n- 没写时点的一条\n")
w("项目情况/甲项目/方案.md", "现役\n\n# 方案\n\n本篇是唯一入口。\n")
w("项目情况/甲项目/附件/旧稿.md", "现役\n\n# 旧稿\n\n本篇是唯一入口。\n")
w("项目情况/乙项目/README.md", "现役\n\n# 乙项目\n")
w("项目情况/乙项目/专题.md", "现役\n\n# 专题\n\n正文。\n")
t0 = NOW - timedelta(days=8)
rc = Z.scan(DOCS, TODO, STATE, "测试", now_utc=t0)
st = json.load(io.open(STATE, encoding="utf-8"))
todo = io.open(TODO, encoding="utf-8").read()
ok("S1 首轮：有发现退出 1，清单落盘，第一行状态词「现役」，附件里的历史篇不列", rc == 1 and todo.startswith("现役\n")
   and "旧稿" not in todo and "方案.md" in todo)
ok("S2 清单链接指回正本、写明「这是线索」和怎么消", "](../项目情况/甲项目/方案.md)" in todo and "这是线索，不是结论" in todo
   and C.ZB_DONE_NAME in todo)
ok("S3 首轮建基线：基线那天就有的不算新出现", st.get("base_date") == f"{t0.astimezone(C.BJ):%Y-%m-%d}" and "近 7 天新出现：" not in todo)
# 7 天后同一天里两轮：第二轮跟 20 小时前那轮比
rc = Z.scan(DOCS, TODO, STATE, "测试", now_utc=NOW - timedelta(days=1))
w("项目情况/乙项目/专题.md", "现役\n\n# 专题\n\n正文，以本篇为准。\n\n见 `../甲项目/工具.py`。\n")
w("项目情况/甲项目/0-当前状态.md", f"现役\n\n# 当前状态\n\n- 训练跑完（{md(1)} 查）\n- 没写时点的一条\n- 又一条没写时点的\n- 老条目（{md(30)} 查）\n")
import contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = Z.scan(DOCS, TODO, STATE, "测试", now_utc=NOW)
out = buf.getvalue()
zs = json.loads(re.search(r"^#zb (\{.*\})$", out, re.M).group(1))
reg = {(x["key"], x["rule"]): x for x in zs["regress"]}
ok("S4 比一天前多出来的：新写的缺时点、自称唯一、反引号路径都算", ("甲项目/0-当前状态.md", "notime") in reg
   and reg[("甲项目/0-当前状态.md", "notime")]["before"] == 1 and reg[("甲项目/0-当前状态.md", "notime")]["now"] == 2
   and ("乙项目/专题.md", "self") in reg and ("乙项目/专题.md", "path") in reg)
ok("S5 放久了过期（stale）不算变差", not any(r == "stale" for _k, r in reg))
ok("S6 新出现（7 天内、基线之后）记进清单的「近 7 天新出现」", zs["new7"] >= 3 and "近 7 天新出现：" in io.open(TODO, encoding="utf-8").read())
ok("S7 #zb 带各项目计数与一周对比", zs["projects"]["甲项目"]["n"] >= 3 and zs["week"] and zs["week"]["since"] in (f"{TODAY - timedelta(days=7)}", f"{TODAY - timedelta(days=8)}")
   and zs["week"]["projects"]["乙项目"]["then"] == 0 and zs["week"]["projects"]["乙项目"]["now"] == 2)
# 挪篇：项目总数不变，不算变差（基线＝上面 NOW 那一轮，乙项目那两处已经在了）
os.replace(os.path.join(PQ, "乙项目", "专题.md"), os.path.join(PQ, "乙项目", "改名后.md"))
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    Z.scan(DOCS, TODO, STATE, "测试", now_utc=NOW + timedelta(hours=21))
zs2 = json.loads(re.search(r"^#zb (\{.*\})$", buf.getvalue(), re.M).group(1))
ok("S8 改名挪篇：项目里同一规则总数没涨，不报变差", not any(x["key"].startswith("乙项目/") for x in zs2["regress"]))
# 已处置登记：豁免这一条
w("工作传递/" + C.ZB_DONE_NAME, "现役\n\n# 正本写法 · 已处置\n\n## 已处置\n\n| 篇 | 规则 | 原句短引 | 理由 |\n|---|---|---|---|\n"
  "| [改名后](../项目情况/乙项目/改名后.md) | 自称唯一、最新或以本篇为准 | 以本篇为准 | 这里说的是价格表本身 |\n")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    Z.scan(DOCS, TODO, STATE, "测试", now_utc=NOW + timedelta(hours=22))
zs3 = json.loads(re.search(r"^#zb (\{.*\})$", buf.getvalue(), re.M).group(1))
ok("S9 已处置登记的那一条不再列、计数里说豁免了几条", zs3["exempt"] == 1 and zs3["projects"]["乙项目"]["n"] == 1
   and "另有 1 条已登记为不成立" in io.open(TODO, encoding="utf-8").read())
mt = os.path.getmtime(TODO)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    Z.scan(DOCS, TODO, STATE, "测试", now_utc=NOW + timedelta(hours=22, minutes=5))
ok("S10 内容没变不重写清单", "清单内容没变" in buf.getvalue() and os.path.getmtime(TODO) == mt)
st = json.load(io.open(STATE, encoding="utf-8"))
ok("S11 快照：48 小时内每轮都留，更早的每天一轮；每天计数留着做周对比", len(st["snaps"]) <= 8 and len(st["daily"]) >= 3)
r = subprocess.run([sys.executable, "-X", "utf8", "-B", os.path.join(SRC, "handoff_zhengben.py"), "scan", os.path.join(ROOT, "没有")],
                   capture_output=True, text=True, encoding="utf-8")
ok("S12 docs 下没有项目情况目录：退出 2（没跑成，和有发现分开）", r.returncode == 2 and "内部错误" in r.stdout)
r = subprocess.run([sys.executable, "-X", "utf8", "-B", os.path.join(SRC, "handoff_zhengben.py"), "check",
                    os.path.join(PQ, "甲项目", "0-当前状态.md"), "--docs", DOCS], capture_output=True, text=True, encoding="utf-8")
ok("S13 check 单篇：列出类型与发现", r.returncode == 1 and "类型：状态" in r.stdout and "没写时点" in r.stdout)

print("== H 写时门钩子 ==")
P0 = os.path.join(PQ, "甲项目", "钩子.md")
old = f"现役\n\n# 钩子\n\n本篇是唯一入口。\n"
new = old + "又一处：以本页为准。\n见 `../甲项目/工具.py`。\n"
io.open(P0, "w", encoding="utf-8", newline="\n").write(new)
h = G.zb_hints(P0, {"file_path": P0}, {"type": "update", "originalFile": old})
ok("H1 只报这次新写的行（原有的「本篇是唯一入口」不报）", len(h) == 2 and all("唯一入口" not in x for x in h)
   and any("以本页为准" in x for x in h) and any("工具.py" in x for x in h))
h = G.zb_hints(P0, {"file_path": P0, "new_string": "见 `../甲项目/工具.py`。"}, {})
ok("H2 没有原件：按这次的 new_string 认新行", len(h) == 1 and "工具.py" in h[0])
io.open(P0, "w", encoding="utf-8", newline="\n").write(log_text)
h = G.zb_hints(P0, {"file_path": P0}, {"type": "create"})
ok("H3 新建：整篇都算新写；更新记录一写就超线也提", any("更新记录超 10 行" in x for x in h))
h = G.zb_hints(P0, {"file_path": P0}, {"type": "update", "originalFile": log_text.replace("- 2026-10-12：改了一处\n", "")})
ok("H4 更新记录已经超线、这次又加一行：不念存量", not any("更新记录" in x for x in h))
small = "现役\n\n# 当前状态\n\n- 一条（" + md(1) + " 查）\n"
io.open(os.path.join(PQ, "甲项目", "0-当前状态.md"), "w", encoding="utf-8", newline="\n").write(big_state)
h = G.zb_hints(os.path.join(PQ, "甲项目", "0-当前状态.md"), {}, {"type": "update", "originalFile": small})
ok("H5 状态篇这一次写过了 2,000 字：提，并说写完多少字", any("状态篇超 2,000 字" in x and "这次写完约" in x for x in h))
h = G.zb_hints(os.path.join(PQ, "甲项目", "0-当前状态.md"), {}, {"type": "update", "originalFile": big_state[:-60]})
ok("H6 已经超线、只多了几十字：不提篇幅", not any("2,000 字" in x for x in h))


def hook(payload, strict=False):
    return subprocess.run([sys.executable, "-X", "utf8", "-B", os.path.join(SRC, "handoff_gate.py")] + (["--hook-strict"] if strict else ["--hook"]),
                          input=json.dumps(payload, ensure_ascii=False), capture_output=True, text=True, encoding="utf-8")


io.open(P0, "w", encoding="utf-8", newline="\n").write(new)
r = hook({"tool_input": {"file_path": P0}, "tool_response": {"filePath": P0, "type": "update", "originalFile": old}})
j = json.loads(r.stdout)
ok("H7 钩子出 JSON：additionalContext 带提示、不 block、systemMessage 一句话", r.returncode == 0 and "decision" not in j
   and "正本写法提示" in j["hookSpecificOutput"]["additionalContext"] and j["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
   and "2 处" in j["systemMessage"])
r = hook({"tool_input": {"file_path": P0}, "tool_response": {"filePath": P0, "type": "update", "originalFile": new}})
ok("H8 这次没写坏：静默", r.returncode == 0 and r.stdout.strip() == "")
r = hook({"tool_input": {"file_path": P0}, "tool_response": {"filePath": P0, "type": "update", "originalFile": old}}, strict=True)
ok("H9 strict 宿主：原因写 stderr、退出 2", r.returncode == 2 and "正本写法提示" in r.stderr)
P1 = w("项目情况/甲项目/_archive/旧.md", "本篇是唯一入口。\n")
r = hook({"tool_input": {"file_path": P1}, "tool_response": {"filePath": P1, "type": "create"}})
ok("H10 _archive 里的不提", r.returncode == 0 and "正本写法" not in r.stdout)
CTL = load("ctl", "handoffctl.py")
_hits = [json.loads(x) for x in io.open(C.P.gate_hits, encoding="utf-8")] if os.path.isfile(C.P.gate_hits) else []
ok("H11 钩子每提示一次记一笔（种类、项目/篇、规则），没写坏的那次不记", len(_hits) == 2
   and all(h["kind"] == "zhengben" and h["file"] == "甲项目/钩子.md" for h in _hits) and "self" in _hits[0]["codes"])
_line = CTL.gate_hits_line(now=datetime.now(timezone.utc))
ok("H12 status 的写时门一行：近 7 天正本几次、最常见哪几类（用规则名，不用代号）", "正本 2 次" in _line
   and "自称唯一" in _line and "self" not in _line)

print("== F Fable 11-12 复查的几处：变差口径、整篇的量、网络路径 ==")
import types as _types


def zrun(docs, state, now):
    b = io.StringIO()
    with contextlib.redirect_stdout(b):
        Z.scan(docs, os.path.join(docs, "工作传递", C.ZB_TODO_NAME), state, "测试", now_utc=now)
    return json.loads(re.search(r"^#zb (\{.*\})$", b.getvalue(), re.M).group(1))


DF = os.path.join(ROOT, "fdocs", "docs")
SF = os.path.join(ROOT, "f_state.json")


def wf(rel, text):
    p_ = os.path.join(DF, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(p_), exist_ok=True)
    io.open(p_, "w", encoding="utf-8", newline="\n").write(text)
    return p_


RD = "现役\n\n# 丙\n\nproject_state_owner: 0-当前状态.md\n\n| 篇 | 类型 | 管 | 不写 |\n|---|---|---|---|\n| [记录](记录.md) | 台账 | 记 | 无 |\n"
os.makedirs(os.path.join(DF, "工作传递"), exist_ok=True)
wf("项目情况/丙项目/README.md", RD)
wf("项目情况/丙项目/方案.md", "现役\n\n# 方案\n\n本篇是唯一入口。\n以本篇为准的价格。\n")
wf("项目情况/丙项目/记录.md", "现役\n\n# 记录\n\n本篇是唯一入口。\n")   # 台账：不查写法
wf("项目情况/丙项目/0-当前状态.md", "现役\n\n# 当前状态\n\n" + "".join(f"- 第{i}条现状说明文字写得很长很长很长（{md(1)} 查）\n" for i in range(150)))
wf("项目情况/丙项目/台账二.md", "现役\n\n# 台账二\n\n" + "| 一行 | 台账内容 |\n" * 3000)
wf("项目情况/丙项目/README.md", RD + "| [台账二](台账二.md) | 台账 | 记 | 无 |\n")
T0 = NOW - timedelta(days=2)
z = zrun(DF, SF, T0)
ok("F0 首轮建基线：不判变差", z["n_regress"] == 0)
# ① 项目目录改名，内容不动
os.replace(os.path.join(DF, "项目情况", "丙项目"), os.path.join(DF, "项目情况", "丁项目"))
z = zrun(DF, SF, T0 + timedelta(hours=24))
ok("F1 项目目录改名、内容一字没动：不算变差（逐句按规则＋原句全库数，整篇的量跟同样大小的旧篇比）", z["n_regress"] == 0)
# ② 篇章表把台账改登记成专题：那篇这一轮只重建基线
wf("项目情况/丁项目/README.md", RD.replace("| [记录](记录.md) | 台账 |", "| [记录](记录.md) | 专题 |") + "| [台账二](台账二.md) | 台账 | 记 | 无 |\n")
z = zrun(DF, SF, T0 + timedelta(hours=48))
ok("F2 改登记类型（台账→专题）冒出来的存量：不算变差", z["n_regress"] == 0)
# ③ 一边清（方案.md 删掉两句）一边新写（新篇里写一句别的自称唯一）：新写的那句要认出来
wf("项目情况/丁项目/方案.md", "现役\n\n# 方案\n\n正文。\n")
wf("项目情况/丁项目/新篇.md", "现役\n\n# 新篇\n\n这篇是本项目最新的说明。\n")
z = zrun(DF, SF, T0 + timedelta(hours=72))
_r = {(x["key"], x["rule"]) for x in z["regress"]}
ok("F3 清掉旧的同时新写一处：新写的照样算变差（不互相抵消）", ("丁项目/新篇.md", "self") in _r and len(_r) == 1)
ok("F3b 变差条目带原句与新写处数，写时门没提示过就记 0", z["regress"][0]["n_new"] == 1 and "最新" in z["regress"][0]["eg"]
   and z["regress"][0]["hook_hits"] == 0)
# ④ 读不到的篇沿用上一轮，不记 0；下一轮读得到了也不算新写
_real_io = Z.io
_bad = os.path.join(DF, "项目情况", "丁项目", "新篇.md")
Z.io = _types.SimpleNamespace(open=lambda p_, *a, **k: (_ for _ in ()).throw(OSError("读不到")) if os.path.abspath(p_) == _bad else _real_io.open(p_, *a, **k))
z = zrun(DF, SF, T0 + timedelta(hours=96))
Z.io = _real_io
z = zrun(DF, SF, T0 + timedelta(hours=120))
ok("F4 某一轮读不到一篇、下一轮又读到了：不算变差", z["n_regress"] == 0)
# ⑤ 已超线的状态篇又涨一截、台账一天涨很多
wf("项目情况/丁项目/0-当前状态.md", "现役\n\n# 当前状态\n\n" + "".join(f"- 第{i}条现状说明文字写得很长很长很长（{md(1)} 查）\n" for i in range(190)))
wf("项目情况/丁项目/台账二.md", "现役\n\n# 台账二\n\n" + "| 一行 | 台账内容 |\n" * 6000)
z = zrun(DF, SF, T0 + timedelta(hours=144))
_m = [x for x in z["regress"] if x["type"] == "metric"]
ok("F5 已超 2,000 字的状态篇一天又多了几百字：算变差，写明从多少字到多少字；只增的台账涨了不算",
   len(_m) == 1 and _m[0]["rule"] == "statesize" and "→" in _m[0]["eg"] and "字" in _m[0]["eg"])
ok("F6 近 7 天的变差留一份、每条标现在改了没有", z["recent"] and all("fixed" in r for r in z["recent"])
   and any(r["key"] == "丁项目/新篇.md" and not r["fixed"] for r in z["recent"]))
wf("项目情况/丁项目/新篇.md", "现役\n\n# 新篇\n\n说明。\n")
z = zrun(DF, SF, T0 + timedelta(hours=148))
ok("F7 改掉以后：近 7 天的那条标「已改掉」", any(r["key"] == "丁项目/新篇.md" and r["fixed"] for r in z["recent"]))
# ⑥ 规则版本变了：只重建基线
_v = C.ZB_RULES_VERSION
C.ZB_RULES_VERSION = "测试-换版"
wf("项目情况/丁项目/新篇.md", "现役\n\n# 新篇\n\n本篇是唯一的说明。\n")
z = zrun(DF, SF, T0 + timedelta(hours=172))
C.ZB_RULES_VERSION = _v
ok("F8 规则版本变了：这一轮只重建基线、不判变差", z["rebased"] and z["n_regress"] == 0)
zrun(DF, SF, T0 + timedelta(hours=177))  # 换回现行版本再跑一轮，后面跟它比
# ⑦ 写时门记账：扫描按「项目/篇」认这一篇写的时候有没有被提示过
os.makedirs(os.path.dirname(C.P.gate_hits), exist_ok=True)
io.open(C.P.gate_hits, "a", encoding="utf-8").write(json.dumps({"utc": (T0 + timedelta(hours=190)).isoformat(), "kind": "zhengben",
                                                                 "file": "丁项目/方案.md", "codes": ["self"]}, ensure_ascii=False) + "\n")
wf("项目情况/丁项目/方案.md", "现役\n\n# 方案\n\n正文，本文是唯一入口。\n")
z = zrun(DF, SF, T0 + timedelta(hours=198))
ok("F9 这一篇近 24 小时被钩子提示过：变差条目记上提示次数", any(x["key"] == "丁项目/方案.md" and x["hook_hits"] == 1 for x in z["regress"]))
# ⑧ 网络路径不交给文件系统
_calls = []
_real_isfile = C.os.path.isfile
C.os.path.isfile = lambda p_: (_calls.append(p_), False)[1]
_r1 = C.zb_local_path("\\\\host\\share\\x.md", fdir, DOCS)
_r2 = C.zb_local_path("\\\\?\\UNC\\host\\share\\x.md", fdir, DOCS)
C.os.path.isfile = _real_isfile
ok("F10 反引号里的 \\\\主机\\共享 路径：不去连，直接不算", _r1 is None and _r2 is None and not any(str(c).startswith(("\\\\", "//")) for c in _calls))

n_fail = sum(1 for _, c in results if not c)
shutil.rmtree(ROOT, ignore_errors=True)
print(f"\n合计 {len(results)} 项，失败 {n_fail} 项")
sys.exit(1 if n_fail else 0)
