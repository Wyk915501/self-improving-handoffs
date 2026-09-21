# -*- coding: utf-8 -*-
"""lessons v3 离线端到端用例：假模型 + 临时 docs 树。不调 claude、不碰真实表。"""
from datetime import datetime, timezone
import io, os, sys, json, shutil, importlib.util, tempfile

LESSONS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "handoff_lessons.py")
ROOT = tempfile.mkdtemp(prefix="hl_")
DOCS = os.path.join(ROOT, "docs")
STATE = os.path.join(ROOT, "state.json")
os.environ["HL_STATE_PATH"] = STATE
os.environ["HL_BUNDLE_CAP"] = "120000"
os.environ["HANDOFF_TOOLS_DIR"] = os.path.join(ROOT, "tools")  # 锁与状态全进临时目录
spec = importlib.util.spec_from_file_location("lessons", LESSONS)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

TODAY = m.now_bj().strftime("%Y-%m-%d")
results = []


def ok(name, cond):
    results.append((name, bool(cond)))
    print(("  PASS " if cond else "  FAIL ") + name)


def w(rel, text):
    p = os.path.join(DOCS, "工作传递", rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="utf-8", newline="\n").write(text)
    return p


def report(rid, feedback_for, body, related=""):
    fm = ["---", f"title: t-{rid}", "status: ready_for_review", f"report_id: {rid}"]
    if feedback_for:
        fm.append(f"feedback_for: {feedback_for}")
    fm.append(f"related_reports: [{related}]")
    fm.append("---")
    return "\n".join(fm) + "\n\n# 正文\n\n" + body + "\n"


HDR = "现役\n\n# 协作教训\n\n| 编号 | 状态 | 一句话规矩 | 为什么 | 出处 |\n|---|---|---|---|---|\n"


def table(rows):
    p = os.path.join(DOCS, "工作传递", "协作教训.md")
    io.open(p, "w", encoding="utf-8", newline="\n").write(HDR + "\n".join(rows) + "\n\n## 更新记录\n\n- 建档\n")
    return p


def reset_state():
    if os.path.exists(STATE):
        os.remove(STATE)


# 判决件：两个来源、不同 feedback_for；第三件无事件身份；第四件非来源目录
w("X/codex/2026-09-08_0100_a_交接报告.md", report("ms-codex-1", "lpi-cc-1", "Codex 发现 frozen_at 写成了尚未到达的计划时间，这是预盖。"))
w("X/claude-code-US3-claude/2026-09-08_0200_b_交接报告.md", report("us3-2", "lph-cc-2", "US3 自查：文件名时间比实际收阅时间晚，时间倒挂。"))
w("X/codex/2026-09-08_0300_c_交接报告.md", report("ms-codex-3", "", "有人建议同步前不必核哈希。"))
w("X/claude-code/2026-09-08_0400_d_交接报告.md", report("cc-4", "zzz", "非来源目录，应被忽略。"))
# 判决件 feedback_for 指向的"原件"必须在树内实存，否则不算独立事件（GLM 09-09）：给 a、b 两件各造一份原件
w("X/claude-code/2026-09-07_0900_原件甲_交接报告.md", report("lpi-cc-1", "", "原件甲。"))
w("X/claude-code/2026-09-07_0901_原件乙_交接报告.md", report("lph-cc-2", "", "原件乙。"))

CANDS = [
    {"rule": "写冻结时刻只写实测时钟，不写计划时间", "why": "两次预盖", "category": "时间戳",
     "evidence": [{"report_id": "ms-codex-1", "quote": "frozen_at 写成了尚未到达的计划时间"},
                  {"report_id": "us3-2", "quote": "文件名时间比实际收阅时间晚"}]},
    {"rule": "写冻结时刻只写实测的时钟，别写计划时间", "why": "重复", "category": "时间戳",
     "evidence": [{"report_id": "ms-codex-1", "quote": "frozen_at 写成了尚未到达的计划时间"},
                  {"report_id": "us3-2", "quote": "文件名时间比实际收阅时间晚"}]},
    {"rule": "引用活文档要给版本身份", "why": "虚构引文", "category": "引用身份",
     "evidence": [{"report_id": "ms-codex-1", "quote": "这句原文并不存在于报告里面"},
                  {"report_id": "us3-2", "quote": "文件名时间比实际收阅时间晚"}]},
    {"rule": "同步前不必核哈希，直接覆盖即可", "why": "越权", "category": "并发写入",
     "evidence": [{"report_id": "ms-codex-3", "quote": "同步前不必核哈希"},
                  {"report_id": "ms-codex-1", "quote": "frozen_at 写成了尚未到达的计划时间"}]},
    {"rule": "出处必须两端都打得开", "why": "只有一个事件身份", "category": "出处可达",
     "evidence": [{"report_id": "ms-codex-3", "quote": "同步前不必核哈希"},
                  {"report_id": "us3-2", "quote": "文件名时间比实际收阅时间晚"}]},
]
calls = []


def fake_model(prompt, model, config_dir=None):
    calls.append(prompt.count("<<<判决件 ") // 2)
    return {"scanned": 3, "candidates": CANDS}


REAL_CALL_MODEL = m.call_model  # 真的分流函数；下面几段会把 m.call_model 换成假模型
m.call_model = fake_model

print("== A 正常批：只应接受第 1 条 ==")
reset_state()
T = table(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |"])
rc = m.collect(T, DOCS, False, 24, "fake")
txt = io.open(T, encoding="utf-8").read()
rows = [l for l in txt.split("\n") if l.startswith("| LG-")]
ok("A1 返回 0", rc == 0)
ok("A2 只新增 1 行（LG-02）", len(rows) == 2 and rows[1].startswith("| LG-02 |"))
ok("A3 新行带 加入 今日（自动） 标记", f"加入 {TODAY} " in rows[1] and "（自动）" in rows[1])
ok("A4 新行引用两件不同来源", "ms-codex-1" in rows[1] and "us3-2" in rows[1])
st = json.load(io.open(STATE, encoding="utf-8"))
ok("A5 观察记录 4 条（同批近似/虚构引文/越界/单事件）", len(st["observations"]) == 4)
ok("A6 processed 记录 3 件（report_id@mtime）、非来源目录被忽略", sorted(x.split("@")[0] for x in st["processed"]) == ["ms-codex-1", "ms-codex-3", "us3-2"])
ok("A7 模型只收到 3 件", calls[-1] == 3)
reasons = " | ".join(o["reason"] for o in st["observations"])
ok("A8 虚构引文被点名", "引文在原文中找不到" in reasons)
ok("A9 越权规则被拦", "不自动生效" in reasons)

print("== B 立即重跑：无新件 ==")
rc = m.collect(T, DOCS, False, 24, "fake")
ok("B1 返回 0 且表未变", rc == 0 and io.open(T, encoding="utf-8").read().count("| LG-") == 2)

print("== C 日配额从表推导：表里已有 2 条当天自动行 ==")
reset_state()
T = table(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |",
           f"| LG-02 | 拟生效（至 2099-01-01 00:00） | 甲 | 乙 | 源；加入 {TODAY} 09:00（自动） |",
           f"| LG-03 | 拟生效（至 2099-01-01 00:00） | 丙 | 丁 | 源；加入 {TODAY} 09:01（自动） |"])
rc = m.collect(T, DOCS, False, 24, "fake")
ok("C1 不新增（日上限）", io.open(T, encoding="utf-8").read().count("| LG-") == 3)
st = json.load(io.open(STATE, encoding="utf-8"))
ok("C2 观察记录含 日上限", any("上限" in o["reason"] for o in st["observations"]))

print("== D 预算积压：把预算压到只装得下 1 件 ==")
reset_state()
m.BUNDLE_CAP = 260
T = table(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |"])
rc1 = m.collect(T, DOCS, False, 24, "fake")
st = json.load(io.open(STATE, encoding="utf-8"))
ok("D1 第一轮只处理 1 件、积压 2 件", calls[-1] == 1 and len(st["pending"]) == 2)
rc2 = m.collect(T, DOCS, False, 24, "fake")
st = json.load(io.open(STATE, encoding="utf-8"))
ok("D2 第二轮先处理积压（模型收到 1 件）、积压减为 1", calls[-1] == 1 and len(st["pending"]) == 1)
rc3 = m.collect(T, DOCS, False, 24, "fake")
st = json.load(io.open(STATE, encoding="utf-8"))
ok("D3 第三轮清空积压、三件全部 processed", len(st["pending"]) == 0 and len(st["processed"]) == 3)
m.BUNDLE_CAP = 120000

print("== E 否决记录优先 ==")
reset_state()
T = table(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |",
           "| LG-02 | 拟生效（至 2026-09-01 00:00） | 写冻结时刻只写实测时钟，不写计划时间 | 事 | 源；加入 2026-08-29 00:00（自动） |"])
io.open(os.path.join(DOCS, "工作传递", "协作教训-否决记录.md"), "w", encoding="utf-8", newline="\n").write(
    "现役\n\n| 编号 | 日期 | 谁 | 理由 |\n|---|---|---|---|\n| LG-02 | 2026-09-08 | 负责人 | 不要 |\n")
rc = m.promote(T)
txt = io.open(T, encoding="utf-8").read()
ok("E1 promote 不升格、状态同步为 否决（见否决记录）", "| LG-02 | 否决（见否决记录） |" in txt and "生效（2026" not in txt.split("LG-02")[1].split("\n")[0])
rc = m.collect(T, DOCS, False, 24, "fake")
st = json.load(io.open(STATE, encoding="utf-8"))
ok("E2 与已否决行近似的候选不进表", io.open(T, encoding="utf-8").read().count("| LG-") == 2 and any("否决" in o["reason"] for o in st["observations"]))

print("== F 状态文件失败时表仍算提交 ==")
reset_state()
T = table(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |"])
orig_save = m.save_state
m.save_state = lambda st: (_ for _ in ()).throw(OSError("disk"))
rc = m.collect(T, DOCS, False, 24, "fake")
m.save_state = orig_save
ok("F1 返回 4、表已写入 1 行", rc == 4 and io.open(T, encoding="utf-8").read().count("| LG-") == 2)
rc = m.collect(T, DOCS, False, 24, "fake")
ok("F2 重跑不重复加行（靠表去重）、日配额不放大", io.open(T, encoding="utf-8").read().count("| LG-") == 2)

print("== G 已生效行被否决记录点名：promote 同步为否决；publish 扣除它 ==")
reset_state()
T = table(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |",
           "| LG-02 | 生效（2026-09-01 自动，48h 无异议） | 规矩二 | 事二 | 源；加入 2026-08-29 00:00（自动） |",
           "| LG-03 | 拟生效（至 2099-01-01 00:00） | 规矩三 | 事三 | 源；加入 2026-09-01 00:00（自动） |",
           "| LG-04 | 否决（负责人） | 规矩四 | 事四 | 源 |"])
io.open(os.path.join(DOCS, "工作传递", "协作教训-否决记录.md"), "w", encoding="utf-8", newline="\n").write(
    "现役\n\n| 编号 | 日期 | 谁 | 理由 |\n|---|---|---|---|\n| LG-02 | 2026-09-08 | 负责人 | 不要 |\n")
rc = m.promote(T)
txt = io.open(T, encoding="utf-8").read()
ok("G1 已生效行被否决记录点名 → 状态同步为否决", "| LG-02 | 否决（见否决记录） |" in txt)
m.publish(T)
pub = io.open(os.path.join(DOCS, "工作传递", "协作教训-生效.md"), encoding="utf-8").read()
ok("G2 生效版只含 LG-01（扣除否决/拟生效/否决记录）", "LG-01" in pub and "LG-02" not in pub and "LG-03" not in pub and "LG-04" not in pub)
ok("G3 生效版不含引文/出处/为什么", "事一" not in pub and "源" not in pub.split("- LG-01")[1] if "- LG-01" in pub else False)

print("== H 锁：占用时 collect 跳过 ==")
os.environ["HL_LOCK_PATH"] = os.path.join(ROOT, "lock")
m.LOCK_PATH = os.environ["HL_LOCK_PATH"]
io.open(m.LOCK_PATH, "w").write("busy")
rc = m.locked(m.collect, T, DOCS, False, 24, "fake")
ok("H1 锁被占用 → 返回 5、不调模型", rc == 5)
os.remove(m.LOCK_PATH)
ok("H2 陈旧锁自动清除后可运行", m.acquire_lock() and (m.release_lock() or True))

print("== I 判决件源头对账：feedback_for 指向不存在的原件 → 不算独立事件（GLM 09-09）==")
reset_state()
w("X/codex/2026-09-08_0500_e_交接报告.md", report("ms-codex-5", "ghost-orig-1", "第五件：frozen_at 又写成了计划时间。"))
w("X/codex/2026-09-08_0600_f_交接报告.md", report("ms-codex-6", "ghost-orig-2", "第六件：文件名时间又比实际晚了。"))
GHOST = [{"rule": "冻结时刻要写实测时钟不写计划", "why": "两件", "category": "时间戳",
          "evidence": [{"report_id": "ms-codex-5", "quote": "frozen_at 又写成了计划时间"},
                       {"report_id": "ms-codex-6", "quote": "文件名时间又比实际晚了"}]}]
m.call_model = lambda prompt, model, config_dir=None: {"scanned": 2, "candidates": GHOST}
T = table(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |"])
m.collect(T, DOCS, False, 24, "fake")
st = json.load(io.open(STATE, encoding="utf-8"))
ok("I1 两件判决件的 feedback_for 都指向树内不存在的原件 → 候选被拒（证据不足）", io.open(T, encoding="utf-8").read().count("| LG-") == 1 and any("证据不足" in o["reason"] for o in st["observations"]))
ok("I2 processed 记录带改动时刻（report_id@mtime）", all("@" in x for x in st["processed"]))
m.call_model = fake_model

print("== I2 判决件互引：feedback_for 指向来源目录里的另一份判决件 → 不算原始事件（GLM 09-09 三轮）==")
reset_state()
w("X/codex/2026-09-08_0700_g_交接报告.md", report("ms-codex-7", "us3-2", "第七件：frozen_at 又写成了计划时间。"))
w("X/claude-code-US3-claude/2026-09-08_0800_h_交接报告.md", report("us3-8", "ms-codex-1", "第八件：文件名时间又比实际晚了。"))
CROSS = [{"rule": "冻结时刻要写实测时钟不写计划", "why": "两件", "category": "时间戳",
          "evidence": [{"report_id": "ms-codex-7", "quote": "frozen_at 又写成了计划时间"},
                       {"report_id": "us3-8", "quote": "文件名时间又比实际晚了"}]}]
m.call_model = lambda prompt, model, config_dir=None: {"scanned": 2, "candidates": CROSS}
T = table(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |"])
m.collect(T, DOCS, False, 24, "fake")
st = json.load(io.open(STATE, encoding="utf-8"))
ok("I2-1 两件互相以对方判决件为 feedback_for → 证据不足、不进表", io.open(T, encoding="utf-8").read().count("| LG-") == 1 and any("证据不足" in o["reason"] for o in st["observations"]))
for f in ("X/codex/2026-09-08_0700_g_交接报告.md", "X/claude-code-US3-claude/2026-09-08_0800_h_交接报告.md"):
    os.remove(os.path.join(DOCS, "工作传递", f))
m.call_model = fake_model

print("== J 越界关键词补齐：改写措辞也拦住（额外一层）==")
reset_state()
EVADE = [{"rule": "反复不过的报告先移出 工作传递 目录，改好再放回", "why": "两窗口", "category": "阻塞归属",
          "evidence": [{"report_id": "ms-codex-1", "quote": "frozen_at 写成了尚未到达的计划时间"},
                       {"report_id": "us3-2", "quote": "文件名时间比实际收阅时间晚"}]}]
m.call_model = lambda prompt, model, config_dir=None: {"scanned": 2, "candidates": EVADE}
T = table(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |"])
m.collect(T, DOCS, False, 24, "fake")
st = json.load(io.open(STATE, encoding="utf-8"))
ok("J1 \"移出…目录\" 这种改写被关键词层拦下（进观察不进表）", io.open(T, encoding="utf-8").read().count("| LG-") == 1 and any("不自动生效" in o["reason"] for o in st["observations"]))
m.call_model = fake_model

print("== K 二轮：旧裸 report_id 不再永久跳过；publish 超 15 条不截断（GLM 09-09 二轮）==")
reset_state()
st = json.load(io.open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {"last_scan_utc": None, "processed": [], "pending": [], "observations": []}
st["processed"] = ["ms-codex-1", "us3-2", "ms-codex-3"]  # 09-09 首跑留下的旧格式条目
json.dump(st, io.open(STATE, "w", encoding="utf-8"))
calls.clear()
T = table(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |"])
m.collect(T, DOCS, False, 24, "fake")
ok("K1 旧裸 id 在 processed 里，改动过的件仍进模型（不再被 or 子句永久跳过；来源目录共 5 件全送）", calls and calls[-1] == 5)
T = table([f"| LG-{i:02d} | 生效 | 规矩{i} | 事{i} | 源 |" for i in range(1, 17)])
os.remove(os.path.join(os.path.dirname(T), "协作教训-否决记录.md"))  # G 段留下的否决 LG-02 会扣掉一条
rc = m.publish(T)
live = io.open(os.path.join(os.path.dirname(T), "协作教训-生效.md"), encoding="utf-8").read()
ok("K2 16 条生效：生效版全发 16 条、不截断（只打警告）", rc == 0 and live.count("\n- LG-") == 16 and "共 16 条" in live)

print("== L 提供方可切换：glm 走智谱订阅额度，claude 走本机账号（负责人 09-10）==")
SSE = ['data: {"model":"glm-5.3","choices":[{"delta":{"content":"{\\"scanned\\": 2, \\"candi"}}]}',
       'data: {"choices":[{"delta":{"content":"dates\\": []}"}}],"usage":{"prompt_tokens":12,"completion_tokens":3}}',
       "data: [DONE]", "data: 这行不是 JSON，应被忽略", ""]
txt, usage, served = m.glm_sse_join(SSE)
ok("L1 SSE 行流拼回正文、取出 usage 与服务端回填的 model",
   json.loads(txt) == {"scanned": 2, "candidates": []} and usage["prompt_tokens"] == 12 and served == "glm-5.3")
ok("L2 坏行不炸、[DONE] 之后不再拼", m.glm_sse_join(["data: 坏", "", "data: [DONE]"])[0] == "")
_k = os.environ.pop("GLM_API_KEY", None)
try:
    m.call_model_glm("x")
    ok("L3 没有 GLM_API_KEY 时明确报错、不静默", False)
except RuntimeError as e:
    ok("L3 没有 GLM_API_KEY 时明确报错、不静默", "GLM_API_KEY" in str(e))
finally:
    if _k is not None:
        os.environ["GLM_API_KEY"] = _k
seen = {}
m.call_model_glm = lambda prompt, model=None: seen.setdefault("glm", model) or {"scanned": 0, "candidates": []}
m.call_model_claude = lambda prompt, model, config_dir=None: seen.setdefault("claude", model) or {"scanned": 0, "candidates": []}
m.PROVIDER = "glm"
REAL_CALL_MODEL("提示词", "sonnet", "某账号目录")
ok("L4 provider=glm 时不碰 claude CLI，且默认 sonnet 不会被当成 GLM 的模型名", "claude" not in seen and "glm" in seen and seen["glm"] is None)
m.PROVIDER = "claude"
REAL_CALL_MODEL("提示词", "sonnet", "某账号目录")
ok("L5 provider=claude 时仍走 claude CLI", seen.get("claude") == "sonnet")
m.PROVIDER = "claude"

print("== K 被拒候选池与新增类目（v3.6）==")
reset_state()
if os.path.exists(m.POOL_PATH):
    os.remove(m.POOL_PATH)
T = table(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |"])
EV2 = [{"report_id": "ms-codex-1", "quote": "frozen_at 写成了尚未到达的计划时间"},
       {"report_id": "us3-2", "quote": "文件名时间比实际收阅时间晚"}]
KCANDS = [
    {"rule": "结论被更正后在索引标处置，口径冲突时指明唯一现行真源", "why": "两次索引失修", "category": "正本与索引维护",
     "evidence": EV2},
    {"rule": "验收按实际证据等级写，作者自测不写成独立复核", "why": "两次拔高", "category": "验收与状态",
     "evidence": EV2},
    {"rule": "引用回执或跟进件来判断当前状态之前，先看清楚件内的观测或冻结时刻，文件名里的时间只是起草时点，绝不能当作结论的公布时刻来引用，两个时刻必须分开", "why": "超长", "category": "时间戳",
     "evidence": EV2},
    {"rule": "含糊指令先问再动", "why": "类别不合", "category": "其他",
     "evidence": [{"report_id": "ms-codex-3", "quote": "同步前不必核哈希"}]},
    {"rule": "规矩一", "why": "与现有重复", "category": "格式与字段",
     "evidence": EV2},
]
m.call_model = lambda prompt, model, config_dir=None: {"scanned": 3, "candidates": KCANDS}
rc = m.collect(T, DOCS, False, 24, "fake")
txt = io.open(T, encoding="utf-8").read()
rows = [l for l in txt.split("\n") if l.startswith("| LG-")]
ok("K1 新类目「正本与索引维护」可自动进表", len(rows) == 3 and "正本与索引维护" in rows[1])
ok("K2 新类目「验收与状态」可自动进表", "验收与状态" in rows[2])
pool = json.load(io.open(m.POOL_PATH, encoding="utf-8"))
items = pool.get("items", [])
pends = [x for x in items if x.get("status") == "pending"]
ok("K3 超字数候选入池且带拒因", any("超过" in x.get("reason", "") for x in pends))
ok("K4 类别不合/证据不足候选入池", any(x.get("rule") == "含糊指令先问再动" for x in pends))
ok("K5 池条目带核验过的证据件相对路径", all(x.get("evidence") for x in pends) and
   any(str(x["evidence"][0].get("rel", "")).endswith("_交接报告.md") for x in pends))
ok("K6 与现有行近似的不入池", not any("规矩一" in x.get("rule", "") for x in items))
ok("K7 池条目有 RP 编号且待裁量", all(str(x.get("id", "")).startswith("RP-") for x in items))
n_before = len(pends)
reset_state()
m.collect(T, DOCS, False, 24, "fake")
pends2 = [x for x in json.load(io.open(m.POOL_PATH, encoding="utf-8"))["items"] if x.get("status") == "pending"]
ok("K8 池内去重：重跑同样的候选不重复入池", len(pends2) == n_before)

print("== M 归档与池的收尾（v3.6.2，fable 2026-09-21_1210 件）==")
pa = w("X/codex/_archive/2026-09-01_0100_归档的评审件_交接报告.md", report("arch-judge-1", "orig-1", "评审正文"))
pb = w("X/claude-code/_archive/2026-09-01_0200_归档的原件_交接报告.md", report("arch-orig-1", "", "原件正文"))
ok("M1 判来源目录时跳过 _archive 这一级", m.source_dir_of(pa) == "codex" and m.source_dir_of(pb) == "claude-code")
kid = m.known_report_ids(DOCS)
ok("M2 评审来源的归档件不算「原始事件」，非评审来源的归档原件仍算", "arch-judge-1" not in kid and "arch-orig-1" in kid)
ok("M3 归档件不再当新件送读", not any("_archive" in p.replace("\\", "/") for p in m.enumerate_new(DOCS, datetime(2000, 1, 1, tzinfo=timezone.utc))))
_pool = {"items": [{"id": f"RP-{i:03d}", "rule": f"占位{i:02d}号" + chr(0x4e00 + i * 37) * 6, "why": "w", "category": "其他",
                    "reason": "r", "evidence": [], "date": "2026-09-01", "status": "pending"} for i in range(1, 21)]}
json.dump(_pool, io.open(m.POOL_PATH, "w", encoding="utf-8"), ensure_ascii=False)
reset_state()
m.collect(T, DOCS, False, 24, "fake")
_items = json.load(io.open(m.POOL_PATH, encoding="utf-8"))["items"]
_ev = [x for x in _items if x.get("status") == "evicted"]
ok("M4 池满：最老的待裁量项标 evicted 留痕（不是整条删掉），待裁量仍不超过 20",
   len(_ev) >= 1 and all(x.get("evicted") for x in _ev) and _ev[0]["id"] == "RP-001"
   and len([x for x in _items if x.get("status") == "pending"]) <= 20 and len(_items) > 20)
io.open(m.POOL_PATH, "w", encoding="utf-8").write("{broken json")
_got = m.load_pool()
_kept = [f for f in os.listdir(os.path.dirname(m.POOL_PATH)) if ".corrupt-" in f]
ok("M5 池文件读不出来：改名留存，不当空池直接覆盖", _got == {"items": []} and len(_kept) == 1
   and io.open(os.path.join(os.path.dirname(m.POOL_PATH), _kept[0]), encoding="utf-8").read() == "{broken json")

pc = w("X/codex/_archive/2026-09/2026-09-01_0300_按月分层的归档评审件_交接报告.md", report("arch-judge-2", "orig-1", "评审正文"))
ok("M6 归档下面再分月份：来源目录仍判成 codex，不算原始事件", m.source_dir_of(pc) == "codex" and "arch-judge-2" not in m.known_report_ids(DOCS))
_up = os.path.join(ROOT, "_archive", "快照", "docs")
_pu = os.path.join(_up, "工作传递", "X", "codex", "2026-09-01_0400_上层目录叫archive_交接报告.md")
os.makedirs(os.path.dirname(_pu), exist_ok=True)
io.open(_pu, "w", encoding="utf-8").write(report("up-1", "orig-1", "正文"))
ok("M7 工作区上层目录恰好叫 _archive：不会把整棵树当归档件漏掉", not m.is_archived(_pu) and m.source_dir_of(_pu) == "codex")
io.open(m.POOL_PATH, "w", encoding="utf-8").write("[1, 2]")
ok("M8 池文件是合法 JSON 但不是 {items:[…]} 结构：同样改名留存，不原样返回去炸下游", m.load_pool() == {"items": []})
json.dump({"items": [{"id": "RP-900", "rule": "好池里的一条", "status": "pending"}]}, io.open(m.POOL_PATH, "w", encoding="utf-8"), ensure_ascii=False)
_good = io.open(m.POOL_PATH, encoding="utf-8").read()
_ro = m.io.open
def _deny(p, *a, **k):
    if os.path.abspath(str(p)) == os.path.abspath(m.POOL_PATH) and (not a or a[0] == "r"):
        raise PermissionError("对方正在替换")
    return _ro(p, *a, **k)
T = table(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |"])   # 回到干净的表，保证这一轮真的有候选要入池（否则下面是空过）
reset_state()
_called = {"n": 0}
_lp = m.load_pool
def _counting_load_pool():
    _called["n"] += 1
    return _lp()
m.load_pool = _counting_load_pool
m.io.open = _deny
try:
    _lp(); _raised = False
except OSError:
    _raised = True
_rc = m.collect(T, DOCS, False, 24, "fake")
m.io.open = _ro
m.load_pool = _lp
_d = os.path.dirname(m.POOL_PATH)
ok("M9 池一时读不到（权限／对方正在替换）：load_pool 抛 OSError 不当损坏；collect 真走到了入池这一步、照常收尾、好池原样不动",
   _raised and _called["n"] >= 1 and _rc == 0 and io.open(m.POOL_PATH, encoding="utf-8").read() == _good
   and len([f for f in os.listdir(_d) if ".corrupt-" in f]) == 2)  # 只有 M5、M8 那两份，没有新增

n_fail = sum(1 for _, c in results if not c)
print(f"\n合计 {len(results)} 项，失败 {n_fail} 项")
shutil.rmtree(ROOT, ignore_errors=True)
sys.exit(1 if n_fail else 0)
