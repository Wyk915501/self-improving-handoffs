# -*- coding: utf-8 -*-
"""handoff_flow.py v0.2.2 离线用例：临时 docs 树，只测报告逻辑（report-only，不写真树）。
日期纪律（09-22 CI 教训）：夹具日期一律相对「北京今天」动态生成——旧件=−5 天（必进 W2 的 48h 窗）、
新鲜件=今天（必在 48h 窗内被跳过）、起算日用显式参数，不依赖代码里的默认 2026-09-20。"""
import io, os, sys, shutil, importlib.util, tempfile
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = tempfile.mkdtemp(prefix="hf_")
os.environ["HANDOFF_TOOLS_DIR"] = os.path.join(ROOT, "tools")
spec = importlib.util.spec_from_file_location("flow", os.path.join(os.path.dirname(HERE), "handoff_flow.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

D_OLD = (date.today() - timedelta(days=5)).isoformat()    # 旧件：冻结满 5 天（>48h）
D_FRESH = date.today().isoformat()                        # 新鲜件：0 天（<48h）
SINCE = (date.today() - timedelta(days=7)).isoformat()    # 常用起算日：旧件也算
SINCE_LATE = (date.today() - timedelta(days=2)).isoformat()  # 晚起算：旧件被赦免

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
r = w(f"工作传递/X/claude-code/{D_FRESH}_0900_a_交接报告.md", backflow_report("t2", f"{D_FRESH}T09:00:00+08:00", "none"))
buf2 = io.StringIO()
with contextlib.redirect_stdout(buf2):
    rc3 = m.scan(DOCS, 2, None, "测试", since_date="2026-09-01")
ok("T2 无 W1 发现", "W1" not in buf2.getvalue())

print("== T3 W2 冻结超48h、正本更新记录更旧 → 报 ==")
old = canon_with_update("2026-09-01")
touch(old, 10)
p3 = w(f"工作传递/X/claude-code/{D_OLD}_0900_b_交接报告.md",
       backflow_report("t3", f"{D_OLD}T09:00:00+08:00", "项目情况/P/A.md"))
touch(p3, 3)
buf3 = io.StringIO()
with contextlib.redirect_stdout(buf3):
    rc4 = m.scan(DOCS, 3, None, "测试", since_date=SINCE)
ok("T3 报 W2", rc4 == 1 and "W2" in buf3.getvalue() and "A.md" in buf3.getvalue())

print("== T4 正本更新记录比冻结新 → 过 ==")
io.open(old, "w", encoding="utf-8", newline="\n").write(HDR + f"- {(date.today()-timedelta(days=4)).isoformat()}：回流。\n")
buf4 = io.StringIO()
with contextlib.redirect_stdout(buf4):
    rc5 = m.scan(DOCS, 3, None, "测试", since_date=SINCE)
ok("T4 无 W2 发现", "W2" not in buf4.getvalue())

print("== T5 回流目标不存在 → 报 ==")
w(f"工作传递/X/claude-code/{D_OLD}_0900_c_交接报告.md",
  backflow_report("t5", f"{D_OLD}T09:00:00+08:00", "项目情况/P/没有.md"))
buf5 = io.StringIO()
with contextlib.redirect_stdout(buf5):
    rc6 = m.scan(DOCS, 3, None, "测试", since_date=SINCE)
ok("T5 报目标不存在", "不存在" in buf5.getvalue())

print("== T6 draft 与新鲜冻结不查 ==")
w(f"工作传递/X/claude-code/{D_FRESH}_1000_d_交接报告.md",
  backflow_report("t6", f"{D_FRESH}T10:00:00+08:00", "项目情况/P/也没有.md", status="draft"))
w(f"工作传递/X/claude-code/{D_FRESH}_1001_e_交接报告.md",
  backflow_report("t6b", f"{D_FRESH}T10:01:00+08:00", "项目情况/P/还是没有.md"))
buf6 = io.StringIO()
with contextlib.redirect_stdout(buf6):
    m.scan(DOCS, 3, None, "测试", since_date=SINCE)
ok("T6 draft 与新鲜冻结都不产生对应 W2", "也没有" not in buf6.getvalue() and "还是没有" not in buf6.getvalue())

print("== T7 W3 碎片化 ==")
for i in range(3):
    w(f"工作传递/Y/codex/{D_FRESH}_1{i}00_f{i}_交接报告.md",
      backflow_report(f"t7-{i}", f"{D_FRESH}T1{i}:00:00+08:00", "none"))
buf7 = io.StringIO()
with contextlib.redirect_stdout(buf7):
    rc7 = m.scan(DOCS, 2, None, "测试", since_date=SINCE)
ok("T7 报 W3 碎片化", "W3" in buf7.getvalue() and "Y/codex" in buf7.getvalue().replace("\\", "/"))

print("== T8 --todo 落文件 ==")
todo = os.path.join(ROOT, "todo.md")
with contextlib.redirect_stdout(io.StringIO()):
    m.scan(DOCS, 2, todo, "测试者", since_date=SINCE)
ok("T8 文件写出且带 writer 与 report-only 字样", os.path.exists(todo) and "测试者" in io.open(todo, encoding="utf-8").read() and "只提醒不拦人" in io.open(todo, encoding="utf-8").read())

print("== T9 起算日：早于起算的旧件赦免，晚于起算的同件照报 ==")
w(f"工作传递/X/claude-code/{(date.today()-timedelta(days=3)).isoformat()}_0900_g_交接报告.md",
  backflow_report("t9", f"{(date.today()-timedelta(days=3)).isoformat()}T09:00:00+08:00", "项目情况/P/同样没有.md"))
buf9 = io.StringIO()
with contextlib.redirect_stdout(buf9):
    m.scan(DOCS, 30, None, "测试", since_date=SINCE_LATE)  # −3 天与 −5 天的件都早于 −2 天起算
ok("T9a 早于起算的件不报 W2", "同样没有" not in buf9.getvalue().replace("\\", "/") and "没有.md，但该文件不存在" not in buf9.getvalue())
buf9b = io.StringIO()
with contextlib.redirect_stdout(buf9b):
    m.scan(DOCS, 30, None, "测试", since_date=SINCE)  # 起算提前到 −7 天，同一批件进窗
ok("T9b 同件在早起算下照报（对照）", "没有.md，但该文件不存在" in buf9b.getvalue())

print("== T10 一格多路径（分号）不再误报 ==")
w(f"工作传递/X/claude-code/{D_OLD}_1400_h_交接报告.md",
  backflow_report("t10", f"{D_OLD}T14:00:00+08:00", "不存在的；项目情况/P/A.md"))
import time as _t
os.utime(os.path.join(DOCS, "项目情况", "P", "A.md"), (_t.time(),) * 2)
buf10 = io.StringIO()
with contextlib.redirect_stdout(buf10):
    m.scan(DOCS, 3, None, "测试", since_date=SINCE)
ok("T10 分号里第二个路径存在 → 不报不存在", "h_交接报告.md 声明回流到" not in buf10.getvalue().replace("\\", "/"))

print("== T11 对话件不计碎片化 ==")
WT3 = os.path.join(DOCS, "工作传递", "W", "codex")
os.makedirs(WT3, exist_ok=True)
for i in range(3):
    w(f"工作传递/W/codex/{D_FRESH}_1{i}50_回签x{i}_交接报告.md",
      backflow_report(f"t11-{i}", f"{D_FRESH}T15:00:00+08:00", "none"))
buf11 = io.StringIO()
with contextlib.redirect_stdout(buf11):
    m.scan(DOCS, 2, None, "测试", since_date=SINCE)
ok("T11 回签/签收类不触发 W3", "W/codex" not in buf11.getvalue().replace("\\", "/"))

print("== T12 W1 默认关 ==")
buf12 = io.StringIO()
with contextlib.redirect_stdout(buf12):
    m.scan(DOCS, 2, None, "测试", since_date=SINCE)
ok("T12 未传 --w1 时 W1 不产生条目", "W1" not in buf12.getvalue())

print("== T13 _archive 排除（克隆＋归档旧件不数两份，fable 09-21）==")
archdir = os.path.join(DOCS, "工作传递", "V", "claude-code", "_archive")
os.makedirs(archdir, exist_ok=True)
for i in range(3):
    io.open(os.path.join(archdir, f"{D_OLD}_1{i}00_旧{i}_交接报告.md"), "w", encoding="utf-8", newline="\n").write(
        backflow_report(f"t13-{i}", f"{D_OLD}T10:00:00+08:00", "none"))
buf13 = io.StringIO()
with contextlib.redirect_stdout(buf13):
    m.scan(DOCS, 2, None, "测试", since_date=SINCE)
ok("T13 _archive 里的件不进 W3/W2", "V/claude-code" not in buf13.getvalue().replace("\\", "/"))

n_fail = sum(1 for _, c in results if not c)
print(f"\n合计 {len(results)} 项，失败 {n_fail} 项")
shutil.rmtree(ROOT, ignore_errors=True)
sys.exit(1 if n_fail else 0)
