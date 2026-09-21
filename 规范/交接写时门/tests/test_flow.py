# -*- coding: utf-8 -*-
"""handoff_flow.py 离线用例（v0.1 起；v0.2.2 补 T14–T17）：临时 docs 树，只测报告逻辑（report-only，不写真树）。"""
import io, os, sys, shutil, importlib.util, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = tempfile.mkdtemp(prefix="hf_")
os.environ["HANDOFF_TOOLS_DIR"] = os.path.join(ROOT, "tools")
spec = importlib.util.spec_from_file_location("flow", os.path.join(os.path.dirname(HERE), "handoff_flow.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

DOCS = os.path.join(ROOT, "docs")
results = []


def ok(name, cond):
    results.append((name, bool(cond)))
    print(("  PASS " if cond else "  FAIL ") + name)


def w(rel, text):
    p = os.path.join(DOCS, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="utf-8", newline="\n").write(text)
    return p


def backflow_report(rid, frozen, path, status="ready_for_review"):
    return (f"---\nstatus: {status}\nreport_id: {rid}\nfrozen_at: {frozen}\ncanonical_backflow:\n  path: {path}\n"
            f"  actual_post_sha256: x\n---\n\n# {rid}\n")


def touch(p, days_ago=0):
    import time
    os.utime(p, (time.time() - days_ago * 86400,) * 2)


os.makedirs(os.path.join(DOCS, "工作传递"), exist_ok=True)
HDR = "现役\n\n# A\n\n## 更新记录\n\n"


def canon_with_update(date_line):
    return w("项目情况/P/A.md", HDR + f"- {date_line}：测试。\n")


print("== T1 W1 只改没写（v0.2 起需显式 --w1）==")
import contextlib
canon_with_update("2026-09-01")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc2 = m.scan(DOCS, 2, None, "测试", since_date="2026-09-01", w1=True)
ok("T1 exit 1 且输出含 W1 与文件名", rc2 == 1 and "W1" in buf.getvalue() and "项目情况/P/A.md" in buf.getvalue())

print("== T2 W1 窗口内也有报告动静 → 不报 ==")
r = w("工作传递/X/claude-code/2026-09-20_0900_a_交接报告.md", backflow_report("t2", "2026-09-20T09:00:00+08:00", "none"))
buf2 = io.StringIO()
with contextlib.redirect_stdout(buf2):
    rc3 = m.scan(DOCS, 2, None, "测试", since_date="2026-09-01")
ok("T2 无 W1 发现", "W1" not in buf2.getvalue())

print("== T3 W2 冻结超48h、正本更新记录更旧 → 报 ==")
old = canon_with_update("2026-09-01")
touch(old, 10)
p3 = w("工作传递/X/claude-code/2026-09-17_0900_b_交接报告.md",
       backflow_report("t3", "2026-09-17T09:00:00+08:00", "项目情况/P/A.md"))
touch(p3, 3)
buf3 = io.StringIO()
with contextlib.redirect_stdout(buf3):
    rc4 = m.scan(DOCS, 3, None, "测试", since_date="2026-09-01")
ok("T3 报 W2", rc4 == 1 and "W2" in buf3.getvalue() and "A.md" in buf3.getvalue())

print("== T4 正本更新记录比冻结新 → 过 ==")
io.open(old, "w", encoding="utf-8", newline="\n").write(HDR + "- 2026-09-18：回流。\n")
buf4 = io.StringIO()
with contextlib.redirect_stdout(buf4):
    rc5 = m.scan(DOCS, 3, None, "测试", since_date="2026-09-01")
ok("T4 无 W2 发现", "W2" not in buf4.getvalue())

print("== T5 回流目标不存在 → 报 ==")
w("工作传递/X/claude-code/2026-09-16_0900_c_交接报告.md",
  backflow_report("t5", "2026-09-16T09:00:00+08:00", "项目情况/P/没有.md"))
buf5 = io.StringIO()
with contextlib.redirect_stdout(buf5):
    rc6 = m.scan(DOCS, 3, None, "测试", since_date="2026-09-01")
ok("T5 报目标不存在", "不存在" in buf5.getvalue())

print("== T6 draft 与新鲜冻结不查 ==")
w("工作传递/X/claude-code/2026-09-20_1000_d_交接报告.md",
  backflow_report("t6", "2026-09-20T10:00:00+08:00", "项目情况/P/也没有.md", status="draft"))
w("工作传递/X/claude-code/2026-09-20_1001_e_交接报告.md",
  backflow_report("t6b", "2026-09-20T10:01:00+08:00", "项目情况/P/还是没有.md"))
buf6 = io.StringIO()
with contextlib.redirect_stdout(buf6):
    m.scan(DOCS, 3, None, "测试", since_date="2026-09-01")
ok("T6 draft 与新鲜冻结都不产生对应 W2", "也没有" not in buf6.getvalue() and "还是没有" not in buf6.getvalue())

print("== T7 W3 碎片化 ==")
for i, (d, fz) in enumerate([("2026-09-20_1100", "2026-09-20T11:00:00+08:00"),
                             ("2026-09-20_1200", "2026-09-20T12:00:00+08:00"),
                             ("2026-09-20_1300", "2026-09-20T13:00:00+08:00")]):
    w(f"工作传递/Y/codex/{d}_f{i}_交接报告.md", backflow_report(f"t7-{i}", fz, "none"))
buf7 = io.StringIO()
with contextlib.redirect_stdout(buf7):
    rc7 = m.scan(DOCS, 2, None, "测试", since_date="2026-09-01")
ok("T7 报 W3 碎片化", "W3" in buf7.getvalue() and "Y/codex" in buf7.getvalue().replace("\\", "/"))

print("== T8 --todo 落文件 ==")
todo = os.path.join(ROOT, "todo.md")
with contextlib.redirect_stdout(io.StringIO()):
    m.scan(DOCS, 2, todo, "测试者", since_date="2026-09-01")
ok("T8 文件写出且带 writer 与 report-only 字样", os.path.exists(todo) and "测试者" in io.open(todo, encoding="utf-8").read() and "只提醒不拦人" in io.open(todo, encoding="utf-8").read())

print("== T9 默认起算日：09-20 前冻结的件不查 ==")
buf9 = io.StringIO()
with contextlib.redirect_stdout(buf9):
    rc9 = m.scan(DOCS, 30, None, "测试")  # 默认 since=2026-09-20
ok("T9 存量旧件被起算日赦免（不再报 W2）", "W2" not in buf9.getvalue() or "2026-09-17" not in buf9.getvalue())

print("== T10 一格多路径（分号）不再误报 ==")
w("工作传递/X/claude-code/2026-09-20_1400_h_交接报告.md",
  backflow_report("t10", "2026-09-20T14:00:00+08:00", "不存在的；项目情况/P/A.md"))
import time as _t
os.utime(os.path.join(DOCS, "项目情况", "P", "A.md"), (_t.time() - 0 * 86400,) * 2)
buf10 = io.StringIO()
with contextlib.redirect_stdout(buf10):
    m.scan(DOCS, 3, None, "测试", since_date="2026-09-01")
ok("T10 分号里第二个路径存在 → 不报不存在", "t10" not in buf10.getvalue() or "h_交接报告.md 声明回流到" not in buf10.getvalue().replace("\\", "/"))

print("== T11 对话件不计碎片化 ==")
WT3 = os.path.join(DOCS, "工作传递", "W", "codex")
os.makedirs(WT3, exist_ok=True)
for i in range(3):
    w(f"工作传递/W/codex/2026-09-20_1{i}50_回签x{i}_交接报告.md",
      backflow_report(f"t11-{i}", "2026-09-20T15:00:00+08:00", "none"))
buf11 = io.StringIO()
with contextlib.redirect_stdout(buf11):
    m.scan(DOCS, 2, None, "测试", since_date="2026-09-01")
ok("T11 回签/签收类不触发 W3", "W/codex" not in buf11.getvalue().replace("\\", "/"))

print("== T12 W1 默认关 ==")
buf12 = io.StringIO()
with contextlib.redirect_stdout(buf12):
    m.scan(DOCS, 2, None, "测试", since_date="2026-09-01")
ok("T12 未传 --w1 时 W1 不产生条目", "W1" not in buf12.getvalue())

print("== T13 _archive 排除（克隆＋归档旧件不数两份，fable 09-21）==")
archdir = os.path.join(DOCS, "工作传递", "V", "claude-code", "_archive")
os.makedirs(archdir, exist_ok=True)
for i in range(3):
    io.open(os.path.join(archdir, f"2026-09-20_1{i}00_旧{i}_交接报告.md"), "w", encoding="utf-8", newline="\n").write(
        backflow_report(f"t13-{i}", "2026-09-20T10:00:00+08:00", "none"))
buf13 = io.StringIO()
with contextlib.redirect_stdout(buf13):
    m.scan(DOCS, 2, None, "测试", since_date="2026-09-01")
ok("T13 _archive 里的件不进 W3/W2", "V/claude-code" not in buf13.getvalue().replace("\\", "/"))

print("== T14–T17 稳定键、按条数截断、长 frontmatter、带括号说明的路径（v0.2.2，fable 2026-09-21_1210 件）==")
import json as _json, re as _re
DOCS2 = os.path.join(ROOT, "docs2")
def w2(rel, text):
    p = os.path.join(DOCS2, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="utf-8", newline="\n").write(text)
    return p
for i in range(25):  # 25 个碎片化目录
    for j in range(3):
        w2(f"工作传递/线{i:02d}/codex/2026-09-21_0{j}00_任务{i}第{j}份_交接报告.md", "---\nstatus: draft\n---\n")
p_bad = w2("工作传递/K/codex/2026-09-02_0100_坏回流_交接报告.md", backflow_report("k-1", "2026-09-02T10:00:00+08:00", "docs/项目情况/不存在.md"))
touch(p_bad, 10)
w2("项目情况/P/台账.md", "现役\n\n# 台账\n\n## 更新记录\n\n- 2026-09-05：回流了。\n")
p_par = w2("工作传递/K/codex/2026-09-02_0200_带说明_交接报告.md", backflow_report("k-2", "2026-09-02T10:00:00+08:00", "项目情况/P/台账.md（已回流某节）"))
touch(p_par, 10)
p_long = w2("工作传递/K/codex/2026-09-02_0300_长frontmatter_交接报告.md",
            "---\nstatus: ready_for_review\nfrozen_at: 2026-09-02T10:00:00+08:00\nnotes: " + "长" * 9000 + "\ncanonical_backflow:\n  path: docs/项目情况/也不存在.md\n---\n\n# x\n")
touch(p_long, 10)
buf14 = io.StringIO()
todo14 = os.path.join(ROOT, "todo14.md")
with contextlib.redirect_stdout(buf14):
    m.scan(DOCS2, 2, todo14, "测试", since_date="2026-09-01")
out14 = buf14.getvalue().replace("\\", "/")
mk = _re.search(r"^#keys (\[.*\])$", out14, _re.M)
keys14 = _json.loads(mk.group(1)) if mk else []
ok("T14a stdout 末行 #keys 给出全量稳定键（25 个 W3＋2 个 W2），不受显示截断影响", len(keys14) == 27)
ok("T14b 稳定键只含类别与路径，不含天数、条数这类会自己变的字",
   "W2:工作传递/K/codex/2026-09-02_0100_坏回流_交接报告.md" in keys14 and not any("天" in k or "份" in k for k in keys14))
ok("T15 显示按发现条数截到 20 条（不是按行数）、清单文件仍是全量",
   len(_re.findall(r"^- \*\*W\d\*\*", out14, _re.M)) == 20 and "其余 7 条" in out14
   and len(_re.findall(r"^- \*\*W\d\*\*", io.open(todo14, encoding="utf-8").read(), _re.M)) == 27)
ok("T16 frontmatter 超过 6000 字符的报告不再被静默跳过", any("长frontmatter" in k for k in keys14))
ok("T17 回流路径后面带括号说明的，剥掉说明后能找到就不报", not any("带说明" in k for k in keys14))

w2("项目情况/P/没人更新.md", "现役\n\n# x\n\n## 更新记录\n\n- 2026-08-01：很早以前。\n")
p_st = w2("工作传递/K/codex/2026-09-02_0400_回流了但正本没新记录_交接报告.md", backflow_report("k-4", "2026-09-02T10:00:00+08:00", "项目情况/P/没人更新.md"))
touch(p_st, 10)
os.makedirs(os.path.join(DOCS2, "项目情况", "Q"), exist_ok=True)
p_dir = w2("工作传递/K/codex/2026-09-02_0500_回流指到目录_交接报告.md", backflow_report("k-5", "2026-09-02T10:00:00+08:00", "项目情况/Q（已废弃）"))
touch(p_dir, 10)
buf18 = io.StringIO()
with contextlib.redirect_stdout(buf18):
    m.scan(DOCS2, 2, None, "测试", since_date="2026-09-01")
out18 = buf18.getvalue().replace("\\", "/")
keys18 = _json.loads(_re.search(r"^#keys (\[.*\])$", out18, _re.M).group(1))
ok("T18 「冻结已 N 天」这类发现：正文带天数，键里不带（否则每天都算新发现）",
   "冻结已" in out18 and "W2:工作传递/K/codex/2026-09-02_0400_回流了但正本没新记录_交接报告.md" in keys18)
ok("T19 回流路径剥掉括号后命中的是目录：按不存在报，不悄悄吞掉", any("回流指到目录" in k for k in keys18))

n_fail = sum(1 for _, c in results if not c)
print(f"\n合计 {len(results)} 项，失败 {n_fail} 项")
shutil.rmtree(ROOT, ignore_errors=True)
sys.exit(1 if n_fail else 0)
