#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v1.9 · 2026-09-21 · 按 fable 复验（2026-09-21_1210 件）改五点：①规范扫描的"新发现"改按扫描器 `#keys` 行给的**稳定键**比
    （v1.8 的指纹取自截断后的 stdout：超过 20 条后新增 12 次漏 8 次；且"冻结已 N 天"每天变会天天误报）；旧版状态首轮只记基线；
    ②**采纳要带处理页口令**：页面上的「采纳」链接带一段本机随机种子＋候选正文算出的短口令，decide 核对——网页、误触、
    记着旧编号的脚本都拿不到；同时把"负责人读到的文字"和"写进表的文字"绑在一起。防不了能读本机状态文件的恶意程序，
    那一层仍靠 48 小时否决窗；③**由池采纳的规矩，「同意」不再静音到期催告**（否则 adopt＋ok 两步就能让一条被程序拦下的
    规矩悄悄生效）；④采纳行的规矩文字压平空白（含换行会把表格行折断）、更新记录改用每日学习同一个插入口径（最新在上）；
    ⑤处理页写出"另有 N 条因池满已过期"。
handoff_notify.py —— 桌面通知与看门狗（Windows 常驻弹窗；Linux 只记日志，如实写"未送达"）
v1.8 · 2026-09-21 · 按 US3 Claude fable 独立核查（2026-09-21_0235 件）修四处：①adopt 写表改走 lessons 的
    锁＋哈希门（原先能覆盖并发写入并撞号；空表时 max([]) 崩）；入口无鉴权如实写明（安全边界＝48h 否决窗＋留痕）；
    ②check() 收尾状态改 merge_save_state——运行期间点的「同意」不再被整份写回抹掉；③规范扫描触发改按
    **逐条指纹新增**（条数会被显示上限卡住、增长永不触发）＋扫描没跑成也进"需要你介入"；④池溢出改留痕（lessons 侧）。
（v1.7 · 2026-09-20 · 新增 --with-flow：每 4 小时顺跑 handoff_flow.py（工作传递三层规范的机检，report-only），
    清单落 工作传递/规范扫描-待处理.md 进"系统自己在做"区；发现比上轮**变多**才给负责人一条当日提醒（负责人令"要盯着指出"）。
（v1.6 · 2026-09-20 · 被拒候选池上处理页（负责人 09-19/09-20：好候选被拒后只沉日志＝没学）：新增「被拒的好点子」区，
    每条给「采纳/不用」按钮；采纳＝写成人工行进表（拟生效 48h，出处注明原拒因），不用＝翻篇。协议注册条件从
    "有拟生效规矩"扩为"有拟生效规矩或有待裁量候选"。弹窗契约不变：池子本身不触发弹窗，只在页面上出现。
（v1.5 · 2026-09-10 · 按负责人反馈改弹窗与静默：倒计时说人话（不再出现"还有 0 小时"）· 到期在即时逐条列全并先说怎么办
    · 升级窗 6→12 小时（看门狗 4 小时一轮，6 小时窗最晚只提前几十分钟）· 所有子进程不再闪控制台窗口
    · 容忍 stdout 为 None（计划任务改用 pythonw.exe）· 弹窗署名从 Windows PowerShell 换成自己的应用名
    · 弹窗上给出真的介入手段：「否决 LG-xx」按钮一点就写进否决记录（自定义协议 handoff-veto:）
（v1.4 · 09-09 按 GLM 二轮复核：扫描只滤 G6 断链不滤 G6P；到期前升级文案改成要动作的写法）
（v1.3 · 同日按 GLM 复核：拟生效行到期前 6 小时升为"需要你介入"常驻提醒（每个到期只升一次）；状态页写明看门狗自指盲区）
（v1.2 · 同日 Codex+Astra：生产扫描收集阶段不设 cap，防 G8 饥饿；v1.1 · 09-08 按 Codex sil-codex-20260908-03 §四 C 补"从未成功过"的宽限截止）

  toast "<标题>" "<正文>"          立刻弹一条（用来测试送达）
  rule <ok|no>/<编号> --table <协作教训.md> [--who 谁]
        负责人对一条规矩拍板（处理状态页上的两个按钮就是拉起这条命令）：
          no → 追加一行到同目录的否决记录（只追加、不改已有行、重复点不重复写）
          ok → 记在看门狗状态里，以后不再拿这条提醒（不动任何 docs 文件）
        **只由人点按钮或手敲触发**，自动流程一行都不碰否决记录；编号必须在表里真实存在
  check <协作教训.md> [--with-scan <docs/工作传递>] [--scan-hours 8] [--with-flow <docs 根>] [--flow-days 2]
        看门狗：独立于每日学习任务运行，判断该不该提醒，去重后弹窗并写日志
        另查一件事：**计划任务上次运行的结果码**（走 PowerShell 的 Get-ScheduledTaskInfo，不用 schtasks /V——
        带 CREATE_NO_WINDOW 时它不输出那几行）。非 0 就当场报：脚本被杀时连一行日志都写不出，
        光靠"多久没成功"要等 36 小时才发现（09-10 实况：HandoffDaily 被关窗口杀掉，结果码 0xC000013A）
        提醒四类：① 新的"拟生效"行（48 小时内可否决；到期前 6 小时若仍未否决，升为"需要你介入"常驻一次）
                  ② 当天由脚本自动处理的行（转生效／否决同步）
                  ③ 每日学习太久没有成功运行：有成功记录 → 距上次成功超过 36 小时；
                     从未成功 → 距本看门狗首次发现该定时任务超过 36 小时（首次发现时刻持久记录）
                  ④ --with-scan：过去 N 小时改动的交接报告里没过写后检查的（**不管是谁写的**：ZCode、Codex、
                     从 US3 同步下来的都算）＋ 索引 README 的链接写错（G8）——**不弹给负责人**，写进 docs 树的「写后检查-待处理.md」让各 AI 自查；
                     只有同一来源目录一轮 ≥3 份新不合格才弹一条"那个窗口可能没在看提示"
状态：~/.claude/tools/handoff_notify_state.json（每个提醒键只弹一次；故障每天最多提醒一次；弹不出最多重试 3 次）
日志：~/.claude/tools/logs/handoff_notify.log（弹窗失败也记一行"未送达"，不假装已通知）
边界：弹窗只在这台电脑登录会话里可见；人不在电脑前看不到；整机关机时它自己也不跑。这不是离机告警。
     弹出成功也只证明交给了系统，不证明负责人看过。
"""
import io, json, os, re, sys, subprocess, hashlib, platform, urllib.parse, html, secrets
from datetime import datetime, timezone, timedelta

BJ = timezone(timedelta(hours=8))
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.environ.get("HANDOFF_TOOLS_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "tools")  # 测试指到临时目录
AUTO_PUBLISH = True  # 生效版凭证与表不一致时自动重跑 publish（同机同锁，不违反单发布者）；测试关掉
OWNER = os.environ.get("HANDOFF_OWNER") or "负责人"  # 状态页里示例否决行的"谁"列；分发出去的脚本不带人名
TODO_WRITER = "Windows 看门狗 HandoffNotify（每 4 小时；本机专属，US3 有自己的 写后检查-待处理-US3.md）"
FLOW_WRITER = "Windows 看门狗 HandoffNotify（每 4 小时；本机专属，US3 有自己的 规范扫描-待处理-US3.md）"
STATE_PATH = os.environ.get("HN_STATE_PATH") or os.path.join(TOOLS, "handoff_notify_state.json")
POOL_PATH = os.environ.get("HL_POOL_PATH") or os.path.join(TOOLS, "handoff_rejected_pool.json")  # 被拒候选池（v1.6，lessons 写、这里读/裁量）
LESSONS_STATE = os.environ.get("HL_STATE_PATH") or os.path.join(TOOLS, "handoff_lessons_state.json")
LOG_PATH = os.environ.get("HN_LOG_PATH") or os.path.join(TOOLS, "logs", "handoff_notify.log")
TASK_NAMES = ("HandoffDaily", "HandoffLessons")
# CREATE_NO_WINDOW：本脚本起的每个子进程都带上，否则计划任务每轮都在屏幕上闪一下控制台（负责人 09-10 反馈）
NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0
# 到期前多久把"拟生效"升为需要介入：看门狗每 4 小时一轮，窗口必须明显大于 4 小时，
# 否则唯一那次提醒可能落在到期前几十分钟（09-10 实况：16:00 才提醒 16:35 到期）。12 小时 ⇒ 至少提前 8 小时
PENDUE_HOURS = 12
# 弹窗的"发信人"：不注册就只能借 powershell.exe 的身份，通知里显示成 Windows PowerShell（负责人 09-10 指出不像自己人）
APP_ID = os.environ.get("HANDOFF_APPID") or "HandoffGate.Lessons"
APP_NAME = os.environ.get("HANDOFF_APPNAME") or "协作教训"
RULE_SCHEME = os.environ.get("HANDOFF_RULE_SCHEME") or "handoff-rule"  # 页面上「同意/不采纳」按钮走的自定义协议
VETO_NAME = "协作教训-否决记录.md"
STALE_HOURS = 36
ROW_PAT = re.compile(r"^\| LG-(\d+) \|")
PEND_PAT = re.compile(r"^拟生效（至 (\d{4}-\d{2}-\d{2} \d{2}:\d{2})）")


def now_bj():
    return datetime.now(timezone.utc).astimezone(BJ)


def log(line):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with io.open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{now_bj():%Y-%m-%d %H:%M} {line}\n")
    print(line)


def load_json(p, default):
    try:
        return json.load(io.open(p, encoding="utf-8"))
    except Exception:
        return default


def page_secret():
    """处理页口令的本机种子（看门狗状态里的 page_secret；check() 开头保证它存在）。没有就返回 None。"""
    return (load_json(STATE_PATH, {}) or {}).get("page_secret") or None


def pool_token(ent, secret=None):
    """一条被拒候选的采纳口令＝sha256(种子|编号|规矩|为什么|类别|拒因|证据件) 前 10 位。
    绑住所有会写进表的字：池被重建、编号换了人、或有人只改了"为什么/证据"，旧页面的链接都自动作废。"""
    secret = secret or page_secret()
    if not secret:
        return None
    ev = "；".join(f"{e.get('report_id')}@{e.get('rel')}" for e in (ent.get("evidence") or [])[:3] if isinstance(e, dict))
    body = "|".join(str(ent.get(k, "")) for k in ("id", "rule", "why", "category", "reason")) + "|" + ev  # 凡是会写进表的字都绑进去
    return hashlib.sha256(f"{secret}|{body}".encode("utf-8")).hexdigest()[:10]


def merge_save_state(st):
    """落盘看门狗状态前先并上磁盘版（fable 09-21 抓的竞态）：check() 运行期间负责人点了「同意」，
    decide() 已把 agreed 写进磁盘；结尾若直接整份写回内存里的旧 st，会把那笔抹掉、之后继续催。
    磁盘上 decide 可写的键（agreed）以磁盘为准；本轮新增的 notified/attempts 以内存为准。"""
    try:
        disk = load_json(STATE_PATH, {}) or {}
    except Exception:
        disk = {}
    if disk.get("page_secret"):
        st["page_secret"] = disk["page_secret"]  # 磁盘优先：页面口令是按磁盘上的种子算的，别被内存里的旧值盖掉
    for k in ("agreed",):
        if isinstance(disk.get(k), dict) or isinstance(st.get(k), dict):
            st[k] = {**(st.get(k) or {}), **(disk.get(k) or {})}  # 磁盘（可能刚被 decide 写过）优先
    for k in ("notified", "attempts"):
        if isinstance(disk.get(k), dict) or isinstance(st.get(k), dict):
            m = dict(disk.get(k) or {})
            m.update(st.get(k) or {})
            st[k] = m
    save_json(STATE_PATH, st)


def save_json(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    io.open(tmp, "w", encoding="utf-8", newline="").write(json.dumps(obj, ensure_ascii=False, indent=1))
    os.replace(tmp, p)


def file_uri(p):
    """本地文件的可点链接。中文要百分号编码，但盘符后的冒号和斜杠必须保持原样，
    否则会变成 file:///C%3A/... —— Windows 的 URI 解析器认不出来（09-08 实测踩过）。"""
    return "file:///" + urllib.parse.quote(os.path.abspath(p).replace("\\", "/"), safe="/:")


def human_left(td):
    """剩余时间说人话：3 天 2 小时 / 5 小时 30 分钟 / 32 分钟 / 不到 1 分钟。
    不用整小时取整——09-10 弹窗把 32 分钟显示成"还有 0 小时"，负责人看不出这是最后通知。"""
    s = int(td.total_seconds())
    if s < 60:
        return "不到 1 分钟"
    d, r = divmod(s, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return f"{d} 天 {h} 小时" if h else f"{d} 天"
    if h:
        return f"{h} 小时 {m} 分钟" if m else f"{h} 小时"
    return f"{m} 分钟"


def cut(s, n):
    """截断只在真的截了的时候才加省略号（旧版一律硬切 58 字，句子断在半路还不带提示）。"""
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n] + "…"


def ensure_appid():
    """把自己注册成一个有名字的通知来源（注册表 HKCU 下 Software/Classes/AppUserModelId/<APP_ID>）。
    不注册也能弹，但通知中心会显示成"Windows PowerShell"。图标是本函数自己画的一张纯色 PNG（不依赖任何三方库）。
    失败一律吞掉：弹窗本身不能因为改个署名而弹不出来。返回可用的 AppUserModelID，失败返回 None。"""
    if platform.system() != "Windows" or os.environ.get("HANDOFF_NO_REGISTER") == "1":
        return None  # 测试用 HANDOFF_NO_REGISTER 隔离：跑用例不碰真实注册表（同 HANDOFF_TOOLS_DIR 那条隔离承诺）
    try:
        import winreg, struct, zlib
        icon = os.path.join(TOOLS, "handoff_toast_icon.png")
        if not os.path.exists(icon):
            size, rgb = 64, (37, 99, 146)
            raw = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
            def _chunk(t, d):
                return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
            png = (b"\x89PNG\r\n\x1a\n"
                   + _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
                   + _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b""))
            os.makedirs(os.path.dirname(icon), exist_ok=True)
            with open(icon, "wb") as f:
                f.write(png)
        key_path = "Software\\Classes\\AppUserModelId\\" + APP_ID
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, icon)
        return APP_ID
    except Exception as e:
        log(f"通知署名未能注册（不影响弹窗，仍会显示成 Windows PowerShell）：{type(e).__name__}")
        return None


def ensure_protocol(table_path):
    """注册 handoff-veto: 协议，让弹窗按钮能真的执行一次否决（而不是只打开一个页面看）。
    命令固定用 pythonw.exe（点按钮时不闪控制台），并把本机的教训表路径写死进去。
    ⚠ 注册 URL 协议意味着任何程序/网页都能拉起它，所以 decide() 那边只认 `ok|no` + `LG-数字`，且编号必须在表里真实存在；
    最坏后果是给某条规矩多写一行否决——可见、可撤（删掉那行即可），不会动别的文件。
    失败返回 None，调用方就不放按钮。"""
    if os.environ.get("HANDOFF_NO_REGISTER") == "1":
        return RULE_SCHEME  # 测试：不写注册表，但按钮与文案照常走这条分支
    if platform.system() != "Windows":
        return None
    try:
        import winreg
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        exe = pyw if os.path.exists(pyw) else sys.executable
        cmd = f'"{exe}" -X utf8 "{os.path.join(HERE, os.path.basename(__file__))}" rule "%1" --table "{os.path.abspath(table_path)}"'
        base = "Software\\Classes\\" + RULE_SCHEME
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "URL:" + APP_NAME + " 拍板")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + "\\shell\\open\\command") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, cmd)
        return RULE_SCHEME
    except Exception as e:
        log(f"拍板按钮未能注册（页面仍可看，只是少两个按钮）：{type(e).__name__}")
        return None


def decide(arg, table_path, who=None):
    """负责人对一条规矩/候选拍板。自动流程不碰；但入口**没有鉴权**——本机任何程序都能调这条命令，
    ok 只是记"已确认"、no 会写否决行、adopt 会加规矩行（fable 09-21 核查指出）。安全边界＝
    48 小时否决窗＋每次动作的弹窗留痕＋更新记录里记 who；非本人操作请及时否决。
    arg 形如 `ok/LG-06`、`no/LG-06`、`adopt/RP-003`、`drop/RP-003`，或协议串 `handoff-rule:no/LG-06`。
      no    = 不采纳 → 往否决记录追加一行（只追加、不改已有行、重复点不重复写）
      ok    = 同意   → 记在看门狗状态里，以后不再拿这条提醒你（不动表、不动任何 docs 文件）
      adopt = 采纳被拒候选（v1.6）→ 写成人工行进表（拟生效 48h、出处注明程序当时的拒因），池里标记 adopted
      drop  = 候选翻篇 → 池里标记 ignored，页面不再列
    LG 编号必须在表里真实存在、RP 编号必须在池里且待裁量；动作与编号都不合法就什么都不做。"""
    raw = urllib.parse.unquote((arg or "").strip().strip('"'))
    if raw.lower().startswith(RULE_SCHEME + ":"):
        raw = raw[len(RULE_SCHEME) + 1:]
    raw = raw.strip().strip("/")
    act, _, lid = raw.partition("/")
    lid, _, token = lid.partition("/")
    act, lid, token = act.strip().lower(), lid.strip(), token.strip().lower()
    if act not in ("ok", "no", "adopt", "drop") or not re.fullmatch(r"(LG|RP)-\d{2,4}", lid) \
            or (token and not re.fullmatch(r"[0-9a-f]{10}", token)):
        log(f"拍板：参数不合法，忽略（{raw[:60]!r}）")
        return 2
    now = datetime.now(BJ)
    if act in ("adopt", "drop"):
        pool = load_json(POOL_PATH, {}) or {}
        ent = next((x for x in pool.get("items", [])
                    if str(x.get("id", "")) == lid and str(x.get("status", "pending")) == "pending"), None)
        if not ent:
            log(f"拍板：池里没有待裁量的 {lid}，忽略")
            toast("没找到这条候选", f"被拒候选里没有编号 {lid} 的待裁量的条目，什么都没有改。", [], persistent=False)
            return 2
        if act == "drop":
            ent["status"], ent["decided"] = "ignored", f"{now:%Y-%m-%d %H:%M}"
            save_json(POOL_PATH, pool)
            log(f"拍板：{lid} 不用，已翻篇")
            toast("好，这条就翻篇了", f"「{cut(str(ent.get('rule', '')), 46)}」\n以后不再列在候选里。", [], persistent=False)
            return 0
        # v1.9：采纳必须带处理页口令（见 pool_token）。它是唯一能"加规矩"的动作，别的动作方向都是安全的。
        want = pool_token(ent)
        if not want or token != want:
            log(f"拍板：{lid} 采纳被拒——口令{'缺失' if not token else '不对'}（不是从最新处理页点的，或候选正文已变）")
            toast("这次采纳没有生效", "采纳要从最新的处理页上点（链接里带一段本机口令）。请重新打开处理页再点一次；"
                  "如果你没点过，说明有别的程序在试这个入口，看一眼日志。", [], persistent=False)
            return 2
        # adopt：写成人工行（拟生效 48h；人工行不受 60 字自动上限约束，同 LG-06/07 先例）。
        # fable 09-21 核查抓的三处都修在这里：①写表要走 lessons 的锁＋哈希门（否则能覆盖别人刚写的行、撞号）；
        # ②空表时 max([]) 会炸；③本入口没有鉴权——任何本机程序都能调，安全边界只有 48h 否决窗＋采纳弹窗留痕，
        # 如实写明，别再写"只有人点按钮才会到这"。
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("hlk", os.path.join(HERE, "handoff_lessons.py"))
        L = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(L)
        if not L.acquire_lock():
            log("拍板：每日学习正在写表，采纳稍后再试")
            toast("现在有点忙", "每天早上自动学习正在写教训表，几分钟后重点一次「采纳」就行。", [], persistent=False)
            return 2
        try:
            try:
                text = io.open(table_path, encoding="utf-8").read()
            except OSError as e:
                log(f"拍板：读不到教训表 {table_path}：{e}")
                return 2
            rows_no = [int(m.group(1)) for m in (re.match(r"\| LG-(\d+)", ln) for ln in text.split("\n")) if m]
            nid = (max(rows_no) if rows_no else 0) + 1
            due = now + timedelta(hours=48)
            rule_txt = re.sub(r"\s+", " ", str(ent.get("rule", ""))).strip().replace("|", "／")  # 含换行会把表格行折断
            refs = "；".join(f"[{e.get('report_id')}]({e.get('rel')})".replace("|", "／") for e in (ent.get("evidence") or [])[:3]) \
                   or "（本条由负责人从被拒候选采纳，无核验过的引文）"
            why_full = (f"{ent.get('why', '')}（类别：{ent.get('category', '其他')}；负责人从被拒候选采纳，"
                        f"程序当时没让它自动生效的原因：{ent.get('reason', '')}）").replace("\n", " ")
            new_row = f"| LG-{nid:02d} | 拟生效（至 {due:%Y-%m-%d %H:%M}） | {rule_txt} | {why_full.replace('|', '／')} | {refs}；加入 {now:%Y-%m-%d %H:%M}（人工） |"
            lines = text.split("\n")
            idx = max((i for i, ln in enumerate(lines) if ln.startswith("| LG-")), default=None)
            if idx is None:
                i2 = next((j for j, ln in enumerate(lines) if ln.replace(" ", "").startswith("|---")), None)
                if i2 is None:
                    log(f"拍板：表里找不到表格，没法加行（{table_path}）")
                    toast("教训表里没找到表格", "这条候选没能写成规矩：表里找不到可以加行的位置，请手动加。", [], persistent=False)
                    return 2
                lines.insert(i2 + 1, new_row)
            else:
                lines.insert(idx + 1, new_row)
            new_text = L.add_update_line("\n".join(lines), f"- {now:%Y-%m-%d %H:%M}：{lid} 经处理页「采纳」写成人工行 LG-{nid:02d}（who={who or '未署名'}；注意：该入口本机程序均可调，非本人操作请在 48 小时内否决）。（handoff_notify.py rule adopt/…）")  # 与每日学习同口径：插在「更新记录」标题下，最新在上
            if not L.write_table(table_path, L.sha(text), new_text, "adopt"):
                toast("没写成，请再点一次", "教训表在你点采纳的瞬间被别的东西改了（防覆盖保护拦下了），"
                      "再点一次「采纳」就好。", [], persistent=False)
                return 2
        finally:
            L.release_lock()
        ent["status"], ent["decided"], ent["row"] = "adopted", f"{now:%Y-%m-%d %H:%M}", f"LG-{nid:02d}"
        save_json(POOL_PATH, pool)
        log(f"拍板：{lid} 已采纳为 {ent['row']}（人工行，48h 后生效）")
        toast("已采纳成新规矩", f"「{cut(str(ent.get('rule', '')), 46)}」\n按人工规矩进了表，48 小时后生效；"
              f"期间反悔可以在否决记录里划掉它。", [], persistent=False)
        return 0
    try:
        text = io.open(table_path, encoding="utf-8").read()
    except OSError as e:
        log(f"拍板：读不到教训表 {table_path}：{e}")
        return 2
    row = next((cells_of(ln) for ln in text.split("\n") if ln.startswith(f"| {lid} |")), None)
    if not row or len(row) < 3:
        log(f"拍板：表里没有 {lid}，忽略")
        toast("没找到这条规矩", f"表里没有编号 {lid}，什么都没有改。", [], persistent=False)
        return 2
    rule, veto_path = row[2], os.path.join(os.path.dirname(os.path.abspath(table_path)), VETO_NAME)
    now = datetime.now(BJ)
    if act == "ok":
        # 同意：本来"什么都不做"也是同意，但那样系统不知道你已经看过，还会继续提醒。
        # 记一笔，之后就不再拿这条烦你。只写看门狗自己的状态文件，不碰 docs。
        st = load_json(STATE_PATH, {}) or {}
        st.setdefault("agreed", {})[lid] = f"{now:%Y-%m-%d %H:%M}"
        save_json(STATE_PATH, st)
        log(f"拍板：{lid} 你已确认同意，之后不再提醒")
        toast("好，这条就这么定了", f"「{cut(rule, 46)}」\n以后 AI 写报告都照这条做。这条不会再提醒你。\n"
              f"改主意随时可以划掉它（编号 {lid}）。", [], persistent=False)
        return 0
    try:
        vt = io.open(veto_path, encoding="utf-8").read() if os.path.exists(veto_path) else ""
    except OSError as e:
        log(f"拍板：读不到否决记录 {veto_path}：{e}")
        return 2
    if any(ln.startswith(f"| {lid} |") for ln in vt.split("\n")):
        log(f"拍板：{lid} 已经在否决记录里，没有重复写")
        toast("这条早就划掉了", f"「{cut(rule, 46)}」\n之前已经标成不采纳（编号 {lid}），这次没重复写。", [], persistent=False)
        return 0
    lines, new = vt.split("\n"), f"| {lid} | {now:%Y-%m-%d} | {who or OWNER} | 页面上点的不采纳 |"
    i = next((j for j, ln in enumerate(lines) if ln.replace(" ", "").startswith("|---")), None)
    if i is None:
        log(f"拍板：否决记录里找不到表格，没有改动（{veto_path}）")
        return 2
    i += 1
    while i < len(lines) and lines[i].startswith("|"):
        i += 1
    lines.insert(i, new)
    for j in range(len(lines) - 1, -1, -1):  # 更新记录追加一行，便于事后对账
        if lines[j].strip().startswith("- "):
            lines.insert(j + 1, f"- {now:%Y-%m-%d %H:%M}：{lid} 经负责人在处理页上点「不采纳」划掉（{who or OWNER}）。（handoff_notify.py rule no/…）")
            break
    try:
        tmp = veto_path + ".tmp"
        io.open(tmp, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
        os.replace(tmp, veto_path)
    except OSError as e:
        log(f"拍板：写不进否决记录 {veto_path}：{e}")
        toast(f"{APP_NAME} · 否决没写成", f"{lid} 没能写进否决记录：{e}。请手动加一行。", [], persistent=False)
        return 2
    log(f"拍板：{lid} 不采纳，已写进 {veto_path}")
    toast("这条不采纳了", f"「{cut(rule, 46)}」\n以后 AI 不用照这条做了；已经在用的也会撤回。\n"
          f"改主意就删掉记录里那一行（编号 {lid}，点下面打开）。", [("看记录", file_uri(veto_path))], persistent=False)
    return 0


def toast(title, body, buttons=None, persistent=True):
    """返回 True = 已交给系统弹出（不证明被看到）；False = 未送达（并已记日志）。
    buttons: 最多三个 (按钮文字, 点击打开的 URI)，走协议激活。
    persistent: True = 常驻直到点掉（需要负责人介入的）；False = 普通弹窗，几秒后自己走、通知中心留底（仅告知）。"""
    if platform.system() != "Windows":
        log(f"未送达（非 Windows，无桌面通知链路）：{title} / {body[:80]}")
        return False
    env = dict(os.environ, HN_TITLE=title, HN_BODY=body, HN_BUTTON="知道了", HN_PERSIST="1" if persistent else "0")
    appid = ensure_appid()
    if appid:
        env["HN_APPID"] = appid  # ps1 用它当发信人；它那边失败会自动退回 powershell 身份
    for i, (label, uri) in enumerate((buttons or [])[:3], 1):
        env[f"HN_BTN{i}_LABEL"] = label
        env[f"HN_BTN{i}_ARG"] = uri
    if os.environ.get("HN_MODAL") == "1":
        ps = ("Add-Type -AssemblyName System.Windows.Forms; [void][System.Windows.Forms.MessageBox]::Show("
              "$env:HN_BODY, $env:HN_TITLE, 'OK', 'Information', "
              "[System.Windows.Forms.MessageBoxDefaultButton]::Button1, [System.Windows.Forms.MessageBoxOptions]::ServiceNotification)")
        try:
            subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
            log(f"已弹出对话框（常驻直到点确定）：{title} / {body[:80]}")
            return True
        except Exception as e:
            log(f"未送达（对话框进程异常 {type(e).__name__}）：{title}")
            return False
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-File", os.path.join(HERE, "handoff_toast.ps1")],
                           env=env, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW)
    except Exception as e:
        log(f"未送达（弹窗进程异常 {type(e).__name__}）：{title}")
        return False
    if r.returncode != 0:
        log(f"未送达（powershell 退出 {r.returncode}：{(r.stderr or '')[:100].strip()}）：{title}")
        return False
    log(f"已弹窗（{'常驻，需点掉' if persistent else '普通，自动消失、通知中心留底'}；不证明已被看到）：{title} / {body[:80]}")
    return True


def task_last_result(name):
    """计划任务上次运行的结果码与时刻。0 = 正常；非 0 表示上次那一跑失败了。
    这是补"任务跑过、脚本却一行日志都没写"这个洞：09-10 HandoffDaily 结果码 -1073741510
    （0xC000013A＝控制台被关掉、进程被杀，正是当时每轮闪出来的那个终端窗口），
    脚本连开头那行日志都没来得及写，光看脚本自己的状态根本发现不了。"""
    if platform.system() != "Windows":
        return None, None
    # 不用 `schtasks /V`：带上 CREATE_NO_WINDOW（不闪控制台）之后它就不再输出"Last Result"那几行了，
    # 实测同一台机器有控制台时 1691 字节、无控制台时 1505 字节且字段整段消失。走 PowerShell 的对象接口不受这个影响。
    ps = (f"$i = Get-ScheduledTaskInfo -TaskName '{name}' -ErrorAction SilentlyContinue; "
          "if ($i) { 'RESULT=' + $i.LastTaskResult; 'WHEN=' + $i.LastRunTime }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=30, creationflags=NO_WINDOW)
    except Exception:
        return None, None
    code, when = None, None
    for ln in (r.stdout or "").splitlines():
        ln = ln.strip()
        if ln.startswith("RESULT=") and ln[7:].lstrip("-").isdigit():
            code = int(ln[7:])
        elif ln.startswith("WHEN="):
            when = ln[5:].strip()
    return code, when


def task_exists():
    if platform.system() != "Windows":
        return False
    for name in TASK_NAMES:
        r = subprocess.run(["schtasks", "/Query", "/TN", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=NO_WINDOW)
        if r.returncode == 0:
            return True
    return False


def cells_of(ln):
    return [c.strip() for c in ln.strip().strip("|").split("|")]


def scan_problems(root, hours, cap=None):
    """跑写后检查扫最近 hours 小时改动的交接报告，不管是谁写的（ZCode／Codex／从 US3 同步下来的都算）。
    **扫描模式一律忽略 G6（断链）**：这些件多半是别的机器写的，`../../../../CLAUDE.md`、`/root/<项目>/...`
    这类目标在对面存在、本机不存在，是同步不对称而不是缺陷（早有定论："从 US3 拷下来的断链是正常的，别去修"）。
    写的那一刻仍然查 G6——那时作者能当场修。只剩 G6 的文件整件跳过。
    返回 [(路径, 改动时刻, 问题列表)]。生产默认完整收集窗口内问题，避免报告先占满上限后索引永远进不来；
    cap 只保留给显式诊断调用，并在两类都收集完成后截断。
    """
    import glob, importlib.util, time as _t
    spec = importlib.util.spec_from_file_location("hgate", os.path.join(HERE, "handoff_gate.py"))
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    cutoff = _t.time() - hours * 3600
    out = []
    for p in sorted(glob.glob(os.path.join(root, "**", "*_交接报告.md"), recursive=True)):
        try:
            mt = os.path.getmtime(p)
        except OSError:
            continue
        if mt < cutoff or not g.is_target(p):
            continue
        probs = [x for x in g.check(p, hook_mode=False) if not x.startswith("G6 ")]  # 只滤 G6 跨机断链；G6P 反斜杠不可移植照进清单
        if probs:
            out.append((os.path.abspath(p), int(mt), probs))
    # G8：索引 README 的链接（v2.5 三类：反斜杠、同目录裸文件名不存在、正斜杠目录前缀；_archive 由 is_index 排除；不套报告检查）
    for p in sorted(glob.glob(os.path.join(root, "**", "README.md"), recursive=True)):
        try:
            mt = os.path.getmtime(p)
        except OSError:
            continue
        if mt < cutoff or not g.is_index(p):
            continue
        probs = g.index_problems(p)
        if probs:
            out.append((os.path.abspath(p), int(mt), probs))
    return out[:cap] if cap is not None else out


FINDINGS_PAGE = os.path.join(TOOLS, "logs", "handoff_findings.html")
STATUS_PAGE = os.path.join(TOOLS, "logs", "handoff_status.html")
CSS = ('<style>body{font:15px/1.7 system-ui,"Microsoft YaHei",sans-serif;max-width:60em;margin:2em auto;padding:0 1.2em;color:#1a1a1a}'
       'h1{font-size:1.4em}h2{font-size:1.1em;margin-top:1.8em;border-bottom:1px solid #ddd;padding-bottom:.3em}'
       'code{background:#f4f4f4;padding:.1em .35em;border-radius:3px;font-size:.92em}'
       '.item{margin:.9em 0;padding:.7em .9em;background:#fafafa;border-left:3px solid #bbb}'
       '.need{border-left-color:#c33;background:#fff6f6}.why{color:#a33;margin:.35em 0 .5em}.p{color:#666;font-size:.88em;word-break:break-all}'
       'a{color:#06c}.none{color:#777}.tip{background:#f0f6ff;border-left:3px solid #6aa;padding:.7em .9em;margin:1em 0}'
       'table{border-collapse:collapse;width:100%;font-size:.93em}th,td{text-align:left;padding:.3em .5em;vertical-align:top}th{border-bottom:1px solid #ccc}'
       '.btn{display:inline-block;margin:.2em .4em .2em 0;padding:.25em .7em;border:1px solid #06c;border-radius:4px;text-decoration:none}'
       '.btn.ok{border-color:#282;color:#282;background:#f2fbf2}.btn.no{border-color:#c33;color:#c33;background:#fff6f6}</style>')


def write_status_page(now, table_path, handling, decide_rules=(), decide_scheme=None, pool_items=(), pool_evicted=0):
    """短页：只回答"要不要你、要你做什么、去哪做"。弹窗唯一按钮「看处理」开这页；细节从这页链过去。
    handling: [(事项, 系统做了什么, 需要负责人?, (链接文字, 链接URI) 或 None)]
    decide_rules: [(编号, 规矩全文, 到期, 为什么, 出处)]——顶部「等你拍板」区，人在这里读全文并按按钮拍板
    pool_items: 被拒候选池里待裁量的条目（v1.6）——「被拒的好点子」区，采纳/不用"""
    e = html.escape
    d = os.path.dirname(os.path.abspath(table_path))
    veto = os.path.join(d, "协作教训-否决记录.md")
    todo = os.path.join(d, "写后检查-待处理.md")
    need = [h for h in handling if h[2]]
    p = ['<!doctype html><meta charset="utf-8"><title>协作教训 · 处理状态</title>', CSS,
         f'<h1>处理状态</h1><p class="p">生成于 {now:%Y-%m-%d %H:%M}（北京）。看门狗每次运行重写。</p>']
    # 「等你拍板」放最上面：这才是人真正要做判断的地方——规矩全文、为什么会有这条、谁提的、什么时候生效，
    # 然后两个按钮。弹窗只负责把你带到这里（负责人 09-10：'跳转出去让我去看实际内容然后再给我的意见'）。
    if decide_rules:
        agreed = (load_json(STATE_PATH, {}) or {}).get("agreed") or {}
        left_n = sum(1 for r in decide_rules if r[0] not in agreed)
        p.append(f'<h2>等你拍板：{left_n} 条新规矩</h2>' if left_n else
                 f'<h2>新规矩：{len(decide_rules)} 条，你都已经确认过了</h2>')
        p.append('<div class="tip">这些规矩是几个 AI 从<b>自己写报告犯过的错</b>里总结出来的，写进一张共用的表，'
                 '以后它们写报告前都会先读一遍。<br>你什么都不做＝同意，到期后的第一次每日学习（每天早上 09:00）就会让它生效。'
                 '读下面的全文，觉得不合适就点「不采纳」。<br>'
                 '<span class="p">点完按钮会弹一条确认；这一页要等看门狗下次运行（每 4 小时）才刷新。</span></div>')
        for lid, rule, due, why, src in decide_rules:
            done = f'　<b style="color:#282">你已确认同意（{html.escape(agreed[lid])}）</b>' if lid in agreed else ''
            acts = (f'<a class="btn ok" href="{decide_scheme}:ok/{lid}">同意，就这么定</a>'
                    f'<a class="btn no" href="{decide_scheme}:no/{lid}">不采纳</a>' if decide_scheme else
                    f'<a class="btn" href="{file_uri(veto)}">要否决就在这个文件里加一行</a>')
            p.append(f'<div class="item need"><div style="font-size:1.05em"><b>{e(rule)}</b></div>'
                     + (f'<div class="why"><b>为什么会有这条：</b>{e(why)}</div>' if why else '')
                     + f'<div class="p">生效时间 {e(due)}{done}　·　谁提的：{e(src) or "—"}　·　编号 {e(lid)}</div>'
                     + f'<div>{acts}</div></div>')
    if pool_items or pool_evicted:  # 池里没有待裁量的、但有过期的，也要让人知道有东西被挤掉过
        p.append(f'<h2>被拒的好点子：{len(pool_items)} 条（你觉得好就采纳）</h2>')
        p.append('<div class="tip">每天早上的自动学习会从 AI 互相挑错的报告里总结新规矩。下面这些看着像样，'
                 '但程序当时没敢让它们自动生效（原因写在每条里，比如证据不够、字数超了、类别不合）。'
                 '你觉得有道理就点「采纳」——按人工规矩进表，48 小时后生效；不想要就点「不用」，或者不管它'
                 '（池子只保留最近 20 条，旧的自己挤掉）。</div>')
        if pool_evicted:
            p.append(f'<div class="tip">另有 {int(pool_evicted)} 条因为池子满了已经过期，没来得及给你看；'
                     f'记录还留在本机的候选池文件里，想翻可以让 AI 把它们列出来。</div>')
        for ent in pool_items:
            evs = ent.get("evidence") or []
            links = " ".join(f'<a class="btn" href="{file_uri(os.path.join(d, str(ev.get("rel", ""))))}">{e(str(ev.get("report_id", "?")))}</a>'
                             for ev in evs[:3] if ev.get("rel"))
            tok = pool_token(ent)
            acts = ((f'<a class="btn ok" href="{decide_scheme}:adopt/{ent.get("id", "")}/{tok}">采纳</a>' if tok else '')
                    +
                    f'<a class="btn no" href="{decide_scheme}:drop/{ent.get("id", "")}">不用</a>') if decide_scheme else ''
            p.append(f'<div class="item need"><div style="font-size:1.05em"><b>{e(str(ent.get("rule", "")))}</b></div>'
                     + (f'<div class="why"><b>为什么：</b>{e(str(ent.get("why", "")))}</div>' if ent.get("why") else '')
                     + f'<div class="p">程序没让它自动生效的原因：{e(str(ent.get("reason", "")))}　·　'
                       f'类别 {e(str(ent.get("category", "")))}　·　{e(str(ent.get("date", "")))}</div>'
                     + (f'<div class="p">证据：{links}</div>' if links else '')
                     + (f'<div>{acts}</div>' if acts else '') + '</div>')
    if need:
        p.append(f'<h2>需要你介入：{len(need)} 项</h2>')
        for ev, act, _, link in need:
            p.append(f'<div class="item need"><b>{e(ev)}</b><div class="why">{e(act)}</div>'
                     + (f'<a class="btn" href="{link[1]}">{e(link[0])}</a>' if link else '') + '</div>')
    else:
        p.append('<h2>需要你介入：0 项</h2><div class="tip">'
                 + ('上面那些新规矩你不管也行（不管＝同意），除此之外没有要你的事。' if decide_rules
                    else '系统都在自己处理，你可以关掉这页。') + '</div>')
    rest = [h for h in handling if not h[2]]
    if rest:
        p.append('<h2>系统自己在做的（不需要你）</h2><table><tr><th>事项</th><th>做了什么</th><th></th></tr>')
        for ev, act, _, link in rest:
            p.append(f'<tr><td>{e(ev)}</td><td>{e(act)}</td><td>'
                     + (f'<a href="{link[1]}">{e(link[0])}</a>' if link else '') + '</td></tr>')
        p.append('</table>')
    p.append('<h2>细节入口</h2><div class="tip">'
             f'<a class="btn" href="{file_uri(FINDINGS_PAGE)}">逐份报告的问题清单</a>'
             f'<a class="btn" href="{file_uri(todo)}">写后检查-待处理（各窗口自查用）</a>'
             f'<a class="btn" href="{file_uri(table_path)}">协作教训（完整表）</a>'
             f'<a class="btn" href="{file_uri(veto)}">否决记录</a>'
             f'<a class="btn" href="{file_uri(LOG_PATH)}">看门狗日志</a><br>'
             '暂停每日学习：PowerShell 里 <code>Disable-ScheduledTask -TaskName HandoffDaily</code>（恢复用 Enable-）。<br>'
             '<b>这页和弹窗有一个盲区</b>：报"通知发不出"的就是发通知的这个程序本身。看门狗的计划任务被禁、损坏或整机关机时，没有任何东西会告诉你。'
             '没有邮件／手机推送这类离机渠道，故障只能靠你自己隔几天打开这页看一眼"每日学习上次成功"那行。</div>')
    try:
        os.makedirs(os.path.dirname(STATUS_PAGE), exist_ok=True)
        tmp = STATUS_PAGE + ".tmp"
        io.open(tmp, "w", encoding="utf-8", newline="").write("\n".join(p) + "\n")
        os.replace(tmp, STATUS_PAGE)
        return STATUS_PAGE
    except OSError as ex:
        log(f"状态页写入失败：{type(ex).__name__}: {ex}")
        return None


def write_findings_page(now, table_path, pending, auto_lines, stale, scan_found, scan_hours):
    """细节页（逐份报告的全部问题、待否决教训的现成否决行）。从处理状态页链过来。放在纯 ASCII 路径下。"""
    e = html.escape
    veto = os.path.join(os.path.dirname(os.path.abspath(table_path)), "协作教训-否决记录.md")
    p = ['<!doctype html><meta charset="utf-8"><title>协作教训 · 细节清单</title>', CSS,
         f'<h1>细节清单</h1><p class="p">生成于 {now:%Y-%m-%d %H:%M}（北京）。看门狗每次运行重写。</p>']

    p.append(f'<p class="p">要不要你、要你做什么：看 <a href="{file_uri(STATUS_PAGE)}">处理状态</a>。这页只放细节。</p>')
    p.append('<h2>一、新教训，48 小时内你可以否决</h2>')
    if pending:
        for lid, rule, due, _why, _src in pending:
            p.append(f'<div class="item"><b>{e(lid)}</b>　到期 {e(due)}<div class="why">{e(rule)}</div>'
                     f'<div class="p">不同意 → 在 <a href="{file_uri(veto)}">否决记录</a> 加一行：'
                     f'<code>| {e(lid)} | {now:%Y-%m-%d} | {e(OWNER)} | 理由可空 |</code>　什么都不做 = 同意</div></div>')
    else:
        p.append('<p class="none">没有等你过目的新教训。</p>')

    p.append(f'<h2>二、近 {int(scan_hours)} 小时没过写后检查的报告（<b>不需要你处理</b>）</h2>')
    if scan_found:
        by_src = {}
        root_dir = os.path.dirname(os.path.abspath(table_path))
        for path, _mt, _pr in scan_found:
            s = os.path.relpath(os.path.dirname(path), root_dir).replace("\\", "/")
            by_src[s] = by_src.get(s, 0) + 1
        todo = os.path.join(os.path.dirname(os.path.abspath(table_path)), "写后检查-待处理.md")
        p.append('<div class="tip">这些是<b>写它们的 AI</b> 该处理的，已经写进 '
                 f'<a href="{file_uri(todo)}">写后检查-待处理.md</a>（按来源目录分组，各 AI 开工时自查）。'
                 '你只需要知道两件事：①"没过检查"＝表头格式不对，程序读不出它的编号／时间／状态，追溯会断，内容本身不一定有错；'
                 '②只有同一个窗口<b>反复</b>不过才会弹给你——那时值得去说它一句。按来源：'
                 + '，'.join(f'{e(s)} {n} 件' for s, n in sorted(by_src.items(), key=lambda kv: -kv[1])) + '</div>')
        for path, _mt, probs in scan_found:
            p.append(f'<div class="item"><b><a href="{file_uri(path)}">{e(os.path.basename(path))}</a></b>'
                     f'<div class="p">{e(os.path.dirname(path))}　·　'
                     f'<a href="{file_uri(os.path.dirname(path))}">打开所在文件夹</a></div>')
            for x in probs:
                p.append(f'<div class="why">· {e(x)}</div>')
            p.append('</div>')
    else:
        p.append('<p class="none">全部通过。</p>')

    p.append('<h2>三、脚本自己干了什么</h2>')
    p.append(''.join(f'<div class="item">{e(x)}</div>' for x in auto_lines) if auto_lines
             else '<p class="none">今天还没有自动处理记录。</p>')
    if stale:
        p.append(f'<div class="item"><b>每日学习异常</b><div class="why">{e(stale)}</div></div>')

    p.append(f'<h2>四、常用入口</h2><div class="tip">'
             f'<a href="{file_uri(table_path)}">协作教训（完整表，带出处）</a>　·　'
             f'<a href="{file_uri(os.path.join(os.path.dirname(os.path.abspath(table_path)), "协作教训-生效.md"))}">生效版（AI 实际读的那份）</a>　·　'
             f'<a href="{file_uri(veto)}">否决记录</a>　·　'
             f'<a href="{file_uri(LOG_PATH)}">看门狗日志</a><br>'
             f'暂停每日学习：PowerShell 里 <code>Disable-ScheduledTask -TaskName HandoffDaily</code>（恢复用 Enable-）。'
             f'自己查一遍全部报告：<code>py -X utf8 docs/规范/交接写时门/handoff_gate.py --scan docs/工作传递 --since 24</code>'
             f'</div>')
    try:
        os.makedirs(os.path.dirname(FINDINGS_PAGE), exist_ok=True)
        tmp = FINDINGS_PAGE + ".tmp"
        io.open(tmp, "w", encoding="utf-8", newline="").write("\n".join(p) + "\n")
        os.replace(tmp, FINDINGS_PAGE)
        return FINDINGS_PAGE
    except OSError as ex:
        log(f"清单页写入失败：{type(ex).__name__}: {ex}")
        return None


def ensure_published(table_path):
    """生效版版本行里的"表哈希"必须等于表现在的 sha256 前 8 位。不等就（同机）重跑一次 publish 自愈。
    返回 None（一致）或 (是否需要负责人, 说明)。"""
    d = os.path.dirname(os.path.abspath(table_path))
    pub = os.path.join(d, "协作教训-生效.md")
    try:
        cur = hashlib.sha256(io.open(table_path, encoding="utf-8").read().encode("utf-8")).hexdigest()[:8]
        m = re.search(r"表哈希 ([0-9a-f]{8})", io.open(pub, encoding="utf-8").read()) if os.path.isfile(pub) else None
    except OSError as e:
        return (True, f"生效版自检读文件失败：{e}")
    if m and m.group(1) == cur:
        return None
    why = "生效版不存在" if not m else f"生效版记的是表哈希 {m.group(1)}，表现在是 {cur}——表在 publish 之后被改过，凭证断绑"
    if not AUTO_PUBLISH:
        return (False, why + "（自动重生成已关闭）")
    lessons = os.path.join(HERE, "handoff_lessons.py")
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", lessons, "publish", table_path], capture_output=True, text=True,
                           creationflags=NO_WINDOW,
                           encoding="utf-8", timeout=60, env=dict(os.environ, HANDOFF_TOOLS_DIR=TOOLS))
    except Exception as e:
        return (True, why + f"；自动重生成失败（{type(e).__name__}），请看日志")
    if r.returncode == 0:
        return (False, why + "；已自动重跑 publish 重生成生效版，凭证已修复")
    return (True, why + f"；自动重跑 publish 失败（退出 {r.returncode}）：{(r.stdout or r.stderr)[-160:]}")


def stale_message(st, now_utc, task_present):
    """返回 (提醒文本或 None, 日志文本或 None)。只在定时任务存在时评估。"""
    if not task_present:
        st.pop("first_seen_utc", None)
        return None, None
    ls = load_json(LESSONS_STATE, {})
    last = ls.get("last_scan_utc")
    if last:
        try:
            hours = (now_utc - datetime.fromisoformat(last)).total_seconds() / 3600
        except ValueError:
            hours = None
        if hours is not None:
            st.pop("first_seen_utc", None)
            if hours > STALE_HOURS:
                return f"每日学习已 {int(hours)} 小时没有成功运行，请看 handoff_lessons 日志", None
            return None, None
    first = st.get("first_seen_utc")
    if not first:
        st["first_seen_utc"] = now_utc.isoformat()
        return None, "每日学习尚未首跑（无扫描记录），从现在起计宽限 36 小时"
    waited = (now_utc - datetime.fromisoformat(first)).total_seconds() / 3600
    if waited > STALE_HOURS:
        return f"每日学习自 {first[:16]}Z 被发现以来 {int(waited)} 小时从未成功运行，请看 handoff_lessons 日志", None
    return None, f"每日学习尚未首跑，宽限中（已等 {int(waited)} 小时／{STALE_HOURS}）"


def check(table_path, now_utc=None, task_present=None, scan_root=None, scan_hours=8.0, flow_root=None, flow_days=2):
    st = load_json(STATE_PATH, {"notified": {}, "attempts": {}})
    if not st.get("page_secret"):  # 处理页「采纳」口令的本机种子（v1.9）；刚读完就写回，不存在与 decide 抢写的窗口
        st["page_secret"] = secrets.token_hex(16)
        save_json(STATE_PATH, st)
    notified, attempts = st.setdefault("notified", {}), st.setdefault("attempts", {})
    now_utc = now_utc or datetime.now(timezone.utc)
    now = now_utc.astimezone(BJ)
    today = f"{now:%Y-%m-%d}"
    # 只留最近 14 天的已提醒记录，不让状态文件无限长（值以 YYYY-MM-DD 开头）
    cutoff = f"{now - timedelta(days=14):%Y-%m-%d}"
    for k in [k for k, v in notified.items() if isinstance(v, str) and v[:10] < cutoff and v[:4].isdigit()]:
        notified.pop(k, None)
        attempts.pop(k, None)
    text = io.open(table_path, encoding="utf-8").read()
    msgs, pending, auto_lines, scan_found = [], [], [], []
    dued = []  # 到期在即、这轮要提醒的：(编号, 规矩, 到期时刻, 剩余)
    consumed = []  # 被到期提醒代替掉的温和提醒：本轮弹成功后一并记为已发，免得下一轮又降级重发

    for ln in text.split("\n"):
        if not ROW_PAT.match(ln):
            continue
        c = cells_of(ln)
        if len(c) < 5:
            continue
        m = PEND_PAT.match(c[1])
        if m:
            pending.append((c[0], c[2], m.group(1), c[3] if len(c) > 3 else "", c[4] if len(c) > 4 else ""))
            key = f"pending:{c[0]}:{m.group(1)}"
            # 到期在即升为"需要你介入"并常驻（GLM 09-09：待否决归"不需要你"档会让 48h 否决窗变成"48h 不知情"）
            # 一条一行、只写编号与规矩本身；"到期时刻、还剩多久、该怎么办"由下面的开场白统一说一次，不每条重复
            left, dkey = None, f"pendue:{c[0]}:{m.group(1)}"
            try:
                left = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=BJ) - now
            except ValueError:
                pass
            # 含"已过期但还没翻牌"：到期只是时刻到了，真正转生效要等下一次每日学习（每天一次），
            # 中间这段最长十几小时里人仍然可以否决——这时更该给按钮，而不是什么都不说（09-10 实况）
            escalate = (left is not None and left <= timedelta(hours=PENDUE_HOURS)
                        and dkey not in notified
                        # v1.9：由池采纳的规矩，「同意」不静音到期催告——adopt＋ok 两步不能让被程序拦下的规矩悄悄生效
                        and (c[0] not in (st.get("agreed") or {}) or "从被拒候选采纳" in c[3]))
            if escalate:
                dued.append((c[0], c[2], m.group(1), left))
                msgs.append((dkey, f"{c[0]}：{cut(c[2], 36)}", True))
                consumed.append(key)  # 催过之后别再退回去发那句温和的"前可否决"（本轮弹成功即视为已发）
            # 同一条规矩不在一个弹窗里出现两次：正在催的就不再重复"XX 前可否决"那句（机器关过几天时两条会同时未发）；
            # 已经到期的也不再补发那句——它下一次每日学习就转生效了，再说"可否决"是误导
            if key not in notified and not escalate and (left is None or left > timedelta(0)):
                msgs.append((key, f"新规矩 {c[0]}（{m.group(1)} 前可否决）：{cut(c[2], 50)}", False))
    for ln in text.split("\n"):
        if ln.startswith(f"- {today}") and "handoff_lessons.py" in ln:
            one = ln.split("：", 1)[-1].strip()
            auto_lines.append(one)
            key = "auto:" + hashlib.sha256(ln.encode("utf-8")).hexdigest()[:10]
            if key not in notified:
                msgs.append((key, "脚本自动处理：" + one[:70], False))
    present = task_exists() if task_present is None else task_present
    stale, note = stale_message(st, now_utc, present)
    if note:
        log(note)
    if stale:
        key = f"stale:{today}"
        if key not in notified:
            msgs.append((key, stale, True))
    # 每日学习上一次运行出错（额度、CLI 挂、表被并发改…）：4 小时内就报，不等 36 小时超时
    # 计划任务跑过但结果码非 0：脚本可能压根没来得及写日志（被杀、解释器起不来）。
    # 这种情况下光靠"多久没成功"要等 36 小时才报，太晚。
    for tname in TASK_NAMES:
        rcode, rwhen = task_last_result(tname)
        if rcode not in (None, 0, 267011):  # 267011 = 还没跑过
            key = f"taskfail:{tname}:{rwhen}"
            if key not in notified:
                # 同一个码，schtasks 报有符号、PowerShell 报无符号，两种都认
                extra = "（0xC000013A：控制台窗口被关掉、进程被杀）" if rcode in (-1073741510, 3221225786) else ""
                msgs.append((key, f"计划任务 {tname} 上次自动运行没成功{extra}：结果码 {rcode}，时刻 {rwhen}。"
                                  f"它这一轮该做的事没做成。", True))
    lr = (load_json(LESSONS_STATE, {}) or {}).get("last_run") or {}
    if lr.get("rc") not in (None, 0):
        key = f"dailyerr:{str(lr.get('utc', ''))[:16]}"
        if key not in notified:
            msgs.append((key, f"每日学习上次运行出错（退出码 {lr.get('rc')}）：{str(lr.get('error') or '')[:90]}", True))
    if scan_root:
        try:
            scan_found = scan_problems(scan_root, scan_hours)
            for p, mt, probs in scan_found:
                log(f"  没过检查：{os.path.relpath(p, scan_root)}（{len(probs)} 处）首条：{probs[0][:90]}")
            # 路由：这些是"写报告的 AI"该处理的，不弹给负责人。写进 docs 树里的待处理清单（随 docs 同步），
            # 各 AI 开工时按自己来源目录自查（生效版页首有指向）。
            import importlib.util
            spec = importlib.util.spec_from_file_location("hgate2", os.path.join(HERE, "handoff_gate.py"))
            g = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(g)
            todo_path = os.path.join(os.path.abspath(scan_root), g.TODO_NAME)
            if not g.todo_md(scan_root, scan_found, todo_path, scan_hours, writer=TODO_WRITER):
                log(f"! 待处理清单写入失败：{todo_path}")
                msgs.append((f"todo_fail:{today}", f"待处理清单写不出来（{todo_path}），各窗口自查会失效——请看日志", True))
            fresh = [x for x in scan_found if f"scan:{os.path.basename(x[0])}:{x[1]}" not in notified]
            for p, mt, _ in fresh:
                # 值里带上窗口路径，升级判断按"今天累计"数，不只数本轮（2+1 分两轮也算 3）
                src = os.path.relpath(os.path.dirname(p), scan_root).replace("\\", "/")
                notified[f"scan:{os.path.basename(p)}:{mt}"] = f"{now:%Y-%m-%d %H:%M} 已列入待处理清单 @{src}"
            # 只有一种情况弹给负责人：同一窗口今天累计 ≥3 份不合格——说明它没在看提示，值得说一句
            by_src = {}
            for k, v in notified.items():
                if k.startswith("scan:") and isinstance(v, str) and v.startswith(today) and " @" in v:
                    src = v.rsplit(" @", 1)[1]
                    by_src[src] = by_src.get(src, 0) + 1
            for src, n in sorted(by_src.items(), key=lambda kv: -kv[1]):
                if n >= 3:
                    key = f"esc:{src}:{today}"
                    if key not in notified:
                        msgs.append((key, f"「{src}」这个窗口今天 {n} 份报告没过写后检查——它可能没在看提示，值得说一句（清单在 写后检查-待处理.md）", True))
            log(f"写后检查扫描：近 {int(scan_hours)} 小时，不合格 {len(scan_found)} 件，新出现 {len(fresh)} 件；待处理清单已写 {todo_path}")
        except Exception as e:
            log(f"写后检查扫描失败（不影响其他提醒）：{type(e).__name__}: {str(e)[:120]}")

    # 规范扫描（v1.7 --with-flow）：跑 handoff_flow.py（report-only），清单落 工作传递/规范扫描-待处理.md。
    # 路由同写后检查：清单是"写报告的 AI"看的；只有发现**在变多**时才给负责人一条当日提醒（负责人 09-20：要盯着指出）。
    flow_note = None
    flow_absorb = None  # 本轮若为新发现生成了提醒，弹成功后才把这些新指纹并进基线（否则下一轮／次日仍算新增）
    if flow_root:
        try:
            ftodo = os.path.join(os.path.abspath(flow_root), "工作传递", "规范扫描-待处理.md")
            r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "handoff_flow.py"), "scan", flow_root,
                                "--days", str(int(flow_days)), "--todo", ftodo, "--writer", FLOW_WRITER],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=180, creationflags=NO_WINDOW)
            out = (r.stdout or "") + (r.stderr or "")
            m = re.search(r"共 (\d+) 条", out)
            n = int(m.group(1)) if m else (0 if "无发现" in out else -1)
            breakdown = {k: out.count(f"- **{k}**") for k in ("W1", "W2", "W3")}
            # 触发口径（fable 09-21 抓"条数截断后增长永远不触发"）：按**逐条指纹**算新增，
            # 不看总数涨没涨——总数会被显示上限卡住，新增条目永远算得出。
            # v1.9：优先用扫描器末行 `#keys [...]` 的全量稳定键（不吃显示截断的亏、不因"冻结已 N 天"天天变）；
            # 老扫描器没有这一行时退回读**全量清单文件**逐行算（不再读截断后的 stdout）。
            mk = re.search(r"^#keys (\[.*\])\s*$", out, re.M)
            if not mk and re.search(r"^#keys\b", out, re.M):
                n = -1  # 有 #keys 行但残缺：按"没跑成"处理，别退回去读上一轮的旧清单
            if mk:
                try:
                    src_keys = [str(k) for k in json.loads(mk.group(1))]
                except ValueError:
                    src_keys, n = [], -1
            else:
                try:
                    full = io.open(ftodo, encoding="utf-8").read()
                except OSError:
                    full = out
                src_keys = [ln.strip() for ln in full.split("\n") if re.match(r"^- \*\*W\d\*\*", ln)]
            fps = sorted({hashlib.sha256(k.encode("utf-8", "replace")).hexdigest()[:12] for k in src_keys})
            if mk:  # 分类计数也按全量键数，不按截断后的显示数
                breakdown = {t: sum(1 for k in src_keys if k.startswith(t + ":")) for t in ("W1", "W2", "W3")}
            kind = "keys" if mk else "lines"
            prev = st.get("flow") or {}
            prev_fps = set(prev.get("fps") or [])
            # 口径换了（旧状态是按 stdout 行算的）就当首轮，只记基线不弹
            n_new = len(set(fps) - prev_fps) if (n >= 0 and prev and prev.get("kind") == kind) else 0
            if n >= 0:
                flow_note = (f"规范扫描：{n} 条" + (f"（{'、'.join(f'{k}×{v}' for k, v in breakdown.items() if v)}）"
                                                    if any(breakdown.values()) else ""),
                             "机器只提醒不拦人：清单在 工作传递/规范扫描-待处理.md，各来源开工先看自己被点名的条目",
                             False, ("看规范扫描清单", file_uri(ftodo)))
                if n_new > 0:  # 出现新发现才弹；首轮只记基线
                    key = f"flownew:{today}"
                    if key not in notified:
                        msgs.append((key, f"工作传递扫描发现 {n_new} 条新的不规范（现共 {n} 条）——比如报告碎片化、"
                                          f"回流路径写坏。清单在 工作传递/规范扫描-待处理.md，点名了具体来源。", True))
                full_state = {"fps": fps, "kind": kind, "n": n, "at": f"{now:%Y-%m-%d %H:%M}"}
                if n_new > 0:
                    # 独立验收（fable 09-21）抓的两条漏报：同一天第二批新发现（当日已弹过就不再弹，基线却照吞）、
                    # 弹窗没送达（基线已更新，下一轮 n_new=0）。所以这里先只留"上轮就有、这轮还在"的，新指纹等弹成功再并入。
                    st["flow"] = dict(full_state, fps=sorted(prev_fps & set(fps)))
                    flow_absorb = full_state
                else:
                    st["flow"] = full_state
            else:
                key = f"flowerr:{today}"
                if key not in notified:
                    msgs.append((key, "规范扫描这一轮没跑成（脚本出错或输出认不出）——写后检查不受影响，"
                                      "但违规清单这一轮没刷新，看看 日志 handoff_notify.log。", True))
            log(f"规范扫描：{n} 条（新增指纹 {n_new}）；清单 {ftodo if n >= 0 else '未写出'}")
        except Exception as e:
            log(f"规范扫描失败（不影响其他提醒）：{type(e).__name__}: {str(e)[:120]}")

    # 生效版凭证自检：版本行嵌的表哈希必须等于表现在的 sha256 前 8 位；不等＝表在 publish 后被改了（US3 Claude 1550 R2）
    pub_note = ensure_published(table_path)
    if pub_note:
        log(pub_note[1])
        if pub_note[0]:
            msgs.append((f"pubfail:{today}", pub_note[1], True))

    # 处理状态：每件事系统做了什么、要不要负责人、去哪做（包括已经提醒过、这轮不再弹的）
    d = os.path.dirname(os.path.abspath(table_path))
    veto_uri = file_uri(os.path.join(d, VETO_NAME))
    todo_uri = file_uri(os.path.join(d, "写后检查-待处理.md"))
    lessons_log = os.path.join(TOOLS, "logs", "handoff_lessons.log")
    handling = []
    ls = load_json(LESSONS_STATE, {})
    last = ls.get("last_scan_utc")
    handling.append(("每日学习", (f"上次成功 {datetime.fromisoformat(last).astimezone(BJ):%m-%d %H:%M}，积压 {len(ls.get('pending', []))} 件"
                                if last else "尚未首跑（宽限 36 小时内不算故障）"), False, None))
    # 待拍板的规矩只在顶部「等你拍板」区出现一次，不再重复列进下面两块（负责人 09-10：'内容是一样的'）
    for one in auto_lines:
        handling.append(("脚本自动处理", one[:90], False, None))
    if scan_found:
        handling.append((f"{len(scan_found)} 份报告没过写后检查", "已写进待处理清单，由写它们的窗口自查；已冻结的不回改", False, ("看待处理清单", todo_uri)))
    if flow_note:
        handling.append(flow_note)
    for key, t, nd in msgs:
        if nd:
            if key.startswith("esc:"):
                handling.append((t.split("——")[0], "去那个窗口说一句：开工先读 写后检查-待处理.md 里自己目录的条目", True, ("打开待处理清单", todo_uri)))
            elif key.startswith("stale:") or key.startswith("dailyerr:"):
                handling.append(("每日学习没跑成", t, True, ("看每日学习日志", file_uri(lessons_log))))
            elif key.startswith("taskfail:"):
                handling.append(("计划任务上次没跑成", t, True, ("看每日学习日志", file_uri(lessons_log))))
            elif key.startswith("pendue:"):
                continue  # 顶部「等你拍板」区已经把这条讲全了，这里再列一遍就是同一件事说三遍
            else:
                handling.append((t[:40], t, True, None))
    page = write_findings_page(now, table_path, pending, auto_lines, stale, scan_found, scan_hours)
    # 被拒候选池（v1.6）：只列待裁量的，最多 20 条（池本身不触发弹窗，只在页面上出现）
    _pool_all = (load_json(POOL_PATH, {}) or {}).get("items") or []
    pool_items = [x for x in _pool_all if str(x.get("status", "pending")) == "pending"][-20:]
    pool_evicted = sum(1 for x in _pool_all if str(x.get("status", "")) == "evicted")
    # 拍板按钮的协议：有待定规矩或有待裁量候选时注册（页面与弹窗共用同一个）
    scheme = ensure_protocol(table_path) if (pending or pool_items) else None
    status = write_status_page(now, table_path, handling, decide_rules=pending, decide_scheme=scheme,
                               pool_items=pool_items, pool_evicted=pool_evicted)
    if status:
        log(f"处理状态页：{status}（弹窗「看处理」打开这一页；按钮被系统拦住时手动打开它）")
    if not msgs:
        log("check：无需提醒（清单页已刷新）")
        merge_save_state(st)
        return 0
    need = [m for m in msgs if m[2]]
    info = [m for m in msgs if not m[2]]
    ordered = need + info  # 需要介入的排前面
    # 到期在即时：先用两行说清"什么时候生效、什么都不做会怎样、不同意怎么办"，再逐条列规矩。
    # 旧版把这些揉进每一条里，结果标题说 2 项、正文只露出第 1 项的半句话（负责人 09-10 截图）。
    # 弹窗是给人看的，不是给系统看的：不出现内部编号（LG-06）、"否决""拟生效""每日学习"这类黑话。
    # 负责人 09-10：'我压根不知道 LG-06 是什么，这个提醒只会让我不知所措'。
    # 所以：标题直接问"同意吗"，第一行说清这是什么、不管会怎样，然后把规矩正文逐条摆出来（①②③），
    # 按钮说人话（"不采纳 ①"）。编号只留在「看处理」那一页——那是详情，需要可追溯。
    lead = ""
    if dued:
        left = min(x[3] for x in dued)
        dstr = dued[0][2]
        when = ("今天 " + dstr[-5:]) if dstr[:10] == f"{now:%Y-%m-%d}" else ("在 " + dstr)
        one = len(dued) == 1
        deadline = (f"还有 {human_left(left)} 到期" if left > timedelta(0) else "已经到期")
        # 弹窗不是做决定的地方：一条规矩要不要，得看全文和它是因为什么事提出来的。
        # 所以这里只说"有这么回事、不管会怎样"，把判断留给「去看看」那一页（负责人 09-10）。
        lead = (f"{'它' if one else '它们'}是几个 AI 从自己写报告犯过的错里总结出来的，以后写报告都照着做。\n"
                f"{deadline}，明早 09:00 生效；你不管就是同意。点「去看看」读全文，再决定要不要。")
    lines = []
    if dued:
        rest = [t for k, t, _ in ordered if not k.startswith("pendue:")][:2]
        lines += rest
    else:
        lines = [t for _, t, _ in ordered[:3]]
        if len(ordered) > 3:
            lines.append(f"…另 {len(ordered) - 3} 条见「看处理」")
    body = (lead + "\n" if lead else "") + "\n".join(lines)
    buttons = []
    if status:
        buttons.append((("去看看" if dued else "看处理"), file_uri(status)))
    if dued:
        title = (f"有 {len(dued)} 条新规矩要加给 AI，你看一眼？" if not one
                 else "有 1 条新规矩要加给 AI，你看一眼？")
    elif need:
        title = f"协作教训 · 需要你介入（{len(need)} 项）"
    else:
        title = f"协作教训 · 自动处理中，不需要你（{len(info)} 条告知）"
    ok = toast(title, body, buttons, persistent=bool(need))
    if ok and flow_absorb is not None and any(k.startswith("flownew:") for k, _, _ in msgs):
        st["flow"] = flow_absorb
    if ok:
        for k in consumed:
            notified.setdefault(k, f"{now:%Y-%m-%d %H:%M} 由到期提醒代替")
    for key, t, _ in msgs:
        if ok:
            notified[key] = f"{now:%Y-%m-%d %H:%M}"
        else:
            attempts[key] = attempts.get(key, 0) + 1
            if attempts[key] >= 3:
                notified[key] = f"{now:%Y-%m-%d %H:%M} 放弃（三次未送达）"
                log(f"放弃提醒（三次未送达）：{t[:60]}")
    merge_save_state(st)
    return 0 if ok else 1


def main(a):
    if len(a) >= 3 and a[0] == "toast":
        return 0 if toast(a[1], a[2]) else 1
    if len(a) >= 2 and a[0] in ("rule", "veto"):
        opt = lambda k, d: a[a.index(k) + 1] if k in a and len(a) > a.index(k) + 1 else d
        tbl = opt("--table", None)
        if not tbl:
            print("rule 需要 --table <协作教训.md>")
            return 2
        arg = a[1] if a[0] == "rule" else "no/" + a[1].split(":")[-1]  # veto 是旧写法，等价于 no/<编号>
        return decide(arg, tbl, who=opt("--who", None))
    if len(a) >= 2 and a[0] == "check":
        opt = lambda k, d: a[a.index(k) + 1] if k in a and len(a) > a.index(k) + 1 else d
        return check(a[1], scan_root=opt("--with-scan", None), scan_hours=float(opt("--scan-hours", 8)),
                     flow_root=opt("--with-flow", None), flow_days=float(opt("--flow-days", 2)))
    print(__doc__)
    return 2


if __name__ == "__main__":
    # 计划任务用 pythonw.exe 才不闪控制台，而 pythonw 下 sys.stdout/stderr 是 None：print 会静默无事，
    # 但任何 sys.stdout.write 都会抛 AttributeError。先垫上空设备，后面的代码就不用逐处判空。
    for _n in ("stdout", "stderr"):
        if getattr(sys, _n) is None:
            setattr(sys, _n, io.open(os.devnull, "w", encoding="utf-8"))
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
