#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
handoff_gate.py 的正确行为回归测试（标准库；临时目录；不碰真实文件）
运行：python tests/test_gate.py          退出 0 = 全过
对应 Codex 反例：G01/G02/G04–G11/H02（sil-codex-20260908-01）、V00–V07（sil-codex-20260908-02）
"""
import io, os, re, sys, json, shutil, tempfile, subprocess, importlib.util
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(os.path.dirname(HERE), "handoff_gate.py")
ROOT = tempfile.mkdtemp(prefix="gate_")
os.environ["HANDOFF_TOOLS_DIR"] = os.path.join(ROOT, "tools")  # 状态文件全进临时目录，不碰真实 ~/.claude/tools（US3 Claude 1550 R1）
spec = importlib.util.spec_from_file_location("gate", GATE)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

T = os.path.join(ROOT, "工作传递", "x")  # 路径必须含"工作传递"才在检查范围
os.makedirs(T)
BJ = timezone(timedelta(hours=8))
now = datetime.now(BJ)
FRESH = (now - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%S+08:00")
OLD = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S+08:00")
OBS = (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S+08:00")
results = []


def ok(name, cond):
    results.append((name, bool(cond)))
    print(("  PASS " if cond else "  FAIL ") + name)


def fm(over=None, drop=()):
    d = {k: "none" for k in g.BUILTIN_KEYS}
    d.update({"status": "ready_for_review", "observed_at": OBS, "frozen_at": FRESH,
              "stale_if": "[]", "exact_refs": "[]", "artifact_hashes": "[]", "related_reports": "[]"})
    d.update(over or {})
    return "---\n" + "\n".join(f"{k}: {v}" for k, v in d.items() if k not in drop) + "\n---\n"


def w(name, text):
    p = os.path.join(T, name)
    io.open(p, "w", encoding="utf-8", newline="\n").write(text)
    return p


def codes(p, hook=False):
    return [x[:2] for x in g.check(p, hook_mode=hook)]


def hook_reason(p):
    r = subprocess.run([sys.executable, "-X", "utf8", GATE, "--hook"], input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": p}}),
                       capture_output=True, text=True, encoding="utf-8")
    return json.loads(r.stdout)["reason"] if r.stdout.strip() else ""


def run_hook(payload, *extra):
    return subprocess.run([sys.executable, "-X", "utf8", GATE, *extra], input=json.dumps(payload, ensure_ascii=False),
                          capture_output=True, text=True, encoding="utf-8")


# G01 引号 status 合法
p = w("t1_引号状态_交接报告.md", fm({"status": '"ready_for_review"'}) + "# 正文\n")
ok("G01 带引号的合法 status 通过", codes(p) == [])
# G02 引号 profile 仍触发条件键
p = w("t2_引号profile_交接报告.md", fm({"workflow_profile": '"multi-ai-loop/v1"'}, drop=("full_contract_finalize",)) + "# 正文\n")
ok("G02 带引号的 multi-ai-loop/v1 仍要求 full_contract_finalize", any("full_contract_finalize" in x for x in g.check(p)))
# G04 非法 YAML
p = w("t3_未闭合数组_交接报告.md", fm({"stale_if": "[unclosed"}) + "# 正文\n")
r = g.check(p)
ok("G04 未闭合数组 → G1 且无连带噪声", r and r[0].startswith("G1") and len(r) == 1)
# G05 重复键（裸）与 V 带引号重复键
p = w("t4_重复键_交接报告.md", fm().replace("---\ntitle: none", "---\nstatus: draft\ntitle: none", 1) + "# 正文\n")
ok("G05 重复 status → G1", any("重复键" in x for x in g.check(p)))
p = w("t9_引号重复键_交接报告.md", fm().replace("---\ntitle: none", '---\n"status": draft\ntitle: none', 1) + "# 正文\n")
ok("V 带引号的重复键 → G1", any("重复键" in x for x in g.check(p)))
# V 坏日期
p = w("t8_坏日期_交接报告.md", fm({"frozen_at": "2026-99-10T20:10:00+08:00"}) + "# 正文\n")
ok("V 坏日期 → G1（不抛未捕获异常）", any(x.startswith("G1") for x in g.check(p)))
# G06 观测晚于冻结
p = w("t6_观测晚于冻结_交接报告.md", fm({"observed_at": "2099-01-01T00:00:00+08:00"}) + "# 正文\n")
ok("G06 observed_at 在未来且晚于 frozen_at → G4", sum(1 for x in g.check(p) if x.startswith("G4")) == 2)
# G07–G11 链接
w("exists with space.md", "x\n")
p = w("t5_链接_交接报告.md", fm() + "# 正文\n\n```\n[代码块示例](missing_in_code.md)\n```\n行内 `[x](missing_inline.md)` 忽略。\n"
      "[a](<exists with space.md>) [b](exists%20with%20space.md \"标题\") [r][ref] [c](missing.md)\n\n[ref]: t1_引号状态_交接报告.md\n")
r = [x for x in g.check(p) if x.startswith("G6")]
ok("G07–G11 尖括号/标题/引用式通过、代码块忽略、只报 missing.md", len(r) == 1 and "missing.md" in r[0] and "missing_in_code" not in r[0] and "missing_inline" not in r[0])
# G7 仅 hook 模式
p = w("t7_回改冻结件_交接报告.md", fm({"frozen_at": OLD, "observed_at": OBS.replace(OBS[11:13], "%02d" % ((int(OBS[11:13]) - 3) % 24))}) + "# 正文\n")
ok("G7 CLI 模式不报", not any(x.startswith("G7") for x in g.check(p)))
ok("G7 hook 模式报提示", "G7" in hook_reason(p))
p_fresh = os.path.join(T, "t1_引号状态_交接报告.md")
ok("刚冻结的好件 hook 静默", hook_reason(p_fresh) == "")
# H02 相对文件名 / 范围外 / 混合 / 目录不存在 → 退出码
cwd = os.getcwd()
os.chdir(T)
r1 = subprocess.run([sys.executable, "-X", "utf8", GATE, "t6_观测晚于冻结_交接报告.md"], capture_output=True, text=True, encoding="utf-8")
os.chdir(cwd)
ok("H02 裸相对文件名被检查（退出 1）", r1.returncode == 1 and "检查 1 件" in r1.stdout)
r2 = subprocess.run([sys.executable, "-X", "utf8", GATE, os.path.join(ROOT, "工作传递", "x", "exists with space.md")], capture_output=True, text=True, encoding="utf-8")
ok("范围外文件明说并退出 2", r2.returncode == 2 and "跳过" in r2.stdout)
r3 = subprocess.run([sys.executable, "-X", "utf8", GATE, p_fresh, os.path.join(T, "不存在_交接报告.md")], capture_output=True, text=True, encoding="utf-8")
ok("V 混合好件+缺失 → 退出 2", r3.returncode == 2)
r4 = subprocess.run([sys.executable, "-X", "utf8", GATE, "--scan", os.path.join(T, "没有这个目录")], capture_output=True, text=True, encoding="utf-8")
ok("V 扫描目录不存在 → 退出 2", r4.returncode == 2)
# 非目标文件 hook 静默
ok("非目标文件 hook 静默", hook_reason(os.path.join(T, "exists with space.md")) == "")

# 跨宿主：字段名不同的载荷（ZCode 等）
bad = os.path.join(T, "t6_观测晚于冻结_交接报告.md")
r = run_hook({"event": "PostToolUse", "toolName": "write_file", "toolInput": {"filePath": bad}}, "--hook")
ok("异构载荷（toolInput.filePath）也能定位并报错", r.stdout.strip() and "G4" in json.loads(r.stdout)["reason"])
r = run_hook({"deep": {"nested": [{"whatever": bad}]}}, "--hook")
ok("深层任意字段名也能定位", r.stdout.strip() and "G4" in json.loads(r.stdout)["reason"])
r = run_hook({"tool_input": {"file_path": bad}}, "--hook-strict")
ok("--hook-strict：原因写 stderr、退出码 2", r.returncode == 2 and "G4" in r.stderr and not r.stdout.strip())
r = run_hook({"tool_input": {"file_path": p_fresh}}, "--hook-strict")
ok("--hook-strict：好件退出 0 且无输出", r.returncode == 0 and not r.stdout.strip() and not r.stderr.strip())
r = run_hook({"nothing": "here"}, "--hook")
ok("载荷无路径且未给 --root：静默退出 0", r.returncode == 0 and not r.stdout.strip())
TOOLS = os.environ["HANDOFF_TOOLS_DIR"]
stamp, seen = os.path.join(TOOLS, "handoff_gate_lastscan"), os.path.join(TOOLS, "handoff_gate_reported.json")
ok("状态文件落在临时目录而非真实家目录", g.TOOLS_DIR == TOOLS and not TOOLS.startswith(os.path.expanduser("~") + os.sep + ".claude"))
_bak = {}
try:
    WT = os.path.join(ROOT, "工作传递")
    r = run_hook({"nothing": "here"}, "--hook-strict", "--root", WT)
    ok("载荷无路径 + 给了 --root：兜底扫到最近改动的坏件", r.returncode == 2 and "件 /" in r.stderr)
    ok("兜底一次最多报 3 件", r.stderr.count("交接报告.md：") <= 3)
    r2 = run_hook({"nothing": "here"}, "--hook-strict", "--root", WT)
    ok("兜底 60 秒内限流，不重复全扫", r2.returncode == 0 and not r2.stderr.strip())
    # 超过 3 件时分批消化：每轮报的都是新的，几轮后收敛为空，同一文件不重复
    names = re.findall(r"([^\s：]+_交接报告\.md)", r.stderr)
    rounds, converged = 0, False
    while rounds < 6:
        rounds += 1
        os.remove(stamp)
        rr = run_hook({"nothing": "here"}, "--hook-strict", "--root", WT)
        got = re.findall(r"([^\s：]+_交接报告\.md)", rr.stderr)
        if not got:
            converged = True
            break
        if set(got) & set(names):
            break
        names += got
    ok("兜底分批消化：同一 (文件, 改动时刻) 不重复报，几轮后收敛为空", converged)
finally:
    pass

# --scan --todo：自定义文件名与写入端说明；写不出必须退出 2 且不得说"已写"（Codex 1557 §三.2）
out_ok = os.path.join(T, "自定义-待处理-测试.md")  # T 已存在；写到不存在的目录属于下一条"不可写"用例
r = subprocess.run([sys.executable, "-X", "utf8", GATE, "--scan", os.path.join(ROOT, "工作传递"), "--all", "--todo", out_ok, "--writer", "测试写者-甲"],
                   capture_output=True, text=True, encoding="utf-8")
body = io.open(out_ok, encoding="utf-8").read() if os.path.exists(out_ok) else ""
ok("--todo 任意文件名 + --writer：文件写出、含写入端与收件箱限制说明", r.returncode == 1 and "测试写者-甲" in body and "收件箱" in body and "已写" in r.stdout)
out_bad = os.path.join(ROOT, "没有这个目录", "再一层", "x.md")
r = subprocess.run([sys.executable, "-X", "utf8", GATE, "--scan", os.path.join(ROOT, "工作传递"), "--all", "--todo", out_bad],
                   capture_output=True, text=True, encoding="utf-8")
ok("--todo 目标不可写：退出 2、不打印'已写'、打印失败原因", r.returncode == 2 and "已写" not in r.stdout and "写入失败" in r.stdout)
# G0 反斜杠文件名（Linux 上会出现；Windows 无法创建，直接测判定函数）
ok("G0 文件名含反斜杠 → 报", any(x.startswith("G0") for x in g.name_problems("claude-code\\2026-09-09_1358_x_交接报告.md")))
ok("G0 正常文件名不报", g.name_problems("2026-09-09_1358_x_交接报告.md") == [])

# G8 索引 README 的链接（US3 Claude 1750：索引行写成 claude-code\文件名，与 G0"文件放错"是两个独立缺陷）
IDX = os.path.join(ROOT, "工作传递", "子任务", "claude-code")
os.makedirs(IDX)
io.open(os.path.join(IDX, "2026-09-09_1400_在_交接报告.md"), "w", encoding="utf-8", newline="\n").write(fm() + "# 正文\n")  # 合格件，免得它自己的 G3 混进索引那一节
io.open(os.path.join(IDX, "README.md"), "w", encoding="utf-8", newline="\n").write(
    "---\ntitle: 索引\n---\n# 索引\n\n"
    "| 日期 | 报告 |\n|---|---|\n"
    "| 09-09 | [反斜杠前缀](claude-code\\2026-09-09_1400_在_交接报告.md) |\n"
    "| 09-09 | [同目录不存在](2026-09-09_1500_不在_交接报告.md) |\n"
    "| 09-09 | [同目录存在](2026-09-09_1400_在_交接报告.md) |\n"
    "| 09-09 | [上级不存在](../不存在.md) [再上级](../../README.md) |\n"
    "| 09-09 | [对面机器绝对路径](/root/proj/docs/不存在.md) [网址](https://example.com/x) [锚](#x) |\n"
    "| 09-09 | [子目录不存在](附件/不存在.md) |\n"
    "| 09-09 | [合法转义](2026-09-09\\_1400\\_在\\_交接报告.md) |\n"
    "| 09-09 | [锚点合法转义](2026-09-09_1400_在_交接报告.md#section\\_one) |\n\n"
    "行内 `[代码里](claude-code\\不算.md)` 忽略。\n"
    "~~~markdown\n[围栏示例](不存在示例.md)\n~~~\n")
r = g.index_problems(os.path.join(IDX, "README.md"))
ok("G8 索引链接目标含反斜杠 → 报", any(x.startswith("G8") and "反斜杠" in x and "2026-09-09_1400_在" in x for x in r))
ok("G8 同目录裸文件名不存在 → 报", any(x.startswith("G8") and "找不到同目录目标" in x and "2026-09-09_1500_不在" in x for x in r))
ok("G8 ../、/root/…、http、#、子目录 一律不报；行内代码忽略；只报上面两类", len(r) == 2 and not any(k in " ".join(r) for k in ("../不存在", "/root/proj", "example.com", "附件/", "不算.md")))
ESC = os.path.join(ROOT, "工作传递", "转义", "codex")
os.makedirs(ESC)
io.open(os.path.join(ESC, "existing_report.md"), "w", encoding="utf-8").write("ok\n")
io.open(os.path.join(ESC, "README.md"), "w", encoding="utf-8", newline="\n").write(
    "# 转义对照\n\n[合法](existing\\_report.md)\n[锚点](existing_report.md#section\\_one)\n")
ok("G8 合法 CommonMark 标点转义不误报", g.index_problems(os.path.join(ESC, "README.md")) == [])
ok("G8 锚点里的合法反斜杠转义不误报", g.scan_links("[锚点](existing_report.md#section\\_one)") == ["existing_report.md#section_one"])
ok("G8 波浪线围栏内示例不报", "不存在示例.md" not in g.scan_links("~~~markdown\n[示例](不存在示例.md)\n~~~\n"))
ARCH = os.path.join(ROOT, "工作传递", "_archive", "旧", "claude-code")
os.makedirs(ARCH)
io.open(os.path.join(ARCH, "README.md"), "w", encoding="utf-8").write("# 旧\n\n[断](claude-code\\x_交接报告.md) [断2](没有.md)\n")
ok("G8 _archive/ 下的 README 不在范围", not g.is_index(os.path.join(ARCH, "README.md")))
GOOD = os.path.join(ROOT, "工作传递", "子任务", "codex")
os.makedirs(GOOD)
io.open(os.path.join(GOOD, "a_交接报告.md"), "w", encoding="utf-8", newline="\n").write(fm() + "# 正文\n")
io.open(os.path.join(GOOD, "README.md"), "w", encoding="utf-8").write("# 好索引\n\n[a](a_交接报告.md) [上](../README.md) [远](/root/x.md)\n")
ok("G8 正常索引不报；交接报告不算索引", g.is_index(os.path.join(GOOD, "README.md")) and g.index_problems(os.path.join(GOOD, "README.md")) == []
   and not g.is_index(os.path.join(GOOD, "a_交接报告.md")))
r = subprocess.run([sys.executable, "-X", "utf8", GATE, "--scan", os.path.join(ROOT, "工作传递"), "--all", "--todo", out_ok],
                   capture_output=True, text=True, encoding="utf-8")
body = io.open(out_ok, encoding="utf-8").read()
ok("--scan 扫到索引问题、清单里标「索引」且不套 G1–G4；_archive 索引不出现", "链接不合格 1 份（G8）" in r.stdout and "子任务/claude-code" in body
   and "状态 `索引`" in body and "G8" in body and "_archive" not in body
   and not any(k in body.split("子任务/claude-code")[1].split("##")[0] for k in ("G1", "G2", "G3", "G4")))
r = subprocess.run([sys.executable, "-X", "utf8", GATE, os.path.join(IDX, "README.md"), os.path.join(ARCH, "README.md")], capture_output=True, text=True, encoding="utf-8")
ok("显式指定索引 README：只做 G8；_archive 下的明说跳过、退出 2", r.returncode == 2 and "G8" in r.stdout and "跳过" in r.stdout and "G3" not in r.stdout)

# v2.4（GLM 09-09 复核）：G8③ 正斜杠前缀、大小写精确比对、文件名含 #、hook 也查索引、G6 反斜杠不可移植
IDX = os.path.join(ROOT, "工作传递", "子任务甲", "claude-code")
os.makedirs(IDX, exist_ok=True)
io.open(os.path.join(IDX, "2026-09-09_0001_真件_交接报告.md"), "w", encoding="utf-8").write("---\nstatus: draft\n---\nx\n")
io.open(os.path.join(IDX, "C#研究_交接报告.md"), "w", encoding="utf-8").write("---\nstatus: draft\n---\nx\n")
idx = os.path.join(IDX, "README.md")
io.open(idx, "w", encoding="utf-8", newline="\n").write(
    "现役\n\n# 索引\n\n"
    "- [好](2026-09-09_0001_真件_交接报告.md)\n"
    "- [正斜杠前缀](claude-code/2026-09-09_0001_真件_交接报告.md)\n"
    "- [大小写](2026-09-09_0001_真件_交接报告.MD)\n"
    "- [井号文件名](C#研究_交接报告.md)\n"
    "- [上级不报](../README.md)\n- [绝对不报](/root/proj/x.md)\n- [子目录不报](sub/x.md)\n")
pr = g.index_problems(idx)
ok("G8③ 正斜杠目录前缀（整体不存在、末段在本目录）被报", any("目录前缀" in x for x in pr))
ok("G8② 大小写不同精确比对：.MD 视为不存在（NTFS 下 exists 会误判通过）", any("找不到同目录目标" in x and ".MD" in x for x in pr))
ok("文件名含 # 的链接不被当锚点截断（整体存在即通过）", not any("C" in x.split("：")[-1].split("；")[0] and "研究" not in x for x in pr) and all("C#研究" not in x for x in pr))
ok("上级/绝对/子目录链接不报", not any("../README.md" in x or "/root/proj" in x or "sub/x.md" in x for x in pr))
ok("hook 模式下 G8 只报确定性两类（不报'找不到同目录目标'）", not any("找不到同目录目标" in x for x in g.index_problems(idx, hook_mode=True)) and any("目录前缀" in x for x in g.index_problems(idx, hook_mode=True)))
r = run_hook({"tool_input": {"file_path": idx}}, "--hook")
ok("hook 写索引 README 当场报（决定性类）", r.stdout.strip() and "G8" in json.loads(r.stdout)["reason"])
idx_ok = os.path.join(IDX, "README2.md")
io.open(idx_ok, "w", encoding="utf-8", newline="\n").write("现役\n\n- [好](2026-09-09_0001_真件_交接报告.md)\n- [尚未落盘的报告](2026-09-09_0002_稍后写_交接报告.md)\n")
ok("hook 模式：索引里指向尚未落盘的报告 → 静默（留给扫描）", g.index_problems(idx_ok, hook_mode=True) == [] and any("找不到同目录目标" in x for x in g.index_problems(idx_ok)))
p = w("t10_反斜杠链接_交接报告.md", fm() + "# 正文\n\n[本机能解析](" + "x\\t1_引号状态_交接报告.md".replace("x\\", "") + ")\n[反斜杠](claude-code\\t1_引号状态_交接报告.md)\n")
ok("G6P 报告正文里的反斜杠链接被判不可移植（即便本机能解析）", any(x.startswith("G6P") and "反斜杠" in x for x in g.check(p)))
# v2.5（GLM 二轮）：扫描/清单只滤 G6 断链，G6P 照报；G6 文件名含 # 整体存在即过；载荷正文里的别件路径不劫持；③逐段精确
SCAN2 = os.path.join(ROOT, "工作传递", "扫描二")
os.makedirs(os.path.join(SCAN2, "claude-code"), exist_ok=True)
p2 = os.path.join(SCAN2, "claude-code", "2026-09-09_0002_反斜杠_交接报告.md")
io.open(p2, "w", encoding="utf-8", newline="\n").write(fm() + "# 正文\n\n[断](没有的文件.md)\n[反斜杠](claude-code\\2026-09-09_0002_反斜杠_交接报告.md)\n")
todo2 = os.path.join(ROOT, "todo2.md")
r = subprocess.run([sys.executable, "-X", "utf8", GATE, "--scan", SCAN2, "--since", "24", "--todo", todo2], capture_output=True, text=True, encoding="utf-8")
t2 = io.open(todo2, encoding="utf-8").read()
ok("--scan --todo：G6 断链被滤掉，G6P 反斜杠进清单", "G6P" in t2 and "解析不到" not in t2)
io.open(os.path.join(IDX, "C#研究_交接报告.md"), "w", encoding="utf-8").write("---\nstatus: draft\n---\nx\n")
p3 = w("t11_井号链接_交接报告.md", fm() + "# 正文\n\n[井号](../../工作传递/子任务甲/claude-code/C#研究_交接报告.md)\n")
ok("G6 链接目标文件名含 #：整体存在即通过，不当锚点截断", not any(x.startswith("G6") for x in g.check(p3)))
p4 = w("t12_井号断_交接报告.md", fm() + "# 正文\n\n[井号断](不存在#研究.md)\n")
ok("G6 含 # 且整体不存在、剥锚点也不存在 → 报断链", any(x.startswith("G6 ") for x in g.check(p4)))
good_report = os.path.join(IDX, "2026-09-09_0001_真件_交接报告.md")
r = run_hook({"tool_input": {"file_path": idx, "content": f"见 {good_report}"}}, "--hook")
ok("hook 写 README 时正文里出现别的报告绝对路径不劫持：仍按索引查（报 G8）", r.stdout.strip() and "G8" in json.loads(r.stdout)["reason"])
os.makedirs(os.path.join(IDX, "sub"), exist_ok=True)
io.open(os.path.join(IDX, "sub", "共名.md"), "w", encoding="utf-8").write("x\n")
io.open(os.path.join(IDX, "共名.md"), "w", encoding="utf-8").write("x\n")
idx3 = os.path.join(IDX, "README3.md")
io.open(idx3, "w", encoding="utf-8", newline="\n").write("现役\n\n- [大小写目录](Sub/共名.md)\n- [对的](sub/共名.md)\n")
pr3 = g.index_problems(idx3)
ok("G8③ 整体存在性逐段精确比对：Sub/ 与 sub/ 不同（NTFS 上 exists 会放过）", any("目录前缀" in x and "Sub/" in x for x in pr3) and not any("sub/共名" in x for x in pr3))

print("== v2.6 _archive 排除（克隆-调整-归档的落地前提，fable 09-21）==")
arch = os.path.join(ROOT, "工作传递", "Z", "_archive", "2026-09-21_0900_归档旧件_交接报告.md")
os.makedirs(os.path.dirname(arch), exist_ok=True)
io.open(arch, "w", encoding="utf-8", newline="\n").write("草稿\n这不是一份合格的报告，且链接 [断的](../不存在的目标.md) 深了一层。\n")
ok("v2.6-1 is_target 不认 _archive 下的报告", not g.is_target(arch))
live = os.path.join(ROOT, "工作传递", "Z", "2026-09-21_0901_现行件_交接报告.md")
io.open(live, "w", encoding="utf-8", newline="\n").write("---\nstatus: draft\nreport_id: za-1\n---\n\n# x\n")
ok("v2.6-2 非 _archive 的报告仍认", g.is_target(live))

print("== v2.7 G6：目标已归档（同目录 _archive/ 下有同名件）不算断链（fable 09-21 复验）==")
ZD = os.path.join(ROOT, "工作传递", "Z")
moved = "2026-09-21_0800_被克隆取代的旧件_交接报告.md"
io.open(os.path.join(ZD, "_archive", moved), "w", encoding="utf-8", newline="\n").write("旧件正文一字不动\n")
citer = os.path.join(ROOT, "工作传递", "Y2", "2026-09-21_0902_引用旧址的冻结件_交接报告.md")
os.makedirs(os.path.dirname(citer), exist_ok=True)
io.open(citer, "w", encoding="utf-8", newline="\n").write(fm() + f"\n# x\n\n见[旧件](../Z/{moved})，以及[真没了的](../Z/2026-09-21_0801_从未存在_交接报告.md)。\n")
pr = g.check(citer)
g6 = [x for x in pr if x.startswith("G6 ")]
ok("v2.7-1 指向已归档旧址的链接放行", not any(moved in x for x in g6))
ok("v2.7-2 真不存在的目标照报（不因此放松）", any("从未存在" in x for x in g6) and "1 个链接" in g6[0])

io.open(os.path.join(ZD, "_archive", "README.md"), "w", encoding="utf-8").write("归档说明\n")
citer2 = os.path.join(ROOT, "工作传递", "Y2", "2026-09-21_0903_引用不存在的索引_交接报告.md")
io.open(citer2, "w", encoding="utf-8", newline="\n").write(fm() + "\n# x\n\n见[索引](../Z/README.md)。\n")
ok("v2.7-3 只对交接报告放行：_archive/ 里恰好有同名 README 不能让断链过关", any(x.startswith("G6 ") for x in g.check(citer2)))

n_fail = sum(1 for _, c in results if not c)
print(f"\n合计 {len(results)} 项，失败 {n_fail} 项")
shutil.rmtree(ROOT, ignore_errors=True)
sys.exit(1 if n_fail else 0)
