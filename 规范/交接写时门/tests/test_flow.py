# -*- coding: utf-8 -*-
"""handoff_flow.py v0.1 离线用例：临时 docs 树，只测报告逻辑（report-only，不写真树）。"""
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


print("== T1 W1 只改没写 ==")
import contextlib
canon_with_update("2026-09-01")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc2 = m.scan(DOCS, 2, None, "测试")
ok("T1 exit 1 且输出含 W1 与文件名", rc2 == 1 and "W1" in buf.getvalue() and "项目情况/P/A.md" in buf.getvalue())

print("== T2 W1 窗口内也有报告动静 → 不报 ==")
r = w("工作传递/X/claude-code/2026-09-20_0900_a_交接报告.md", backflow_report("t2", "2026-09-20T09:00:00+08:00", "none"))
buf2 = io.StringIO()
with contextlib.redirect_stdout(buf2):
    rc3 = m.scan(DOCS, 2, None, "测试")
ok("T2 无 W1 发现", "W1" not in buf2.getvalue())

print("== T3 W2 冻结超48h、正本更新记录更旧 → 报 ==")
old = canon_with_update("2026-09-01")
touch(old, 10)
p3 = w("工作传递/X/claude-code/2026-09-17_0900_b_交接报告.md",
       backflow_report("t3", "2026-09-17T09:00:00+08:00", "项目情况/P/A.md"))
touch(p3, 3)
buf3 = io.StringIO()
with contextlib.redirect_stdout(buf3):
    rc4 = m.scan(DOCS, 3, None, "测试")
ok("T3 报 W2", rc4 == 1 and "W2" in buf3.getvalue() and "A.md" in buf3.getvalue())

print("== T4 正本更新记录比冻结新 → 过 ==")
io.open(old, "w", encoding="utf-8", newline="\n").write(HDR + "- 2026-09-18：回流。\n")
buf4 = io.StringIO()
with contextlib.redirect_stdout(buf4):
    rc5 = m.scan(DOCS, 3, None, "测试")
ok("T4 无 W2 发现", "W2" not in buf4.getvalue())

print("== T5 回流目标不存在 → 报 ==")
w("工作传递/X/claude-code/2026-09-16_0900_c_交接报告.md",
  backflow_report("t5", "2026-09-16T09:00:00+08:00", "项目情况/P/没有.md"))
buf5 = io.StringIO()
with contextlib.redirect_stdout(buf5):
    rc6 = m.scan(DOCS, 3, None, "测试")
ok("T5 报目标不存在", "不存在" in buf5.getvalue())

print("== T6 draft 与新鲜冻结不查 ==")
w("工作传递/X/claude-code/2026-09-20_1000_d_交接报告.md",
  backflow_report("t6", "2026-09-20T10:00:00+08:00", "项目情况/P/也没有.md", status="draft"))
w("工作传递/X/claude-code/2026-09-20_1001_e_交接报告.md",
  backflow_report("t6b", "2026-09-20T10:01:00+08:00", "项目情况/P/还是没有.md"))
buf6 = io.StringIO()
with contextlib.redirect_stdout(buf6):
    m.scan(DOCS, 3, None, "测试")
ok("T6 draft 与新鲜冻结都不产生对应 W2", "也没有" not in buf6.getvalue() and "还是没有" not in buf6.getvalue())

print("== T7 W3 碎片化 ==")
for i, (d, fz) in enumerate([("2026-09-20_1100", "2026-09-20T11:00:00+08:00"),
                             ("2026-09-20_1200", "2026-09-20T12:00:00+08:00"),
                             ("2026-09-20_1300", "2026-09-20T13:00:00+08:00")]):
    w(f"工作传递/Y/codex/{d}_f{i}_交接报告.md", backflow_report(f"t7-{i}", fz, "none"))
buf7 = io.StringIO()
with contextlib.redirect_stdout(buf7):
    rc7 = m.scan(DOCS, 2, None, "测试")
ok("T7 报 W3 碎片化", "W3" in buf7.getvalue() and "Y/codex" in buf7.getvalue().replace("\\", "/"))

print("== T8 --todo 落文件 ==")
todo = os.path.join(ROOT, "todo.md")
with contextlib.redirect_stdout(io.StringIO()):
    m.scan(DOCS, 2, todo, "测试者")
ok("T8 文件写出且带 writer 与 report-only 字样", os.path.exists(todo) and "测试者" in io.open(todo, encoding="utf-8").read() and "只提醒不拦人" in io.open(todo, encoding="utf-8").read())

n_fail = sum(1 for _, c in results if not c)
print(f"\n合计 {len(results)} 项，失败 {n_fail} 项")
shutil.rmtree(ROOT, ignore_errors=True)
sys.exit(1 if n_fail else 0)
