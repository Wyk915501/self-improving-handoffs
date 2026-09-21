#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""handoff_notify.py 的回归测试：'从未成功'宽限截止（Codex sil-codex-20260908-03 §四 C）。临时目录，不弹窗。"""
import io, os, sys, json, shutil, tempfile, importlib.util
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = tempfile.mkdtemp(prefix="hn_")
os.environ["HANDOFF_TOOLS_DIR"] = os.path.join(ROOT, "tools")  # 状态、日志、页面全进临时目录（US3 Claude 1550 R1）
os.environ["HN_STATE_PATH"] = os.path.join(ROOT, "notify_state.json")
os.environ["HL_STATE_PATH"] = os.path.join(ROOT, "lessons_state.json")
os.environ["HN_LOG_PATH"] = os.path.join(ROOT, "log.txt")
os.environ["HANDOFF_NO_REGISTER"] = "1"  # 不碰真实注册表（AppUserModelID 与 handoff-veto: 协议），按钮逻辑照常走
spec = importlib.util.spec_from_file_location("notify", os.path.join(os.path.dirname(HERE), "handoff_notify.py"))
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)
n.AUTO_PUBLISH = False  # 本测试不起 publish 子进程
n.task_last_result = lambda name: (None, None)  # 不读真机的计划任务状态（同 HANDOFF_TOOLS_DIR 那条隔离承诺）

sent = []
n.toast = lambda title, body, buttons=None, persistent=True: (sent.append((title, body, buttons, persistent)), True)[1]
T = os.path.join(ROOT, "协作教训.md")
io.open(T, "w", encoding="utf-8", newline="\n").write("现役\n\n| 编号 | 状态 | 一句话规矩 | 为什么 | 出处 |\n|---|---|---|---|---|\n| LG-01 | 生效 | 规矩一 | 事一 | 源 |\n\n## 更新记录\n\n- 建档\n")
t0 = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
results = []


def ok(name, cond):
    results.append((name, bool(cond)))
    print(("  PASS " if cond else "  FAIL ") + name)


n.check(T, now_utc=t0, task_present=True)
st = json.load(io.open(os.environ["HN_STATE_PATH"], encoding="utf-8"))
ok("首次发现：记 first_seen、不弹", st.get("first_seen_utc") == t0.isoformat() and not sent)
n.check(T, now_utc=t0 + timedelta(hours=35), task_present=True)
ok("35 小时：宽限中不弹", not sent)
n.check(T, now_utc=t0 + timedelta(hours=37), task_present=True)
ok("37 小时仍无成功：弹'从未成功'", len(sent) == 1 and "从未成功" in sent[0][1])
ok("故障类 → 常驻弹窗、标题含'需要你介入'、唯一按钮「看处理」开状态页", sent[0][3] is True and "需要你介入" in sent[0][0]
   and [b[0] for b in (sent[0][2] or [])] == ["看处理"] and sent[0][2][0][1].endswith("handoff_status.html"))
n.check(T, now_utc=t0 + timedelta(hours=40), task_present=True)
ok("同日不重复弹", len(sent) == 1)
json.dump({"last_scan_utc": (t0 + timedelta(hours=41)).isoformat()}, io.open(os.environ["HL_STATE_PATH"], "w", encoding="utf-8"))
n.check(T, now_utc=t0 + timedelta(hours=42), task_present=True)
st = json.load(io.open(os.environ["HN_STATE_PATH"], encoding="utf-8"))
ok("成功后：清 first_seen、不弹", "first_seen_utc" not in st and len(sent) == 1)
n.check(T, now_utc=t0 + timedelta(hours=42 + 37), task_present=True)
ok("上次成功后 37 小时：弹'已 N 小时没有成功'", len(sent) == 2 and "没有成功运行" in sent[1][1])
n.check(T, now_utc=t0 + timedelta(hours=100), task_present=False)
ok("定时任务不存在：不评估故障", len(sent) == 2)
ok("页面与状态都在临时目录，没碰真实家目录", n.STATUS_PAGE.startswith(ROOT) and n.FINDINGS_PAGE.startswith(ROOT)
   and os.path.exists(n.STATUS_PAGE) and not os.path.exists(os.path.join(os.path.expanduser("~"), ".claude", "tools", "logs", "handoff_status.html.tmp")))
# --with-scan 的扫描器也覆盖索引 README（G8）：反斜杠链接被扫到，_archive 下的不扫，跨机链接不报
WT = os.path.join(ROOT, "工作传递")
for sub, text in (("子任务/claude-code", "# 索引\n\n[坏](claude-code\\2026-09-09_x_交接报告.md) [远](/root/x.md) [上](../没有.md)\n"),
                  ("_archive/旧/claude-code", "# 旧\n\n[坏](claude-code\\x_交接报告.md)\n"),
                  ("子任务/codex", "# 好\n\n[上](../README.md)\n")):
    os.makedirs(os.path.join(WT, sub))
    io.open(os.path.join(WT, sub, "README.md"), "w", encoding="utf-8", newline="\n").write(text)
found = n.scan_problems(WT, 24)
ok("看门狗扫描覆盖索引 README：只报反斜杠那份（G8），_archive 与跨机链接不报", len(found) == 1 and found[0][0].endswith(os.path.join("claude-code", "README.md"))
   and "_archive" not in found[0][0] and all(x.startswith("G8") for x in found[0][2]) and "/root/x.md" not in " ".join(found[0][2]))
# 旧实现总 cap=20 且先扫报告，20 个坏报告会让索引循环直接退出；生产默认必须完整收集，不能让 G8 饥饿。
for i in range(20):
    p = os.path.join(WT, "拥堵", f"{i:02d}_交接报告.md")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="utf-8", newline="\n").write("不是 frontmatter\n")
found = n.scan_problems(WT, 24)
ok("20 个坏报告不会饿死 G8 索引：生产默认完整返回 21 项", len(found) == 21 and sum(1 for p, _, _ in found if p.endswith("README.md")) == 1)

# v1.4：扫描只滤 G6 跨机断链，G6P 反斜杠不可移植照进清单（GLM 09-09 二轮）
pbs = os.path.join(WT, "反斜杠件", "claude-code", "2026-09-09_0003_x_交接报告.md")
os.makedirs(os.path.dirname(pbs), exist_ok=True)
io.open(pbs, "w", encoding="utf-8", newline="\n").write("---\nstatus: draft\nreport_id: x-3\n---\n\n[断](没有.md)\n[反](claude-code\\2026-09-09_0003_x_交接报告.md)\n")
found = n.scan_problems(WT, 24)
mine = [f for f in found if f[0] == pbs]
ok("scan_problems：G6P 反斜杠项保留、G6 断链项滤掉", len(mine) == 1 and any(x.startswith("G6P") for x in mine[0][2]) and not any(x.startswith("G6 ") for x in mine[0][2]))

# v2.4：待否决到期前 6 小时升为"需要你介入"并常驻（GLM 09-09）
due_soon = (t0 + timedelta(hours=100 + 3)).astimezone(n.BJ).strftime("%Y-%m-%d %H:%M")
io.open(T, "w", encoding="utf-8", newline="\n").write(
    "现役\n\n| 编号 | 状态 | 一句话规矩 | 为什么 | 出处 |\n|---|---|---|---|---|\n| LG-01 | 生效 | 规矩一 | 事一 | 源 |\n"
    f"| LG-02 | 拟生效（至 {due_soon}） | 规矩二 | 事二 | 源；加入 2026-09-07 00:00（自动） |\n\n## 更新记录\n\n- 建档\n")
sent.clear()
n.check(T, now_utc=t0 + timedelta(hours=100), task_present=False)
ok("到期前 3 小时：升级为常驻弹窗，标题只邀请去看，不逼人在弹窗上判断", len(sent) == 1 and sent[0][3] is True
   and "你看一眼" in sent[0][0] and "明早 09:00 生效" in sent[0][1] and "你不管就是同意" in sent[0][1])
n.check(T, now_utc=t0 + timedelta(hours=101), task_present=False)
ok("同一到期只升级提醒一次", len(sent) == 1)

# v1.5（负责人 09-10 反馈）：倒计时说人话、到期在即逐条列全并先说怎么办、升级窗 6→12 小时
ok("human_left：32 分钟不再显示成 0 小时；天/小时/分钟各档",
   n.human_left(timedelta(minutes=32)) == "32 分钟" and n.human_left(timedelta(seconds=30)) == "不到 1 分钟"
   and n.human_left(timedelta(hours=5, minutes=30)) == "5 小时 30 分钟" and n.human_left(timedelta(hours=5)) == "5 小时"
   and n.human_left(timedelta(days=2, hours=3)) == "2 天 3 小时" and n.human_left(timedelta(days=2)) == "2 天")
ok("cut：不满长度不加省略号，超了才加", n.cut("短", 10) == "短" and n.cut("一二三四五", 3) == "一二三…")


def with_pending(rows):
    io.open(T, "w", encoding="utf-8", newline="\n").write(
        "现役\n\n| 编号 | 状态 | 一句话规矩 | 为什么 | 出处 |\n|---|---|---|---|---|\n| LG-01 | 生效 | 规矩一 | 事一 | 源 |\n"
        + "".join(rows) + "\n## 更新记录\n\n- 建档\n")


def row(lid, due_utc, rule):
    d = due_utc.astimezone(n.BJ).strftime("%Y-%m-%d %H:%M")
    return f"| {lid} | 拟生效（至 {d}） | {rule} | 事 | 源；加入 2026-09-07 00:00（自动） |\n"


due = t0 + timedelta(hours=200)
with_pending([row("LG-03", due, "写已实测时出处要给复核方打得开的位置"), row("LG-04", due, "引用会改的文档要给版本身份")])
sent.clear()
n.check(T, now_utc=due - timedelta(minutes=40), task_present=False)
title, body = sent[0][0], sent[0][1]
ok("到期前 40 分钟：正文写「40 分钟」而不是「0 小时」", len(sent) == 1 and "40 分钟" in body and "0 小时" not in title + body)
# 负责人 09-10：'我压根不知道 LG-06 是什么' / '要么就是跳转出去让我去看实际内容然后再给我的意见'
ok("弹窗对人可读：不出现内部编号（LG-xx）", "LG-" not in title and "LG-" not in body)
ok("弹窗对人可读：不出现内部黑话（否决／拟生效／每日学习／否决记录）",
   not any(w in title + body for w in ("拟生效", "否决记录", "每日学习", "否决")))
ok("弹窗不塞规矩正文，也不在弹窗上让人拍板——只说有这回事 + 一个「去看看」",
   "写已实测时" not in body and "引用会改的文档" not in body
   and [b[0] for b in (sent[0][2] or [])] == ["去看看"] and sent[0][2][0][1].endswith("handoff_status.html"))
ok("弹窗说清了不管会怎样、去哪读全文", "你不管就是同意" in body and "读全文" in body and sent[0][3] is True)
page = io.open(n.STATUS_PAGE, encoding="utf-8").read()
ok("判断在页面上做：顶部「等你拍板」区给出两条规矩的全文",
   "等你拍板" in page and "写已实测时出处要给复核方打得开的位置" in page and "引用会改的文档要给版本身份" in page)
ok("页面每条规矩都给「同意」「不采纳」两个按钮，指向正确的编号",
   'href="handoff-rule:ok/LG-03"' in page and 'href="handoff-rule:no/LG-03"' in page
   and 'href="handoff-rule:ok/LG-04"' in page and 'href="handoff-rule:no/LG-04"' in page)
ok("页面解释了这些规矩是哪来的、不做事会怎样", "自己写报告犯过的错" in page and "什么都不做＝同意" in page)
due2 = t0 + timedelta(hours=300)
with_pending([row("LG-05", due2, "规矩五")])
sent.clear()
n.check(T, now_utc=due2 - timedelta(hours=10), task_present=False)
ok("到期前 10 小时就升级（旧的 6 小时窗配 4 小时轮询，最晚只提前几十分钟）",
   len(sent) == 1 and sent[0][3] is True and "10 小时" in sent[0][1] and "你看一眼" in sent[0][0])
due9 = t0 + timedelta(hours=500)
with_pending([row("LG-09", due9, "规矩九")])
sent.clear()
n.check(T, now_utc=due9 + timedelta(hours=5), task_present=False)
ok("已过期但还没翻牌：仍然常驻提醒 + 带去页面（这段最长十几小时）",
   len(sent) == 1 and sent[0][3] is True and "已经到期" in sent[0][1]
   and [b[0] for b in (sent[0][2] or [])] == ["去看看"])
ok("过期文案不出现负数倒计时", "还有 -" not in sent[0][1] and "还有 -" not in sent[0][0])
due3 = t0 + timedelta(hours=400)
with_pending([row("LG-08", due3, "规矩八")])
sent.clear()
n.check(T, now_utc=due3 - timedelta(hours=20), task_present=False)
ok("离到期还有 20 小时：只当告知、不常驻", len(sent) == 1 and sent[0][3] is False and "需要你介入" not in sent[0][0])

# v1.5：一键否决（弹窗按钮真的执行的那件事）——只追加、不重复、编号必须真实存在
VD = os.path.join(ROOT, "veto")
os.makedirs(VD, exist_ok=True)
VT, VV = os.path.join(VD, "协作教训.md"), os.path.join(VD, "协作教训-否决记录.md")
io.open(VT, "w", encoding="utf-8", newline="\n").write(
    "现役\n\n| 编号 | 状态 | 一句话规矩 | 为什么 | 出处 |\n|---|---|---|---|---|\n"
    "| LG-01 | 生效 | 规矩一 | 事一 | 源 |\n| LG-06 | 拟生效（至 2099-01-01 00:00） | 规矩六 | 事六 | 源 |\n\n## 更新记录\n\n- 建档\n")
io.open(VV, "w", encoding="utf-8", newline="\n").write(
    "现役\n\n# 否决记录\n\n| 编号 | 日期 | 谁 | 理由（可空） |\n|---|---|---|---|\n\n## 更新记录\n\n- 建档\n")
sent.clear()
rc = n.decide("handoff-rule:no/LG-06", VT, who="负责人")
vt = io.open(VV, encoding="utf-8").read()
ok("不采纳：协议串里的动作与编号被正确取出，行写进否决记录表格里", rc == 0 and "| LG-06 | " in vt
   and vt.index("| LG-06 | ") > vt.index("|---|---|---|---|") and vt.index("| LG-06 | ") < vt.index("## 更新记录"))
ok("不采纳：更新记录也补一行，便于事后对账", "点「不采纳」划掉" in vt.split("## 更新记录")[1])
ok("不采纳：确认弹窗说人话——先复述规矩，再说怎么反悔", len(sent) == 1 and sent[0][0] == "这条不采纳了"
   and "规矩六" in sent[0][1] and "改主意就删掉" in sent[0][1] and sent[0][3] is False)
sent.clear()
rc2 = n.decide("no/LG-06", VT)
ok("不采纳：重复点不写第二行", rc2 == 0 and io.open(VV, encoding="utf-8").read().count("| LG-06 | ") == 1 and "早就划掉了" in sent[0][0])
sent.clear()
rc3 = n.decide("no/LG-99", VT)
ok("不采纳：表里没有的编号不写、明确告知", rc3 == 2 and "| LG-99 |" not in io.open(VV, encoding="utf-8").read() and "没找到" in sent[0][0])
sent.clear()
before = io.open(VV, encoding="utf-8").read()
rc4 = n.decide("handoff-rule:no/../../etc/passwd", VT)
rc5 = n.decide("no/LG-06; rm -rf /", VT)
rc6 = n.decide("delete/LG-06", VT)
ok("拍板：动作或编号不合法一律忽略（协议注册给全系统，只认 ok|no + LG-数字）",
   rc4 == 2 and rc5 == 2 and rc6 == 2 and io.open(VV, encoding="utf-8").read() == before and not sent)
# 「同意」不是"什么都不做"：记一笔，之后不再拿这条烦你
sent.clear()
io.open(VT, "a", encoding="utf-8", newline="\n").write("")
rc7 = n.decide("handoff-rule:ok/LG-01", VT)
agreed = (json.load(io.open(os.environ["HN_STATE_PATH"], encoding="utf-8")).get("agreed") or {})
ok("同意：记进状态、弹确认、不碰任何 docs 文件", rc7 == 0 and "LG-01" in agreed
   and sent[0][0] == "好，这条就这么定了" and "不会再提醒" in sent[0][1]
   and io.open(VV, encoding="utf-8").read() == before)

# v1.5：计划任务"跑过但结果码非 0"当场报（09-10 实况：HandoffDaily 被关窗口杀掉，脚本一行日志都没写）
io.open(T, "w", encoding="utf-8", newline="\n").write(
    "现役\n\n| 编号 | 状态 | 一句话规矩 | 为什么 | 出处 |\n|---|---|---|---|---|\n| LG-01 | 生效 | 规矩一 | 事一 | 源 |\n\n## 更新记录\n\n- 建档\n")
n.task_last_result = lambda name: ((3221225786, "2026-09-10 01:40:22") if name == "HandoffDaily" else (None, None))  # PowerShell 报的是无符号
sent.clear()
n.check(T, now_utc=t0 + timedelta(hours=600), task_present=True)
ok("计划任务上次结果码非 0：当场报，并点破是窗口被关掉杀的",
   len(sent) == 1 and sent[0][3] is True and "HandoffDaily" in sent[0][1] and "0xC000013A" in sent[0][1])
n.check(T, now_utc=t0 + timedelta(hours=601), task_present=True)
ok("同一次失败只报一次", len(sent) == 1)
n.task_last_result = lambda name: (0, "2026-09-10 09:00:00")
sent.clear()
n.check(T, now_utc=t0 + timedelta(hours=602), task_present=True)
ok("结果码 0：不报", not sent)
n.task_last_result = lambda name: (267011, "N/A")
n.check(T, now_utc=t0 + timedelta(hours=603), task_present=True)
ok("267011（从没跑过）不当失败", not sent)
n.task_last_result = lambda name: (None, None)

print("== P 被拒候选池（v1.6）==")
io.open(T, "w", encoding="utf-8", newline="\n").write("现役\n\n| 编号 | 状态 | 一句话规矩 | 为什么 | 出处 |\n|---|---|---|---|---|\n| LG-01 | 生效 | 规矩一 | 事一 | 源 |\n\n## 更新记录\n\n- 建档\n")
json.dump({"items": [
    {"id": "RP-001", "rule": "活正本随进展及时回流，更新时同步删改被推翻的旧结论", "why": "两个项目都犯过",
     "category": "正本与索引维护", "reason": "涉及权限/部署/同步/冻结机制/检查器等，不自动生效（额外一层，不是语义边界）",
     "evidence": [{"report_id": "ms-codex-1", "rel": "X/codex/2026-09-08_0100_a_交接报告.md"}],
     "date": "2026-09-20", "status": "pending"},
    {"id": "RP-002", "rule": "拿不准就问", "why": "含糊指令", "category": "其他",
     "reason": "类别「其他」不在可自动生效的白名单", "evidence": [], "date": "2026-09-20", "status": "pending"},
]}, io.open(n.POOL_PATH, "w", encoding="utf-8"))
sent.clear()
n.check(T, now_utc=t0 + timedelta(hours=700), task_present=True)
page = io.open(n.STATUS_PAGE, encoding="utf-8").read()
ok("P1 页面出现「被拒的好点子」区，每条给采纳/不用按钮",
   "被拒的好点子" in page and "adopt/RP-001" in page and "drop/RP-001" in page)
ok("P2 每条候选写明程序当时的拒因", "额外一层" in page and "白名单" in page)
ok("P3 池子本身不触发「候选」类弹窗（只在页面上出现；此刻的弹窗是别的旧条件）",
   all("候选" not in (s[0] + (s[1] or "")) and "好点子" not in s[0] for s in sent))
tbl0 = io.open(T, encoding="utf-8").read()
# v1.9：采纳要带处理页口令（页面链接里那一段）。先验三种拿不到口令的调用都被拒，再用页面上的真链接采纳。
import re as _re
rc_bare = n.decide("handoff-rule:adopt/RP-001", T, who="负责人")
rc_wrong = n.decide("handoff-rule:adopt/RP-001/0123456789", T, who="负责人")
ok("Q1 不带口令或口令不对的采纳一律被拒，表一个字不变",
   rc_bare == 2 and rc_wrong == 2 and io.open(T, encoding="utf-8").read() == tbl0)
m_link = _re.search(r'handoff-rule:adopt/RP-001/([0-9a-f]{10})"', page)
ok("Q2 页面「采纳」链接带 10 位口令，且等于 pool_token 算出来的",
   bool(m_link) and m_link.group(1) == n.pool_token(json.load(io.open(n.POOL_PATH, encoding="utf-8"))["items"][0]))
_p = json.load(io.open(n.POOL_PATH, encoding="utf-8"))
_p["items"][0]["rule"] += "（被人改过）"
json.dump(_p, io.open(n.POOL_PATH, "w", encoding="utf-8"), ensure_ascii=False)
ok("Q3 候选正文变了，旧页面上的口令自动作废（读到的字和写进表的字必须是同一条）",
   n.decide(f"handoff-rule:adopt/RP-001/{m_link.group(1)}", T) == 2 and io.open(T, encoding="utf-8").read() == tbl0)
_p["items"][0]["rule"] = _p["items"][0]["rule"].replace("（被人改过）", "")
json.dump(_p, io.open(n.POOL_PATH, "w", encoding="utf-8"), ensure_ascii=False)
sent.clear()
rc = n.decide(f"handoff-rule:adopt/RP-001/{m_link.group(1)}", T, who="负责人")
tbl = io.open(T, encoding="utf-8").read()
ok("P4 adopt 返回 0 且写成人工行（拟生效 48h、出处注明原拒因、加入（人工））",
   rc == 0 and "（人工）" in tbl and "负责人从被拒候选采纳" in tbl and "拟生效（至" in tbl)
ok("P5 新行编号接续现有最大号（LG-02）", "| LG-02 |" in tbl)
pool = json.load(io.open(n.POOL_PATH, encoding="utf-8"))
ok("P6 池内标记 adopted 且记行号", pool["items"][0]["status"] == "adopted" and pool["items"][0].get("row") == "LG-02")
ok("P7 采纳/翻篇的提示语不出现内部编号", all("RP-" not in (s[1] or "") and "LG-" not in (s[1] or "") for s in sent))
rc = n.decide("adopt/RP-001", T)
ok("P8 已裁决的候选再点不重复写", rc == 2 and io.open(T, encoding="utf-8").read() == tbl)
rc = n.decide("handoff-rule:drop/RP-002", T)
ok("P9 drop 返回 0 且标记 ignored",
   rc == 0 and json.load(io.open(n.POOL_PATH, encoding="utf-8"))["items"][1]["status"] == "ignored")
n.check(T, now_utc=t0 + timedelta(hours=701), task_present=True)
page2 = io.open(n.STATUS_PAGE, encoding="utf-8").read()
ok("P10 裁决后页面不再列这两条", "adopt/RP-001" not in page2 and "拿不准就问" not in page2)
ok("P11 动作与编号不合法仍然全拒", n.decide("steal/RP-001", T) == 2 and n.decide("adopt/RP-999", T) == 2
   and n.decide("adopt/../../etc/passwd", T) == 2)

print("== F --with-flow 接线（v1.7）==")
import json as _json
DOCSF = os.path.join(ROOT, "docsf")
WT = os.path.join(DOCSF, "工作传递", "Y", "claude-code")
os.makedirs(WT, exist_ok=True)
io.open(os.path.join(DOCSF, "工作传递", "协作教训.md"), "w", encoding="utf-8", newline="\n").write(
    "现役\n\n| 编号 | 状态 | 一句话规矩 | 为什么 | 出处 |\n|---|---|---|---|---|\n| LG-01 | 生效 | 规矩一 | 事一 | 源 |\n\n## 更新记录\n\n- 建档\n")
for i in range(3):  # 三份 → W3 碎片化
    io.open(os.path.join(WT, f"2026-09-20_1{i}00_f{i}_交接报告.md"), "w", encoding="utf-8", newline="\n").write(
        f"---\nstatus: ready_for_review\nreport_id: nf-{i}\nfrozen_at: 2026-09-20T10:00:00+08:00\n---\n\n# f{i}\n")
sent.clear()
n.check(T, now_utc=t0 + timedelta(hours=710), task_present=True, flow_root=DOCSF)
ftodo = os.path.join(DOCSF, "工作传递", "规范扫描-待处理.md")
ok("F1 首轮发现>0：清单落盘且处理页列「规范扫描」行",
   os.path.exists(ftodo) and "W3" in io.open(ftodo, encoding="utf-8").read()
   and "规范扫描" in io.open(n.STATUS_PAGE, encoding="utf-8").read())
st_f = _json.load(io.open(os.environ["HN_STATE_PATH"], encoding="utf-8"))
ok("F2 首轮记指纹与条数", isinstance(st_f.get("flow"), dict) and st_f["flow"]["n"] >= 1)
ok("F3 首轮（无上轮可比）不弹", not any("规范扫描" in (s[1] or "") for s in sent))
sent.clear()
for i in range(3, 6):  # 再加三份别的目录 → 条数变多
    WT2 = os.path.join(DOCSF, "工作传递", "Z", "codex")
    os.makedirs(WT2, exist_ok=True)
    io.open(os.path.join(WT2, f"2026-09-20_1{i}00_g{i}_交接报告.md"), "w", encoding="utf-8", newline="\n").write(
        f"---\nstatus: ready_for_review\nreport_id: ng-{i}\nfrozen_at: 2026-09-20T10:00:00+08:00\n---\n\n# g{i}\n")
n.check(T, now_utc=t0 + timedelta(hours=711), task_present=True, flow_root=DOCSF)
ok("F4 发现变多才弹负责人一条", any("规范扫描" in (s[0] + (s[1] or "")) for s in sent))
sent.clear()
n.check(T, now_utc=t0 + timedelta(hours=712), task_present=True, flow_root=DOCSF)
ok("F5 条数不变不再弹", not sent)

print("== Q 复验补测（v1.9，fable 2026-09-21_1210 件）==")
from datetime import datetime as _dt
# Q4 由池采纳的规矩：点了「同意」也不静音到期催告；普通规矩点了「同意」照旧静音
_now = _dt.now(timezone.utc)
_due = (_now + timedelta(hours=48)).astimezone(n.BJ)
_tbl_q = io.open(T, encoding="utf-8").read()  # 先读后写：同一条语句里先 open("w") 会把文件清空
io.open(T, "w", encoding="utf-8", newline="\n").write(
    _tbl_q.replace("\n\n## 更新记录",
    f"\n| LG-21 | 拟生效（至 {_due:%Y-%m-%d %H:%M}） | 从池里采纳的规矩 | 事（类别：其他；负责人从被拒候选采纳，程序当时没让它自动生效的原因：越界） | 源；加入 {_now.astimezone(n.BJ):%Y-%m-%d %H:%M}（人工） |"
    f"\n| LG-22 | 拟生效（至 {_due:%Y-%m-%d %H:%M}） | 普通新规矩 | 事三 | 源；加入 {_now.astimezone(n.BJ):%Y-%m-%d %H:%M}（自动） |\n\n## 更新记录", 1))
ok("Q4a 两条「同意」都记下了", n.decide("ok/LG-21", T) == 0 and n.decide("ok/LG-22", T) == 0)
sent.clear()
n.check(T, now_utc=_now + timedelta(hours=40), task_present=True)
_page = io.open(n.STATUS_PAGE, encoding="utf-8").read()
ok("Q4b 到期在即：由池采纳的 LG-21 仍然催一次（标题问「看一眼」），普通的 LG-22 已同意不再催",
   any("新规矩要加给 AI" in s[0] and "1 条" in s[0] for s in sent))
st_q = json.load(io.open(os.environ["HN_STATE_PATH"], encoding="utf-8"))
ok("Q4c 催过的是 LG-21 不是 LG-22", any(k.startswith("pendue:LG-21:") for k in st_q["notified"])
   and not any(k.startswith("pendue:LG-22:") for k in st_q["notified"]))

# Q5 规矩文字含换行：写进表必须还是完整的一行
_p = json.load(io.open(n.POOL_PATH, encoding="utf-8"))
_p["items"].append({"id": "RP-003", "rule": "第一行\n第二行 | 带竖线", "why": "w", "category": "其他", "reason": "r",
                    "evidence": [], "date": "2026-09-21", "status": "pending"})
for _i in range(4):
    _p["items"].append({"id": f"RP-10{_i}", "rule": f"旧{_i}", "status": "evicted", "evicted": "2026-09-21 09:00"})
json.dump(_p, io.open(n.POOL_PATH, "w", encoding="utf-8"), ensure_ascii=False)
rc = n.decide("adopt/RP-003/" + n.pool_token(_p["items"][-5]), T)
_rows = [ln for ln in io.open(T, encoding="utf-8").read().split("\n") if ln.startswith("| LG-23 |")]
ok("Q5 含换行与竖线的规矩写成完整一行（5 格齐全）", rc == 0 and len(_rows) == 1 and len(n.cells_of(_rows[0])) >= 5
   and "第一行 第二行 ／ 带竖线" in _rows[0])
_L = io.open(T, encoding="utf-8").read().split("\n")
_h = _L.index("## 更新记录")
ok("Q6 采纳的更新记录插在「更新记录」标题正下方（与每日学习同口径，最新在上）",
   "RP-003" in next(ln for ln in _L[_h + 1:] if ln.strip()))

# Q7 池满过期条数写在页面上
n.check(T, now_utc=_now + timedelta(hours=41), task_present=True)
ok("Q7 处理页写出「另有 4 条…已经过期」（即使此刻没有待裁量的候选）", "另有 4 条" in io.open(n.STATUS_PAGE, encoding="utf-8").read())

# Q8 状态合并：值班运行期间磁盘上新写的「同意」与口令种子，收尾写回时都得留着
_disk = json.load(io.open(os.environ["HN_STATE_PATH"], encoding="utf-8"))
_mem = {k: v for k, v in _disk.items() if k not in ("agreed", "page_secret")}
_mem["notified"] = dict(_disk.get("notified") or {}, **{"probe:key": "2026-09-21 12:00"})
_disk.setdefault("agreed", {})["LG-77"] = "clicked-during-check"
json.dump(_disk, io.open(os.environ["HN_STATE_PATH"], "w", encoding="utf-8"), ensure_ascii=False)
n.merge_save_state(_mem)
_after = json.load(io.open(os.environ["HN_STATE_PATH"], encoding="utf-8"))
ok("Q8 merge_save_state：磁盘上的 agreed 与 page_secret 保留、内存里新增的 notified 也在",
   _after.get("agreed", {}).get("LG-77") == "clicked-during-check" and _after.get("page_secret") == _disk.get("page_secret")
   and "probe:key" in _after.get("notified", {}))

# Q9 扫描脚本崩了：当日给负责人一条"没跑成"，不拖垮 check
_here0, _bad = n.HERE, os.path.join(ROOT, "badhere")
os.makedirs(_bad, exist_ok=True)
io.open(os.path.join(_bad, "handoff_flow.py"), "w", encoding="utf-8").write("raise RuntimeError('boom')\n")
shutil.copy(os.path.join(_here0, "handoff_lessons.py"), _bad)
n.HERE = _bad
sent.clear()
rc = n.check(T, now_utc=t0 + timedelta(hours=800), task_present=True, flow_root=DOCSF)
ok("Q9 扫描崩溃：check 照常返回、弹出「没跑成」", rc in (0, 1) and any("没跑成" in (s[1] or "") for s in sent))
n.HERE = _here0

# Q10 超过 20 条发现以后，新增一条也必须触发（v1.8 的指纹取自截断后的 stdout，12 次漏 8 次）
DOCSG = os.path.join(ROOT, "docsg")
def _mkdir3(i):
    d = os.path.join(DOCSG, "工作传递", f"线{i:03d}", "codex")
    os.makedirs(d, exist_ok=True)
    for j in range(3):
        io.open(os.path.join(d, f"2026-09-21_0{j}00_任务{i}第{j}份_交接报告.md"), "w", encoding="utf-8").write("---\nstatus: draft\n---\n")
for _i in range(25):
    _mkdir3(_i)
n.check(T, now_utc=t0 + timedelta(hours=900), task_present=True, flow_root=DOCSG)   # 口径/树都换了 → 只记基线
_st = json.load(io.open(os.environ["HN_STATE_PATH"], encoding="utf-8"))
ok("Q10a 基线记下全部 25 个稳定键（不是截断后的 20 条）", _st["flow"]["n"] == 25 and len(_st["flow"]["fps"]) == 25 and _st["flow"].get("kind") == "keys")
_miss = 0
for _k in range(6):
    _mkdir3(100 + _k)
    sent.clear()
    n.check(T, now_utc=t0 + timedelta(hours=900 + 24 * (_k + 1)), task_present=True, flow_root=DOCSG)  # 每次隔一天，避开"一天只弹一条"
    _miss += not any("新的不规范" in (s[1] or "") for s in sent)
ok("Q10b 逐个新增 6 个碎片化目录，6 次全部触发（漏 0 次）", _miss == 0)
sent.clear()
n.check(T, now_utc=t0 + timedelta(hours=900 + 24 * 8), task_present=True, flow_root=DOCSG)
ok("Q10c 什么都没变：隔天再跑不弹", not any("新的不规范" in (s[1] or "") for s in sent))

print("== R 独立验收补测（fable 子代理 09-21：同日第二批、弹窗未送达、口令绑种子与全字段、采纳走锁与哈希门）==")
_H = 900 + 24 * 20
def _alerted():
    return any("新的不规范" in (s[1] or "") for s in sent)
_mkdir3(200); sent.clear()
n.check(T, now_utc=t0 + timedelta(hours=_H), task_present=True, flow_root=DOCSG)
_a1 = _alerted()
_mkdir3(201); sent.clear()
n.check(T, now_utc=t0 + timedelta(hours=_H + 4), task_present=True, flow_root=DOCSG)   # 同一天第二批：当日已弹过，不再弹
_a2 = _alerted(); sent.clear()
n.check(T, now_utc=t0 + timedelta(hours=_H + 24), task_present=True, flow_root=DOCSG)  # 次日：什么都没再变，但第二批必须补弹
_a3 = _alerted(); sent.clear()
n.check(T, now_utc=t0 + timedelta(hours=_H + 48), task_present=True, flow_root=DOCSG)
ok("R1 同一天第二批新发现：当天不重复弹，次日补弹一次，之后不再弹", _a1 and not _a2 and _a3 and not _alerted())
_mkdir3(202); _toast_ok = n.toast
n.toast = lambda *a, **k: (sent.append((a[0], a[1], None, True)), False)[1]            # 弹窗送不出去
n.check(T, now_utc=t0 + timedelta(hours=_H + 72), task_present=True, flow_root=DOCSG)
n.toast = _toast_ok; sent.clear()
n.check(T, now_utc=t0 + timedelta(hours=_H + 76), task_present=True, flow_root=DOCSG)  # 同一天下一轮：上次没送达，这次必须再弹
ok("R2 弹窗没送达：新发现不被基线吞掉，下一轮照样提醒", _alerted())

_ent = {"id": "RP-050", "rule": "规矩", "why": "原因", "category": "其他", "reason": "拒因", "evidence": [{"report_id": "a", "rel": "x.md"}]}
ok("R3 口令必须绑本机种子（换种子口令就变；没有种子算不出口令）",
   n.pool_token(_ent, "A" * 32) != n.pool_token(_ent, "B" * 32) and len(n.pool_token(_ent, "A" * 32)) == 10)
ok("R4 口令绑住所有会写进表的字：只改「为什么」或证据件，口令也变",
   n.pool_token(_ent, "A") != n.pool_token(dict(_ent, why="伪造的原因"), "A")
   and n.pool_token(_ent, "A") != n.pool_token(dict(_ent, evidence=[{"report_id": "伪造", "rel": "y.md"}]), "A"))

_p = json.load(io.open(n.POOL_PATH, encoding="utf-8"))
_p["items"].append(dict(_ent, date="2026-09-21", status="pending"))
json.dump(_p, io.open(n.POOL_PATH, "w", encoding="utf-8"), ensure_ascii=False)
_tok = n.pool_token(_p["items"][-1])
_lockp = os.path.join(os.environ["HANDOFF_TOOLS_DIR"], "handoff_lessons.lock")
os.makedirs(os.path.dirname(_lockp), exist_ok=True)
io.open(_lockp, "w").write("other 2026-09-21T00:00:00+00:00")
_before = io.open(T, encoding="utf-8").read()
ok("R5 每日学习占着锁时采纳不写表（返回 2、表一个字不变）",
   n.decide(f"adopt/RP-050/{_tok}", T) == 2 and io.open(T, encoding="utf-8").read() == _before)
os.remove(_lockp)
_real_open, _hit = io.open, {"n": 0}
def _racing_open(p, *a, **k):   # 采纳读表之后、写表之前，别的写者改了表
    f = _real_open(p, *a, **k)
    if os.path.abspath(str(p)) == os.path.abspath(T) and not _hit["n"] and (not a or a[0] == "r"):
        _hit["n"] = 1
        data = f.read(); f.close()
        _real_open(T, "w", encoding="utf-8", newline="\n").write(data.replace("## 更新记录", "<!-- 别的写者刚动过 -->\n\n## 更新记录", 1))
        return io.StringIO(data)
    return f
n.io.open = _racing_open
_rc = n.decide(f"adopt/RP-050/{_tok}", T)
n.io.open = _real_open
_after = _real_open(T, encoding="utf-8").read()
ok("R6 读表后表被别人改过：哈希门拦下，采纳放弃、别人的改动还在、没写出新规矩",
   _rc == 2 and "别的写者刚动过" in _after and "| 规矩 |" not in _after)

n_fail = sum(1 for _, c in results if not c)
print(f"\n合计 {len(results)} 项，失败 {n_fail} 项")
shutil.rmtree(ROOT, ignore_errors=True)
sys.exit(1 if n_fail else 0)
