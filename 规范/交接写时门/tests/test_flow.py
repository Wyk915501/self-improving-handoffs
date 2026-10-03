# -*- coding: utf-8 -*-
"""handoff_flow.py v0.2.2 离线用例：临时 docs 树，只测报告逻辑（report-only，不写真树）。
日期纪律（09-22 CI 教训）：夹具日期一律相对「北京今天」动态生成——旧件=−5 天（必进 W2 的 48h 窗）、
新鲜件=今天（必在 48h 窗内被跳过）、起算日用显式参数，不依赖代码里的默认 2026-09-20。"""
import io, os, sys, shutil, importlib.util, tempfile
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"  # 子进程也不写 __pycache__
for _k in [k for k in os.environ if k.upper().startswith(("HANDOFF_", "HN_", "HL_"))]:
    os.environ.pop(_k)  # 继承来的运行目录变量（HANDOFF_HOME 等）会压过下面的临时目录、让测试写进真目录（第十批打包干净检出时发现）
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

print("== T2 W1 窗口内也有报告动静 → 不报（审查：原 T2 没开 --w1，W1 根本没跑，是空测）==")
r = w(f"工作传递/X/claude-code/{D_FRESH}_0900_a_交接报告.md", backflow_report("t2", f"{D_FRESH}T09:00:00+08:00", "none"))
buf2 = io.StringIO()
with contextlib.redirect_stdout(buf2):
    rc3 = m.scan(DOCS, 2, None, "测试", since_date="2026-09-01", w1=True)
ok("T2 开了 --w1、窗口内有报告改动：无 W1 发现", "W1" not in buf2.getvalue())

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

# ===================== v0.3（2026-10-02 全面审查）回归 =====================
def scan_out(days=3, since=SINCE, todo=None):
    b = io.StringIO()
    with contextlib.redirect_stdout(b):
        rc = m.scan(DOCS, days, todo, "测试", since_date=since)
    return rc, b.getvalue().replace("\\", "/")


print("== T14 回流写成对端机器绝对路径 /root/proj/…：按配置的前缀映射回本机后照常核对（原来一律报写坏、永远消不掉）==")
_cfg_flow0 = m.C.cfg
m.C.cfg = lambda *k, **kw: {"/root/proj/": "{ws_root}/"} if k[:2] == ("flow", "path_prefix_map") else _cfg_flow0(*k, **kw)
io.open(os.path.join(DOCS, "项目情况", "P", "A.md"), "w", encoding="utf-8", newline="\n").write(HDR + f"- {date.today().isoformat()}：回流。\n")
w(f"工作传递/R/claude-code-US3-claude/{D_OLD}_0900_r1_交接报告.md",
  backflow_report("t14", f"{D_OLD}T09:00:00+08:00", "/root/proj/docs/项目情况/P/A.md"))
w(f"工作传递/R/claude-code-US3-claude/{D_OLD}_0901_r2_交接报告.md",
  backflow_report("t14b", f"{D_OLD}T09:01:00+08:00", "/root/proj/docs/项目情况/P/真没有.md"))
_, o14 = scan_out()
m.C.cfg = _cfg_flow0
ok("T14a 映射后目标存在且已更新：不报", "r1_交接报告.md" not in o14)
ok("T14b 映射后目标不存在：照报不存在", "r2_交接报告.md 声明回流到" in o14 and "但该文件不存在" in o14)

print("== T15 不带前缀的回流路径也试工作区根（原来只试 docs 根：自我改进循环/分享包/README.md 被误报）==")
_ws = os.path.join(ROOT, "自我改进循环", "分享包")
os.makedirs(_ws, exist_ok=True)
io.open(os.path.join(_ws, "README.md"), "w", encoding="utf-8").write(HDR + f"- {date.today().isoformat()}：发布。\n")
w(f"工作传递/S/claude-code/{D_OLD}_0900_s_交接报告.md", backflow_report("t15", f"{D_OLD}T09:00:00+08:00", "自我改进循环/分享包/README.md"))
_, o15 = scan_out()
ok("T15 工作区根下的目标被找到、不报", "S/claude-code" not in o15)

print("== T16 frozen_at 带引号的冻结件照样核对（原来整件跳过）==")
w(f"工作传递/Q/codex/{D_OLD}_0900_q_交接报告.md",
  f"---\nstatus: \"ready_for_review\"\nreport_id: t16\nfrozen_at: \"{D_OLD}T09:00:00+08:00\"\ncanonical_backflow:\n  path: \"项目情况/P/引号件没有.md\"\n---\n\n# q\n")
_, o16 = scan_out()
ok("T16 带引号的件进入 W2 核对", "引号件没有.md" in o16)

print("== T17 回流目标不是 UTF-8：不再整次崩溃 ==")
_bin = os.path.join(DOCS, "项目情况", "P", "二进制.md")
io.open(_bin, "wb").write(b"\xff\xfe\x00\x81 not utf8 \x80\x81")
w(f"工作传递/B/codex/{D_OLD}_0900_b_交接报告.md", backflow_report("t17", f"{D_OLD}T09:00:00+08:00", "项目情况/P/二进制.md"))
_rc17, o17 = scan_out()
ok("T17 扫描照常结束（退出码 0 或 1，不是崩溃）", _rc17 in (0, 1) and "#keys" in o17)

print("== T18 W3 按文件名里的写作时刻判窗口：同步落盘的老件不算碎片化 ==")
for i in range(3):
    pp = w(f"工作传递/M/codex/{D_OLD}_1{i}00_老件{i}_交接报告.md", backflow_report(f"t18-{i}", f"{D_OLD}T10:00:00+08:00", "none"))
    touch(pp, 0)  # 改动时刻＝现在（模拟刚同步下来）
_, o18 = scan_out(days=2)
ok("T18 文件名是 5 天前的三份老件：改动时刻是现在也不报 W3", "M/codex" not in o18)

print("== T19 清单：首行状态词、内容不变不重写、写不出返回 2 ==")
todo2 = os.path.join(ROOT, "todo2.md")
scan_out(todo=todo2)
_t1 = io.open(todo2, encoding="utf-8").read()
_m1 = os.path.getmtime(todo2)
_t.sleep(1.1)
_, o19 = scan_out(todo=todo2)
ok("T19a 首行是「现役」、末尾有更新记录", _t1.startswith("现役\n") and "## 更新记录" in _t1)
ok("T19b 第二轮内容没变：不重写（同步域里不制造假改动）", os.path.getmtime(todo2) == _m1 and "未重写" in o19)
_rc19, _ = scan_out(todo=os.path.join(todo2, "x", "todo.md"))  # 上级"目录"其实是个文件：两种系统都写不出
ok("T19c 清单写不出：返回 2（与'有发现'的 1 分开）", _rc19 == 2)

print("== T20 内部错误：main 返回 2，看门狗据此报'没跑成' ==")
_c = m.candidates
m.candidates = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
with contextlib.redirect_stdout(io.StringIO()):
    _rc20 = m.main(["handoff_flow.py", "scan", DOCS, "--days", "3", "--since-date", SINCE])
m.candidates = _c
ok("T20 内部异常 → 退出码 2", _rc20 == 2)

print("== T21 回流路径写成 //主机/共享：不去碰文件系统（会去连 SMB），当找不到报（复核 R2-2-2）==")
import time as _tm
w(f"工作传递/U/codex/{D_OLD}_0900_unc_交接报告.md", backflow_report("t21", f"{D_OLD}T09:00:00+08:00", "//192.0.2.1/s/x.md"))
_t0 = _tm.time()
_, o21 = scan_out()
ok("T21 报成回流目标不存在，而且没有等网络（< 2 秒）", "192.0.2.1" in o21 and "不存在" in o21 and _tm.time() - _t0 < 2)

n_fail = sum(1 for _, c in results if not c)
print(f"\n合计 {len(results)} 项，失败 {n_fail} 项")
shutil.rmtree(ROOT, ignore_errors=True)
sys.exit(1 if n_fail else 0)
