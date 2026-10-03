#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
handoff_notify.py —— 桌面通知、处理页与巡检（v1.13 · 2026-10-03；Windows 弹窗，Linux 只记日志并如实写"未送达"）

负责人的用法（09-29 定）：新教训默认直接生效；弹窗只简述改动；觉得不合理才点进处理页，点「不采纳」撤回。
10-03 第十批：弹窗先说事由、需要你做事的第二行写做法；内部编号与内部词由 toast() 出口强制挡掉；只是告知的静音、
同类互相替换、到期自动消失；点弹窗正文直接打开处理页对应的那一区；点完按钮处理页当场重写、页面几秒后自己刷新；
「不采纳」「不用」都能一键恢复；每日学习跑完立刻巡检一轮（新规矩当场简述，一次最多三条、每条恰好说一次）。

  check <协作教训.md> [--with-scan <docs/工作传递>] [--scan-hours 8] [--with-flow <docs 根>] [--flow-days 2] [--source task|daily]
        巡检（计划任务每 4 小时；每日学习跑完也顺带一轮）：判断该不该提醒、去重后弹窗、写日志、重写处理页。弹窗分几类：
          需要你介入（常驻、有声音）：自动学习连续 36 小时没成功、AI 读的那份规矩刷新不了、表里冒出不是本机加的敏感规矩、
                                    表里有认不出的行、待处理清单写不出、规范扫描没跑成
          新规矩简述（静音）：最近新生效的规矩，一次最多三条、每条只说一次
          只是告知（静音、24 小时后自动消失）：自动学习某一轮没跑成（下一轮会再跑）、表满了（每周一次）、
                                    有候选因越界或注入形态没自动生效、不采纳记录同步、积压太多、某窗口反复没过写后检查
          规范扫描的新发现不弹窗（给写报告的 AI 窗口看，只进清单与处理页）
        计划任务结果码按语义判：正在运行／排队／还没跑过不算失败；被系统终止、被禁用、条件不满足才报，时刻换算成北京时间。
  rule <handoff-rule:动作/编号/口令> --table <协作教训.md>
        处理页按钮的协议处理器。动作 ok（看过了）／no（不采纳）／unveto（恢复不采纳）／trust（确认生效）／
        adopt（采纳候选）／drop（候选不用）／undrop（恢复不用）**都要带处理页口令**（HMAC(本机种子, 动作|编号|正文哈希) 前 10 位）
        ——任何网页或本机程序都能唤起协议，没有口令或口令不对的一律只记日志、不改任何文件。改了状态的当场重写处理页。
  register [--table <协作教训.md>]   重新注册 handoff-rule: 协议（handoffctl install 调用；check 只在缺失或失效时补注册）
  toast "<标题>" "<正文>"            立刻弹一条（测试送达；普通、静音、10 分钟后自动消失）
状态与页面：见 handoff_common.py（已安装在 ~/.claude/handoff/state、pages；旧布局在 ~/.claude/tools/）。
边界：弹窗只在这台电脑的登录会话里可见；整机关机或巡检任务被禁用时，没有任何离机渠道会告诉你。
     弹出成功只证明交给了系统，不证明负责人看过。历史版本说明见 README「更新记录」。
"""
import io, json, os, re, sys, subprocess, hashlib, hmac, platform, urllib.parse, html, secrets, base64
from xml.sax.saxutils import escape as _xml_escape
from datetime import datetime, timezone, timedelta

sys.dont_write_bytecode = True  # 不在正本目录（docs 同步域）里留 __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import handoff_common as C  # noqa: E402

VERSION = "1.13"
BJ = C.BJ
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = C.P.home
AUTO_PUBLISH = True  # 生效版凭证（表哈希＋否决哈希）与现状不一致时当轮重发布；测试可关
PUBLISH_ON_DECIDE = True  # 「不采纳」「采纳」写完当场重发布
DECIDE_LOCK_WAIT = 20.0  # 点按钮时每日学习正占着锁：最多等这么久再告诉负责人"稍后再点"
OWNER = os.environ.get("HANDOFF_OWNER") or "负责人"
TODO_WRITER = "Windows 看门狗 HandoffNotify（每 4 小时；本机专属，US3 有自己的 写后检查-待处理-US3.md）"
FLOW_WRITER = "Windows 看门狗 HandoffNotify（每 4 小时；本机专属，US3 有自己的 规范扫描-待处理-US3.md）"
STATE_PATH = C.P.notify_state
POOL_PATH = C.P.pool
LESSONS_STATE = C.P.lessons_state
LOG_PATH = C.P.notify_log
TASK_NAMES = tuple(C.cfg("notify", "task_names", ["HandoffDaily"]))
NO_WINDOW = C.NO_WINDOW
APP_ID = os.environ.get("HANDOFF_APPID") or "HandoffGate.Lessons"
APP_NAME = os.environ.get("HANDOFF_APPNAME") or "协作教训"
RULE_SCHEME = os.environ.get("HANDOFF_RULE_SCHEME") or "handoff-rule"
VETO_NAME = C.VETO_NAME
STALE_HOURS = int(C.cfg("notify", "stale_hours", 36))
ROW_PAT = C.ROW_PAT
PEND_PAT = C.PEND_FULL  # 与 lessons 同一个正则（以前 notify 只匹配前缀，两边口径不一）
LIVE_ADDED = C.ADDED_ANY
RECENT_DAYS = int(C.cfg("notify", "recent_days", 7))
KEEP_DAYS = 14
STATUS_PAGE = C.P.status_page
FINDINGS_PAGE = C.P.findings_page


def now_bj():
    return C.now_bj()


def log(line):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    C.rotate_if_big(LOG_PATH)
    with io.open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{now_bj():%Y-%m-%d %H:%M} {C.one_line(line)}\n")
    print(line)


def load_json(p, default):
    return C.load_json(p, default)


def save_json(p, obj):
    C.save_json(p, obj)


def _lessons():
    import handoff_lessons as L  # 同目录；读写表都走它的锁与哈希门
    return L


# ---------- 处理页口令 ----------
def page_secret():
    return (load_json(STATE_PATH, {}) or {}).get("page_secret") or None


def _mac(secret, msg):
    return hmac.new(str(secret).encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()[:10]


def pool_token(ent, secret=None):
    """采纳口令＝HMAC(种子, 编号|规矩|为什么|类别|拒因|证据件) 前 10 位：凡是会写进表的字都绑进去，
    候选正文被人改过或池被重建，旧页面上的链接自动作废。"""
    secret = secret or page_secret()
    if not secret:
        return None
    ev = "；".join(f"{e.get('report_id')}@{e.get('rel')}" for e in (ent.get("evidence") or [])[:3] if isinstance(e, dict))
    body = "|".join(str(ent.get(k, "")) for k in ("id", "rule", "why", "category", "reason")) + "|" + ev
    return _mac(secret, "adopt|" + body)


def action_token(act, oid, text, secret=None):
    """同意／不采纳／不用 的口令：绑动作、编号与该条正文的哈希。正文变了口令就变；不含日期，昨晚开着的页面今天照样能点。"""
    secret = secret or page_secret()
    if not secret:
        return None
    return _mac(secret, f"{act}|{oid}|{C.sha(text or '')[:16]}")


# ---------- 状态 ----------
def _prune(st, cutoff):
    notified, attempts = st.setdefault("notified", {}), st.setdefault("attempts", {})
    for k in [k for k, v in notified.items() if isinstance(v, str) and v[:4].isdigit() and v[:10] < cutoff]:
        notified.pop(k, None)
        attempts.pop(k, None)


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def merge_save_state(st, cutoff=None):
    """落盘前先并上磁盘版（运行期间负责人点的「同意」、口令种子以磁盘为准；本轮新增的提醒键以内存为准），
    合并**之后**再剪 14 天前的键——v1.8～v1.11 先剪后并，剪掉的又从磁盘并回来，清理从没生效过。"""
    lk = C.Lock(STATE_PATH + ".lock", stale_sec=300)
    got = lk.acquire(10)
    try:
        disk = load_json(STATE_PATH, {}) or {}
        if disk.get("page_secret"):
            st["page_secret"] = disk["page_secret"]
        _d = lambda k: disk.get(k) if isinstance(disk.get(k), dict) else {}  # 磁盘上类型坏了当空（复核 R2-2-3）
        _s = lambda k: st.get(k) if isinstance(st.get(k), dict) else {}
        st["agreed"] = {**_s("agreed"), **_d("agreed")}  # 负责人的「看过了」以磁盘为准
        for k in ("notified", "attempts"):  # 本轮新增的提醒键以内存为准
            st[k] = {**_d(k), **_s(k)}
        for k in st.pop("_dropped", []):
            st["notified"].pop(k, None)
        # 不采纳编号：以磁盘为底（处理页／终端在本轮期间记进、移出的都直接写磁盘），只套用本轮确认告知过的增减；
        # 整份取并集会把负责人刚点「恢复」移出的编号又并回来（复核 A-02、C-03）。每次增减代数 +1，提醒键带代数（R2-1-1）。
        # 升级首轮对齐成现状（_veto_reset，R2-1-5）。错口令限流计数也以磁盘为准（check 不碰它，复核 R2-06）
        add, rem = set(st.pop("_veto_add", []) or []), set(st.pop("_veto_remove", []) or [])
        reset = st.pop("_veto_reset", None)
        base = reset if reset is not None else (disk.get("veto_seen") if isinstance(disk.get("veto_seen"), list)
                                                else st.get("veto_seen"))
        if isinstance(base, list) or add or rem:
            st["veto_seen"] = sorted((set(base or []) | add) - rem)
        st["veto_gen"] = _int(disk.get("veto_gen")) + (1 if (add or rem) else 0)
        if "badtok" in disk:
            st["badtok"] = disk["badtok"]
        for k, typ in (("last_decide", dict), ("acts", list)):
            if isinstance(disk.get(k), typ):
                st[k] = disk[k]
        if cutoff:
            _prune(st, cutoff)
        save_json(STATE_PATH, st)
    finally:
        if got:
            lk.release()


def file_uri(p):
    """本地文件的可点链接：中文百分号编码，盘符后的冒号与斜杠保持原样（file:///C%3A/... Windows 认不出）。"""
    return "file:///" + urllib.parse.quote(os.path.abspath(p).replace("\\", "/"), safe="/:")


def cut(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n] + "…"


# ---------- 注册（发信人与协议） ----------
def ensure_appid():
    """把自己注册成有名字的通知来源（HKCU AppUserModelId）；图标是自己画的纯色 PNG。失败吞掉，不影响弹窗。"""
    if platform.system() != "Windows" or os.environ.get("HANDOFF_NO_REGISTER") == "1":
        return None
    try:
        import winreg, struct, zlib
        icon = C.P.toast_icon
        if not os.path.exists(icon):
            size, rgb = 64, (37, 99, 146)
            raw = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
            def _chunk(t, d):
                return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
            png = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
                   + _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b""))
            os.makedirs(os.path.dirname(icon), exist_ok=True)
            with open(icon, "wb") as f:
                f.write(png)
        key_path = "Software\\Classes\\AppUserModelId\\" + APP_ID
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            cur = None
            try:
                cur = winreg.QueryValueEx(k, "IconUri")[0]
            except OSError:
                pass
            if cur != icon:
                winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
                winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, icon)
        return APP_ID
    except Exception as e:
        log(f"通知署名未能注册（不影响弹窗，仍会显示成 Windows PowerShell）：{type(e).__name__}")
        return None


def protocol_command(table_path):
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else sys.executable
    return f'"{exe}" -X utf8 -B "{os.path.join(HERE, "handoff_notify.py")}" rule "%1" --table "{os.path.abspath(table_path)}"'


def current_protocol_command():
    if platform.system() != "Windows":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software\\Classes\\" + RULE_SCHEME + "\\shell\\open\\command") as k:
            return winreg.QueryValueEx(k, None)[0]
    except OSError:
        return None


def ensure_protocol(table_path, force=False):
    """注册 handoff-rule: 协议。平时只在"没注册或注册的脚本已不存在"时补注册（v1.11 以前每轮都按调用者重写——
    有人手动对副本表跑一次 check，负责人的按钮就指到副本去了）；install 用 force=True 指到运行版。"""
    if os.environ.get("HANDOFF_NO_REGISTER") == "1":
        return RULE_SCHEME
    if platform.system() != "Windows":
        return None
    try:
        import winreg
        cur = current_protocol_command()
        if cur and not force:
            m = re.search(r'"([^"]+handoff_notify\.py)"', cur)
            if m and os.path.isfile(m.group(1)):
                return RULE_SCHEME
        cmd = protocol_command(table_path)
        base = "Software\\Classes\\" + RULE_SCHEME
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "URL:" + APP_NAME + " 拍板")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + "\\shell\\open\\command") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, cmd)
        if cur != cmd:
            log(f"拍板协议已注册：{cmd}" + (f"（原来是 {cur}）" if cur else ""))
        return RULE_SCHEME
    except Exception as e:
        log(f"拍板按钮未能注册（页面仍可看，只是少按钮）：{type(e).__name__}")
        return None


# ---------- 拍板（协议处理器） ----------
def _row_of(text, lid):
    return next((C.cells_of(ln) for ln in text.split("\n") if ln.startswith(f"| {lid} |")), None)


_BADTOK_N = [0]  # 本次拍板里错口令计数（decide 据此决定要不要当场重写处理页；网页刷协议时每小时第 4 次起不再重写）
_REFRESH = [False]  # 本次拍板之后要不要当场重写处理页（改了状态、或页面上的东西已经过时）


def _throttle():
    """拍板入口的"没生效"类回执限流：同一小时最多弹 3 次、最多重写 3 次处理页（复核 S-11；B-02 补上口令核验之前的
    三处——表忙、找不到条目），免得某个网页循环唤起协议刷屏；日志照记。返回 True＝这次还能弹。"""
    hour = f"{now_bj():%Y-%m-%d %H}"
    n = 0
    lk = C.Lock(STATE_PATH + ".lock", stale_sec=300)
    got = lk.acquire(5)
    try:
        st = load_json(STATE_PATH, {}) or {}
        bt = st.get("badtok") if isinstance(st.get("badtok"), dict) and st["badtok"].get("hour") == hour else {"hour": hour, "n": 0}
        bt["n"] = n = int(bt.get("n", 0)) + 1
        st["badtok"] = bt
        save_json(STATE_PATH, st)
    except Exception:
        pass
    finally:
        if got:
            lk.release()
    _BADTOK_N[0] = n
    return n <= 3


def _bad_token(what):
    log(f"拍板：{what}——没有口令或口令不对，什么都没改（不是从最新的处理页点的，或有别的程序在试这个入口）")
    if _throttle():
        _REFRESH[0] = True
        toast("这次点击没有生效", "按钮要从最新的处理页上点（链接里带一段本机口令）。处理页已经重新生成，回去再点一次；"
              "如果你没点过，说明有别的程序在试这个入口，让 AI 看一眼巡检日志。", kind="receipt_err")
    return 2


def _not_found(token, require_token, title, body):
    """找不到条目：合法页面上的按钮永远带口令，没口令的唤起不可能来自负责人——只记日志；有口令的（页面过时）限流告知。"""
    if require_token and not token:
        return 2
    if _throttle():
        _REFRESH[0] = True
        toast(title, body, kind="receipt_err")
    return 2


def _republish(L, table_path):
    if not PUBLISH_ON_DECIDE:
        return True
    try:
        return L.publish(table_path) == 0
    except Exception as e:
        log(f"拍板后重发布生效版失败：{type(e).__name__}: {e}")
        return False


def _remember_veto(oid):
    """处理页／终端写进否决记录的编号记一笔：看门狗据此分辨"否决记录里冒出来的、不是从这两处写的"（复核 S-01 的否决半边）。"""
    lk = C.Lock(STATE_PATH + ".lock", stale_sec=300)
    got = lk.acquire(10)
    try:
        st = load_json(STATE_PATH, {}) or {}
        seen = set(st.get("veto_seen") if isinstance(st.get("veto_seen"), list) else [])
        seen.add(oid)
        st["veto_seen"] = sorted(seen)
        st["veto_gen"] = _int(st.get("veto_gen")) + 1
        save_json(STATE_PATH, st)
    finally:
        if got:
            lk.release()


def _forget_veto(oid):
    """处理页／终端恢复了一条不采纳：编号移出 veto_seen——之后别处再把它写进否决记录，巡检要能认出来（复核 A-02、C-03）。"""
    lk = C.Lock(STATE_PATH + ".lock", stale_sec=300)
    got = lk.acquire(10)
    try:
        st = load_json(STATE_PATH, {}) or {}
        seen = st.get("veto_seen") if isinstance(st.get("veto_seen"), list) else []
        st["veto_seen"] = sorted(set(seen) - {oid})
        st["veto_gen"] = _int(st.get("veto_gen")) + 1
        save_json(STATE_PATH, st)
    except Exception as e:
        log(f"拍板：veto_seen 去掉 {oid} 失败（下一轮巡检按最近操作照样认得出）：{type(e).__name__}")
    finally:
        if got:
            lk.release()


def _acts(st):
    """状态里最近的拍板记录（类型不对的条目丢掉，复核 B-05）。"""
    out = []
    for a in (st.get("acts") if isinstance(st.get("acts"), list) else []):
        if isinstance(a, dict) and isinstance(a.get("oid"), str) and isinstance(a.get("act"), str):
            try:
                out.append(dict(a, ms=int(a.get("ms") or 0)))
            except (TypeError, ValueError):
                continue
    return out


def _remember_decide(oid, act, rule, result, undo=None, src="page"):
    """处理页顶部「刚才的操作」横幅用：记下最近一次拍板（巡检落盘时以磁盘为准，不会被冲掉）。
    undo＝(动作, 编号)：横幅上的「撤销」按钮做什么（口令在写页面时按当时的正文现算）。
    src＝page（处理页带口令的按钮）／terminal（终端，未核实是谁敲的）：巡检把终端替负责人做的事告知一次（复核 B-04）。"""
    lk = C.Lock(STATE_PATH + ".lock", stale_sec=300)
    got = lk.acquire(10)
    try:
        st = load_json(STATE_PATH, {}) or {}
        ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        st["last_decide"] = {"oid": oid, "act": act, "at": f"{now_bj():%Y-%m-%d %H:%M}",
                             "ms": ms, "rule": cut(rule, 40), "result": result, "undo": list(undo) if undo else None}
        # 最近 7 天的拍板（至多 50 条）：巡检据此不把负责人自己刚点的事再弹一遍
        acts = [a for a in _acts(st) if ms - a["ms"] <= 7 * 86400 * 1000]
        st["acts"] = (acts + [{"oid": oid, "act": act, "ms": ms, "src": src, "rule": cut(rule, 30)}])[-50:]
        save_json(STATE_PATH, st)
    except Exception as e:
        log(f"拍板：记「刚才的操作」失败（不影响拍板本身）：{type(e).__name__}")
    finally:
        if got:
            lk.release()


def _rule_state(table_path, oid):
    """一条规矩现在的样子：(状态格, 在不在生效版里, 是不是被本机账本扣下等确认)。"""
    try:
        row = _row_of(C.read_text(table_path), oid)
    except (OSError, UnicodeDecodeError):
        row = None
    try:
        pub = C.read_text(os.path.join(os.path.dirname(os.path.abspath(table_path)), C.PUBLISH_NAME))
    except (OSError, UnicodeDecodeError):
        pub = ""
    held = oid in ((load_json(LESSONS_STATE, {}) or {}).get("untrusted") or {})
    return (row[1] if row and len(row) > 1 else ""), bool(re.search(rf"^- {re.escape(oid)}：", pub, re.M)), held


def _unveto_receipt(table_path, oid, rule):
    """恢复之后照实说：重读表、本机账本与生效版再定文案（复核 A-05、C-10：以前只看返回码就说"已经放回"）。"""
    status, live, held = _rule_state(table_path, oid)
    q = f"「{cut(rule, 46)}」\n"
    if live:
        return "恢复了，重新生效", q + "已经放回 AI 读的规矩里。", "receipt"
    if held:
        return "恢复了，还差你确认一下", q + "它是别处加进来、碰到敏感话题的规矩，要你在处理页点「确认生效」才给 AI 读。", "receipt_err"
    m = PEND_PAT.match(status)
    if m:
        return "恢复了，按原定时刻生效", q + f"它是手写的老格式规矩，{m.group(1)} {m.group(2)} 自动生效。", "receipt"
    if status.startswith("否决"):
        if "原：" not in status:  # 老格式的状态格没留原状态，promote 恢复不了（复核 R2-1-8）
            return "已从不采纳记录里删掉，还要手改一下", q + "它的状态格是老格式、没记原来的状态，自动恢复不了；让 AI 把状态格改成「生效（日期 说明）」。", "receipt_err"
        return "已从不采纳记录里删掉", q + "教训表这会儿没改成状态，明早的自动学习会把它恢复成生效。", "receipt_err"
    return "恢复了，但 AI 读的那份还没刷新", q + "下一轮巡检会补刷。", "receipt_err"


def decide(arg, table_path, who=None, require_token=True, reason=None, allow_held=True):
    """负责人对一条规矩/候选拍板。arg 形如 ok/LG-06/口令、no/LG-06/口令、trust/LG-06/口令、unveto/LG-06/口令、
    adopt/RP-003/口令、drop/RP-003/口令、undrop/RP-003/口令，或带 handoff-rule: 前缀的协议串。
    require_token=False 只给本机终端（handoffctl）用——终端没有口令可核，所以署名写"未核实是谁敲的"；而且凡是放行
    "等你看一眼"的条目、或推翻负责人已经做过的决定（采纳 hold 候选、确认表外规矩、恢复不采纳、恢复不用）都要显式
    allow_held（handoffctl … --confirm-held），免得别的 AI 会话顺手一条命令就替负责人做了主（复核 N-04、R2-03）。
      ok     = 看过了：记进巡检状态，这条以后不再简述（处理页仍列着、标"你看过了"，随时还能撤）
      no     = 不采纳：往否决记录追加一行（只追加、不重复写），当场重发布生效版
      unveto = 恢复不采纳：删掉否决记录里这一行，状态格恢复、当场重发布
      trust  = 确认一条"不是本机流程加的"规矩可以生效（登记进本机账本，当场重发布）
      adopt  = 采纳被拒候选：写成人工行**立即生效**（出处注明程序当时的拒因），当场重发布
      drop   = 候选不用：池里标 ignored
      undrop = 恢复不用：池里改回待处理（下一次每日学习按规则补入；有硬拒因的仍等负责人点采纳）
    改了状态的（以及口令错、找不到条目这类"页面已经过时"的情况）当场重写处理页。"""
    _BADTOK_N[0], _REFRESH[0] = 0, False
    rc = _decide(arg, table_path, who, require_token, reason, allow_held)
    if rc == 0 or _REFRESH[0]:
        try:
            check(table_path, pages_only=True)
        except Exception as e:
            log(f"拍板后重写处理页失败（不影响刚才的操作）：{type(e).__name__}: {e}")
    return rc


def _decide(arg, table_path, who=None, require_token=True, reason=None, allow_held=True):
    raw = urllib.parse.unquote((arg or "").strip().strip('"'))
    if raw.lower().startswith(RULE_SCHEME + ":"):
        raw = raw[len(RULE_SCHEME) + 1:]
    raw = raw.strip().strip("/")
    act, _, rest = raw.partition("/")
    oid, _, token = rest.partition("/")
    act, oid, token = act.strip().lower(), oid.strip(), token.strip().lower()
    lg_acts, rp_acts = ("ok", "no", "trust", "unveto"), ("adopt", "drop", "undrop")
    if act not in lg_acts + rp_acts or not re.fullmatch(r"(LG|RP)-\d{2,4}", oid) \
            or (token and not re.fullmatch(r"[0-9a-f]{10}", token)) \
            or (act in lg_acts and not oid.startswith("LG-")) or (act in rp_acts and not oid.startswith("RP-")):
        log(f"拍板：参数不合法，忽略（{re.sub(r'[0-9a-fA-F]{8,}', '…', raw[:60])!r}）")
        return 2
    who = C.cell(who or ("负责人（处理页按钮）" if require_token else "本机终端（handoffctl，未核实是谁敲的）"), 60)
    src = "page" if require_token else "terminal"
    now = datetime.now(BJ)
    L = _lessons()
    if not L.acquire_lock(wait_s=DECIDE_LOCK_WAIT):  # 所有拍板都走每日学习同一把锁：防丢更新、防撞号
        log("拍板：每日学习正在写表，稍后再试")
        if not (require_token and not token) and _throttle():
            toast("现在有点忙，稍后再点", "每天早上的自动学习正在写教训表，几分钟后再点一次就行。", kind="receipt_err")
        return 2
    try:
        if act in rp_acts:
            pool = load_json(POOL_PATH, {}) or {}
            want = "ignored" if act == "undrop" else "pending"
            ent = next((x for x in pool.get("items", [])
                        if str(x.get("id", "")) == oid and str(x.get("status", "pending")) == want
                        and not (act == "undrop" and x.get("note"))), None)  # 只恢复负责人亲手点的「不用」
            if not ent:
                log(f"拍板：池里没有可{({'adopt': '采纳', 'drop': '不用', 'undrop': '恢复'})[act]}的 {oid}，忽略")
                return _not_found(token, require_token, "没找到这条候选",
                                  "候选里没有这条可处理的条目，什么都没有改。处理页已经重新生成，回去看最新的。")
            rule_rp = str(ent.get("rule", ""))
            if act in ("drop", "undrop"):
                if require_token and (not token or not hmac.compare_digest(token, action_token(act, oid, rule_rp) or "")):
                    return _bad_token(f"{oid} {'不用' if act == 'drop' else '恢复为候选'}")
                if act == "undrop" and not require_token and not allow_held:
                    log(f"拍板：恢复负责人点过「不用」的 {oid} 是推翻负责人已做的决定，终端要显式 --confirm-held，没有改动（{who}）")
                    return 2
                if act == "drop":
                    ent["status"], ent["decided"] = "ignored", f"{now:%Y-%m-%d %H:%M}"
                    ent.pop("restored", None)
                    msg, undo = "这条候选不用了", ("undrop", oid)
                    body = f"「{cut(rule_rp, 46)}」\n以后不再列在候选里。点错了：处理页顶部点「撤销」。"
                else:
                    ent["status"] = "pending"
                    ent.pop("decided", None)
                    ent["restored"] = {"at": f"{now:%Y-%m-%d %H:%M}", "by": who}
                    msg, undo = "已恢复为候选", ("drop", oid)
                    body = (f"「{cut(rule_rp, 46)}」\n明早的自动学习会把它补进表"
                            "（提到权限、路径这类内容的，会等你在处理页点「采纳」）。")
                save_json(POOL_PATH, pool)
                log(f"拍板：{oid} {'不用，已翻篇' if act == 'drop' else '恢复为待处理候选'}（{who}）")
                _remember_decide(oid, act, rule_rp, msg, undo, src)
                toast("好，" + msg if act == "drop" else msg, body, kind="receipt")
                return 0
            want_tok = pool_token(ent)
            if require_token and (not want_tok or not token or not hmac.compare_digest(token, want_tok)):
                return _bad_token(f"{oid} 采纳")
            held = _hard_reasons(ent)
            if held and not require_token and not allow_held:
                log(f"拍板：{oid} 是等负责人看一眼的候选（{held}），终端采纳要显式 --confirm-held，没有改动（{who}）")
                return 2
            try:
                text = C.read_text(table_path)
            except OSError as e:
                log(f"拍板：读不到教训表 {table_path}：{e}")
                return 2
            nid = C.max_lg(text) + 1
            rule_txt = C.cell(ent.get("rule", ""))
            refs = "；".join(f"[{C.cell(e.get('report_id'))}]({C.cell(e.get('rel'))})" for e in (ent.get("evidence") or [])[:3]
                             if isinstance(e, dict)) or "（本条由负责人从被拒候选采纳，无核验过的引文）"
            why_full = C.cell(f"{ent.get('why', '')}（类别：{ent.get('category', '其他')}；负责人从被拒候选采纳，"
                              f"程序当时没让它自动生效的原因：{ent.get('reason', '')}）")
            new_row = (f"| LG-{nid:02d} | 生效（{now:%Y-%m-%d} 采纳） | {rule_txt} | {why_full} | "
                       f"{refs}；{C.added_marker(now, '人工')} |")
            new_text = C.insert_rows(text, [new_row])
            if new_text is None:
                log(f"拍板：表里找不到表格，没法加行（{table_path}）")
                toast("教训表里没找到表格", "这条候选没能写成规矩：表里找不到可以加行的位置，请让 AI 看一下。", kind="receipt_err")
                return 2
            via = "处理页「采纳」" if require_token else "终端 handoffctl adopt"
            new_text = C.add_update_line(new_text, f"- {now:%Y-%m-%d %H:%M}：{oid} 经{via}写成人工行 LG-{nid:02d}，"
                                                   f"立即生效（{who}）。（handoff_notify.py rule adopt/…）")
            if not L.write_table(table_path, C.sha(text), new_text, "adopt"):
                _REFRESH[0] = True
                toast("没写成，请再点一次", "教训表在你点的瞬间被别的东西改了（防覆盖保护拦下了），回处理页再点一次就好。",
                      kind="receipt_err")
                return 2
            ent["status"], ent["decided"], ent["row"] = "adopted", f"{now:%Y-%m-%d %H:%M}", f"LG-{nid:02d}"
            ent.pop("hold", None)
            save_json(POOL_PATH, pool)
            try:
                L.ledger_add(f"LG-{nid:02d}", rule_txt, text)  # 负责人采纳的行登记进本机账本
            except Exception as e:
                log(f"拍板：账本登记失败（下次发布会按硬门重查）：{e}")
            pub = _republish(L, table_path)
            log(f"拍板：{oid} 已采纳为 {ent['row']}（人工行，立即生效；{who}）" + ("" if pub else "；生效版还没刷新"))
            _remember_decide(ent["row"], "adopt", rule_txt, "已采纳，立即生效", ("no", ent["row"]), src)
            toast("已采纳，立即生效" if pub else "已采纳，但 AI 读的那份还没刷新",
                  f"「{cut(str(ent.get('rule', '')), 46)}」\n" + ("现在 AI 写报告就照它做了；" if pub else
                  "表里已经写上了，下一轮巡检会补刷；") + "反悔就在处理页点「不采纳」。", kind="receipt")
            return 0
        try:
            text = C.read_text(table_path)
        except OSError as e:
            log(f"拍板：读不到教训表 {table_path}：{e}")
            return 2
        row = _row_of(text, oid)
        if not row or len(row) < 3:
            log(f"拍板：表里没有 {oid}，忽略")
            return _not_found(token, require_token, "没找到这条规矩", "表里没有这个编号，什么都没有改。处理页已经重新生成，回去看最新的。")
        rule = row[2]
        if require_token and (not token or not hmac.compare_digest(token, action_token(act, oid, rule) or "")):
            return _bad_token(f"{oid} {({'ok': '看过了', 'no': '不采纳', 'trust': '确认生效', 'unveto': '恢复'})[act]}")
        if act == "trust":
            if not require_token and not allow_held:
                log(f"拍板：{oid} 是被扣下的表外规矩，终端确认要显式 --confirm-held，没有改动（{who}）")
                return 2
            rc = L.trust(table_path, oid)
            log(f"拍板：{oid} 确认可以生效，登记进本机账本（{who}）" + ("" if rc == 0 else f"；重发布返回 {rc}"))
            _remember_decide(oid, "trust", rule, "确认生效", ("no", oid), src)
            if rc == 0:
                toast("好，这条生效了", f"「{cut(rule, 46)}」\n已经放进 AI 读的规矩里。改主意就在处理页点「不采纳」。",
                      kind="receipt")
            else:
                toast("已确认，但 AI 读的那份还没刷新", f"「{cut(rule, 46)}」\n已经记下你确认过了；这次没刷新成功，"
                      "下一轮巡检会补刷。", kind="receipt_err")
            return 0 if rc == 0 else 2
        if act == "ok":
            if not require_token and not allow_held:
                # 「看过了」会让巡检不再把这条简述给负责人——简述是负责人唯一的知情渠道，终端替负责人点要显式确认（复核 B-03）
                log(f"拍板：终端把 {oid} 标成看过了会让负责人收不到简述，要显式 --confirm-held，没有改动（{who}）")
                return 2
            lk = C.Lock(STATE_PATH + ".lock", stale_sec=300)
            got = lk.acquire(10)
            try:
                st = load_json(STATE_PATH, {}) or {}
                if not isinstance(st.get("agreed"), dict):
                    st["agreed"] = {}
                st["agreed"][oid] = f"{now:%Y-%m-%d %H:%M}" + ("" if require_token else " 终端")
                save_json(STATE_PATH, st)
            finally:
                if got:
                    lk.release()
            log(f"拍板：{oid} 看过了，之后不再简述（{who}）")
            _remember_decide(oid, "ok", rule, "看过了", None, src)
            toast("好，看过了", f"「{cut(rule, 46)}」\n这条以后不再简述给你。改主意随时在处理页点「不采纳」。", kind="receipt")
            return 0
        veto_path = C.veto_path(table_path)
        try:
            vt = C.read_text(veto_path) if os.path.exists(veto_path) else ""
        except OSError as e:
            log(f"拍板：读不到否决记录 {veto_path}：{e}")
            return 2
        if act == "unveto":
            if not require_token and not allow_held:
                log(f"拍板：恢复负责人不采纳过的 {oid} 是推翻负责人已做的决定，终端要显式 --confirm-held，没有改动（{who}）")
                return 2
            if oid not in C.parse_veto(vt)[0]:
                log(f"拍板：{oid} 不在否决记录里，没有改动")
                _REFRESH[0] = True
                toast("这条本来就在用", f"「{cut(rule, 46)}」\n不采纳记录里没有它，什么都没改。", kind="receipt")
                return 0
            rc = L.unveto(table_path, oid, who)
            log(f"拍板：{oid} 恢复（删掉否决记录里那一行；{who}）" + ("" if rc == 0 else f"；状态格或生效版没刷新成（返回 {rc}）"))
            if rc in (0, 1):
                _forget_veto(oid)
            title, body, kind = _unveto_receipt(table_path, oid, rule)
            _remember_decide(oid, "unveto", rule, title, ("no", oid), src)
            toast(title, body, kind=kind, anchor="untrusted" if "确认生效" in body else None)
            return 0 if rc in (0, 1) else 2
        if oid in C.parse_veto(vt)[0]:
            log(f"拍板：{oid} 已经在否决记录里，没有重复写")
            _REFRESH[0] = True
            toast("这条早就不采纳了", f"「{cut(rule, 46)}」\n之前已经标成不采纳，这次没重复写。", kind="receipt")
            return 0
        lines = vt.split("\n")
        i = next((j for j, ln in enumerate(lines) if ln.replace(" ", "").startswith("|---")), None)
        if i is None:
            log(f"拍板：否决记录里找不到表格，没有改动（{veto_path}）")
            toast("不采纳没写成", "不采纳记录里找不到表格，请让 AI 看一下。", kind="receipt_err")
            return 2
        i += 1
        while i < len(lines) and lines[i].startswith("|"):
            i += 1
        why_col = C.cell(reason or ("页面上点的不采纳" if require_token else "终端否决"), 120)
        lines.insert(i, f"| {oid} | {now:%Y-%m-%d} | {who} | {why_col} |")
        upd = next((j for j, ln in enumerate(lines) if ln.strip() == "## 更新记录"), None)
        where = "在处理页上点「不采纳」划掉" if require_token else "在终端用 handoffctl veto 划掉"
        note = f"- {now:%Y-%m-%d %H:%M}：{oid} {where}（{who}）。（handoff_notify.py rule no/…）"
        if upd is not None:
            j = upd + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            lines.insert(j, note)
        else:
            lines += ["", "## 更新记录", "", note]
        try:
            C.atomic_write(veto_path, "\n".join(lines), newline="\n")
        except OSError as e:
            log(f"拍板：写不进否决记录 {veto_path}：{e}")
            toast("不采纳没写成", "没能写进不采纳记录（文件可能正被占用或是只读的），过一会儿再点；还不行就让 AI 看一眼巡检日志。",
                  kind="receipt_err")
            return 2
        _remember_veto(oid)
        pub = _republish(L, table_path)
        log(f"拍板：{oid} 不采纳，已写进 {veto_path}（{who}）" + ("；生效版已当场刷新" if pub else "；生效版刷新失败，下一轮补"))
        _remember_decide(oid, "no", rule, "不采纳了", ("unveto", oid), src)
        toast("这条不采纳了", f"「{cut(rule, 46)}」\n" + ("已经从 AI 读的规矩里撤下了。" if pub else
              "已记下；AI 读的那份下一轮巡检会补刷。") + "\n点错了：处理页顶部点「撤销」。", kind="receipt")
        return 0
    finally:
        L.release_lock()


# ---------- 弹窗 ----------
SCRUB_HITS = []  # 出口兜底替换过的弹窗（测试要求生产路径上为空：每个调用点的源文案都该自己写干净）


_XML_BAD = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")  # XML 1.0 不允许的字符


def _x(s):
    """转义成 XML 文本／属性值；先去掉 XML 1.0 不允许的控制字符与孤立代理——留着它们 LoadXml 会失败，弹窗静默发不出。"""
    return _xml_escape(_XML_BAD.sub("", str(s if s is not None else "")), {'"': "&quot;"})


def _clip(s, n):
    s = " ".join(str(s if s is not None else "").split())
    return s if len(s) <= n else s[: max(1, n - 1)] + "…"


def build_toast_xml(title, body, buttons=None, persistent=False, launch=None, silent=False, attribution=None,
                    maxlines=4, snooze=False):
    """弹窗 XML（ToastGeneric）。文字一律转义（引号、尖括号、& 都转）；标题 ≤60 字；正文 ≤4 行、每行 ≤60 字
    （官方：标题之外的文字合计最多 4 行，旧版写 6 行超标）；常驻用 reminder 场景；有 launch 时点正文就打开它；
    按钮 ≤3 个（开稍后提醒时 ≤2 个），另有一个系统的「知道了」；总长超过 4800 字节先去署名行、再截正文，
    最后从后往前去按钮（正常的链接很短，走不到这一步；保证上限是硬的）。"""
    title = _clip(title, 60)
    lines = [_clip(x, 60) for x in str(body if body is not None else "").split("\n") if x.strip()][:maxlines]
    btns = [(lab, uri) for lab, uri in (buttons or []) if lab and uri][: (2 if snooze else 3)]

    def render(att, ls, bs):
        head = "<toast" + (' scenario="reminder"' if persistent else "")
        if launch:
            head += f' launch="{_x(launch)}" activationType="protocol"'
        texts = f"<text>{_x(title)}</text>"
        if ls:
            texts += f'<text hint-maxLines="{maxlines}">{_x(chr(10).join(ls))}</text>'
        if att:
            texts += f'<text placement="attribution">{_x(att)}</text>'
        acts = ""
        if snooze:
            acts += ('<input id="snoozeTime" type="selection" defaultInput="120">'
                     '<selection id="30" content="30 分钟后"/><selection id="120" content="2 小时后"/>'
                     '<selection id="1440" content="明天这个时候"/></input>')
        acts += "".join(f'<action content="{_x(_clip(lab, 20))}" arguments="{_x(uri)}" activationType="protocol"/>'
                        for lab, uri in bs)
        if snooze:
            acts += '<action activationType="system" arguments="snooze" hint-inputId="snoozeTime" content="稍后提醒"/>'
        acts += '<action content="知道了" arguments="dismiss" activationType="system"/>'
        return (head + '><visual><binding template="ToastGeneric">' + texts + "</binding></visual>"
                + ('<audio silent="true"/>' if silent else "") + "<actions>" + acts + "</actions></toast>")

    att, ls, bs = attribution, list(lines), list(btns)
    xml = render(att, ls, bs)
    while len(xml.encode("utf-8")) > 4800:
        if att:
            att = None
        elif len(ls) > 1:
            ls = ls[:-1]
        elif ls and len(ls[0]) > 20:
            ls = [_clip(ls[0], 20)]
        elif bs:
            bs = bs[:-1]
        else:
            break
        xml = render(att, ls, bs)
    return xml


def toast(title, body, buttons=None, persistent=None, kind=None, anchor=None, tag=None):
    """发弹窗的唯一出口（文案层）。标题正文先过 C.toast_scrub——内部编号与内部词由程序挡掉（09-10 负责人：弹窗里不出现
    这些）；命中说明调用点源文案没写干净，照样替换、记日志，测试要求一次都不命中。再按 kind（common.TOAST_KINDS）定常驻／
    静音／同类替换／过期／点正文去处理页哪一区；没给按钮就补一个去处理页的。返回 True＝已交给系统（不证明被看到）。"""
    if kind is None:
        kind = "info" if persistent is False else "need"
    spec = C.TOAST_KINDS.get(kind) or C.TOAST_KINDS["info"]
    if persistent is None:
        persistent = spec["persistent"]
    title, h1 = C.toast_scrub(title)
    body, h2 = C.toast_scrub(body)
    if h1 or h2:
        SCRUB_HITS.append((title, h1 + h2))
        log(f"弹窗文案含内部词，已在出口替换（该调用点的源文案要改）：{h1 + h2}")
    if title.startswith(APP_NAME + " · "):  # 系统已经显示应用名，不再重复
        title = title[len(APP_NAME) + 3:]
    a = spec.get("anchor") if anchor is None else anchor
    launch = file_uri(STATUS_PAGE) + (f"#{a}" if a else "")
    btns = [(lab, uri) for lab, uri in (buttons or []) if lab and uri]
    if not btns:
        btns = [("去处理" if persistent else "看处理页", launch)]
    meta = {"kind": kind, "tag": str(tag or spec["tag"])[:63], "group": C.TOAST_GROUP,
            "expire_min": int(spec.get("expire_min") or 0), "silent": bool(spec.get("silent")), "suppress": False,
            "launch": launch}
    meta["xml"] = build_toast_xml(title, body, btns, persistent, launch=launch, silent=meta["silent"],
                                  attribution=f"北京 {now_bj():%m-%d %H:%M} · 点这条打开处理页",
                                  snooze=bool(persistent and C.cfg("notify", "snooze", False)))
    return _send(title, body, btns, persistent, meta)


_PS_ENV = {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "PATH", "PATHEXT", "TEMP", "TMP", "USERPROFILE", "USERNAME", "USERDOMAIN",
           "COMPUTERNAME", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
           "PROGRAMW6432", "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)", "COMMONPROGRAMW6432", "PSMODULEPATH", "COMSPEC",
           "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER", "OS", "ALLUSERSPROFILE", "PUBLIC"}


def _send(title, body, buttons, persistent, meta):
    """弹窗传输层：整段 XML 经环境变量交给 ps1（不拼命令行）。子进程环境先清掉父进程里的 HN_*、再填本次的——
    免得测试用的 HN_DRYRUN_OUT 之类混进真弹窗，把"没弹"记成"已弹"。子进程环境是白名单（Windows 与 PowerShell 要的那几个），
    其余一律不带——按名字排除挡不全（GITHUB_PAT、带口令的代理串……，复核 B-08）。"""
    if platform.system() != "Windows":
        log(f"未送达（非 Windows，无桌面通知链路）：{title} / {body[:80]}")
        return False
    env = {k: v for k, v in os.environ.items() if k.upper() in _PS_ENV}
    env["HN_XML"] = meta["xml"]
    appid = ensure_appid()
    if appid:
        env["HN_APPID"] = appid
    if meta.get("tag"):
        env["HN_TAG"] = str(meta["tag"])[:63]
    if meta.get("group"):
        env["HN_GROUP"] = str(meta["group"])[:63]
    if meta.get("expire_min"):
        env["HN_EXPIRE_MIN"] = str(int(meta["expire_min"]))
    if meta.get("suppress"):
        env["HN_SUPPRESS"] = "1"
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
    log(f"已弹窗（{'常驻，需点掉' if persistent else '普通，自动消失、通知中心留底'}·{meta.get('kind')}；不证明已被看到）："
        f"{title} / {body[:120]}")
    return True


# ---------- 计划任务 ----------
def task_last_result(name):
    """计划任务上次运行的结果码与时刻（北京时间串）。走 PowerShell 对象接口（schtasks /V 在无控制台时不出那几行）。
    时刻取 UTC 再换算北京：本机时区会变（09-28 是 UTC-4、10-02 是 UTC-7），原样输出本地时刻负责人会读错日期。"""
    if platform.system() != "Windows":
        return None, None, None
    ps = (f"$i = Get-ScheduledTaskInfo -TaskName '{name}' -ErrorAction SilentlyContinue; "
          "if ($i) { 'RESULT=' + $i.LastTaskResult; if ($i.LastRunTime) { 'WHEN=' + $i.LastRunTime.ToUniversalTime().ToString('o') } }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30, creationflags=NO_WINDOW)
    except Exception:
        return None, None, None
    code, when, utc = None, None, None
    for ln in (r.stdout or "").splitlines():
        ln = ln.strip()
        if ln.startswith("RESULT=") and ln[7:].lstrip("-").isdigit():
            code = int(ln[7:])
        elif ln.startswith("WHEN="):
            d = C.to_bj(ln[5:].strip())
            if d and d.year > 2000:
                when, utc = f"北京 {d:%m-%d %H:%M}", d.astimezone(timezone.utc).isoformat()
    return code, when, utc


def task_exists():
    if platform.system() != "Windows":
        return False
    for name in TASK_NAMES:
        r = subprocess.run(["schtasks", "/Query", "/TN", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=NO_WINDOW)
        if r.returncode == 0:
            return True
    return False


cells_of = C.cells_of


def _gate():
    import importlib.util
    spec = importlib.util.spec_from_file_location("hgate", os.path.join(HERE, "handoff_gate.py"))
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    return g


def scan_problems(root, hours, cap=None):
    """跑写后检查扫最近 hours 小时改动的交接报告（不管谁写的）＋索引 README 的 G8。扫描模式一律滤掉 G6 跨机断链
    （对面机器上存在、本机不存在是同步不对称，不是缺陷）；G6P 反斜杠照报。返回 [(路径, 改动时刻, 问题列表)]。"""
    import glob, time as _t
    g = _gate()
    cutoff = _t.time() - hours * 3600
    out = []
    for p in sorted(glob.glob(os.path.join(root, "**", "*_交接报告.md"), recursive=True)):
        try:
            mt = os.path.getmtime(p)
        except OSError:
            continue
        if mt < cutoff or not g.is_target(p):
            continue
        probs = [x for x in g.check(p, hook_mode=False) if not x.startswith("G6 ")]
        if probs:
            out.append((os.path.abspath(p), int(mt), probs))
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


# ---------- 页面 ----------
# 颜色只表三种意思：红＝坏了／要你做事（#need、#untrusted）；琥珀＝等你看一眼（#held）；灰＝只是让你知道。绿＝你已经看过。
CSS = ('<style>:root{--fg:#1a1a1a;--bg:#fff;--mut:#666;--card:#fafafa;--line:#ddd;--a:#06c;--red:#c33;--redbg:#fff4f4;'
       '--amb:#b7791f;--ambbg:#fff9ec;--grn:#2a7a2a;--grnbg:#f2fbf2;--info:#5b7ea8;--infobg:#f0f6ff}'
       '@media (prefers-color-scheme:dark){:root{--fg:#e6e6e6;--bg:#16181c;--mut:#9aa0a6;--card:#1f2228;--line:#333;--a:#7ab7ff;'
       '--red:#ff7a7a;--redbg:#2a1d1f;--amb:#e0b050;--ambbg:#2a2418;--grn:#7ccf7c;--grnbg:#1b2a1d;--info:#8fb3e0;--infobg:#1b2330}}'
       'body{font:15px/1.7 system-ui,"Microsoft YaHei",sans-serif;max-width:60em;margin:1.5em auto;padding:0 1.2em;color:var(--fg);background:var(--bg)}'
       'h1{font-size:1.35em;margin-bottom:.2em}h2{font-size:1.08em;margin-top:1.8em;border-bottom:1px solid var(--line);padding-bottom:.3em}'
       'code,.say{background:var(--card);padding:.1em .4em;border-radius:3px;font-size:.92em;user-select:all}'
       '.banner{padding:.8em 1em;border-radius:6px;margin:1em 0;border-left:5px solid}'
       '.banner.ok{background:var(--grnbg);border-color:var(--grn)}.banner.warn{background:var(--redbg);border-color:var(--red)}'
       '.banner.info{background:var(--infobg);border-color:var(--info)}'
       '.card{margin:.8em 0;padding:.6em .9em;background:var(--card);border-left:4px solid var(--line);border-radius:3px}'
       '.card.fault{border-color:var(--red);background:var(--redbg)}.card.ask{border-color:var(--amb);background:var(--ambbg)}'
       '.card.done{border-color:var(--grn)}.card.acting{opacity:.6}'
       '.rule{font-weight:600;font-size:1.03em}.how{margin:.3em 0}.meta,.p{color:var(--mut);font-size:.88em;word-break:break-all}'
       'details{margin:.25em 0;font-size:.93em}summary{cursor:pointer;color:var(--mut)}'
       'a{color:var(--a)}.none{color:var(--mut)}.tip{color:var(--mut);font-size:.93em;margin:.4em 0}'
       'table{border-collapse:collapse;width:100%;font-size:.93em}th,td{text-align:left;padding:.3em .5em;vertical-align:top}'
       'th{border-bottom:1px solid var(--line)}'
       '.acts{margin-top:.35em}.btn{display:inline-block;margin:.2em 1.2em .2em 0;padding:.25em .8em;border:1px solid var(--a);'
       'border-radius:4px;text-decoration:none}.btn.ok{border-color:var(--grn);color:var(--grn)}'
       '.btn.no{border-color:var(--red);color:var(--red);font-weight:600}.btn.off{pointer-events:none;opacity:.4}'
       'a:focus-visible{outline:2px solid var(--a);outline-offset:2px}</style>')

# 处理页唯一的一段脚本：固定常量、不含任何数据（CSP 只放行这段的哈希）。点按钮后同卡按钮置灰、显示"已发出"；
# 3 秒后重载，看到页面是点击之后才生成的就滚到「刚才的操作」；还没等到就按 3/8/20 秒再看，最多三次。
# 不以编程方式打开 handoff-rule:（只有负责人亲手点的链接才会唤起协议）。
PAGE_JS = ('(function(){var g=+document.documentElement.getAttribute("data-generated-ms")||0;'
           'function say(t){var b=document.getElementById("acting");if(b){b.textContent=t;b.hidden=false;}}'
           'document.addEventListener("click",function(ev){var a=ev.target&&ev.target.closest?ev.target.closest(\'a[href^="handoff-rule:"]\'):null;'
           'if(!a)return;var c=a.closest(".card")||a.parentNode;if(c){c.classList.add("acting");'
           'var bs=c.querySelectorAll("a.btn");for(var i=0;i<bs.length;i++){if(bs[i]!==a)bs[i].classList.add("off");}}'
           'a.textContent="已发出，处理中…";var t=Date.now();'
           'setTimeout(function(){location.hash="#acted&t="+t+"&n=1";location.reload();},3000);});'
           'var m=/^#acted&t=(\\d+)&n=(\\d+)$/.exec(location.hash);'
           'if(m){var t=+m[1],n=+m[2];if(g>=t-2000){history.replaceState(null,"",location.pathname);'
           'var l=document.getElementById("last");if(l)l.scrollIntoView();}'
           'else if(n<4){var w=[3000,8000,20000][n-1];say("还没收到处理结果，"+Math.round(w/1000)+" 秒后再看一次…");'
           'setTimeout(function(){location.hash="#acted&t="+t+"&n="+(n+1);location.reload();},w);}'
           'else{say("还没收到处理结果。再等等，或让 AI 看一眼巡检日志。");}}'
           'document.addEventListener("visibilitychange",function(){if(document.visibilityState==="visible"&&Date.now()-g>600000)location.reload();});'
           '})();')
PAGE_JS_SHA = base64.b64encode(hashlib.sha256(PAGE_JS.encode("utf-8")).digest()).decode("ascii")


def _write_page(path, parts):
    try:
        C.atomic_write(path, "\n".join(parts) + "\n")
        return path
    except OSError as ex:
        log(f"页面写入失败 {path}：{type(ex).__name__}: {ex}")
        return None


def _head(title, now_utc):
    return [f'<!doctype html><html lang="zh-CN" data-generated-ms="{int(now_utc.timestamp() * 1000)}"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; '
            f'img-src data:; script-src \'sha256-{PAGE_JS_SHA}\'">'
            f'<title>{html.escape(title)}</title>', CSS, '</head><body>']


_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _safe_md(rel, base_dir):
    """出处／证据里的相对链接 → (docs 根下实存 .md 的绝对路径, "")，不合格 → (None, 原因)。
    **碰文件系统之前**先做纯字符串判断（解码之后）：带协议、以 / 或 \\ 开头、带盘符或 UNC、含 NUL、不是 .md 一律拒——
    realpath／isfile 碰到 \\\\主机\\共享 会真去连 SMB：连不上抛 WinError 64 让巡检整轮崩掉，连得上还会把本机的
    NTLM 凭据带过去（复核 B-01）。之后 realpath 与 isfile 也包在 try 里。"""
    r = urllib.parse.unquote(str(rel or ""))
    if (not r or "\x00" in r or C.is_remote_path(r) or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", r) or r[0] in "/\\"
            or os.path.splitdrive(r)[0]
            or not r.lower().endswith(".md")):
        return None, "文件不在允许范围"
    try:
        root = os.path.realpath(C.docs_root())
        inside = []
        for b_ in (base_dir, root):  # 先按表所在目录，再按 docs 根（手写的出处常按 docs 根写，复核 R2-2-7）
            p = os.path.realpath(os.path.join(b_, r))
            if os.path.normcase(p).startswith(os.path.normcase(root) + os.sep):
                inside.append(p)
        hit = next((p for p in inside if os.path.isfile(p)), None)
        return (hit, "") if hit else (None, "找不到文件" if inside else "文件不在允许范围")
    except (OSError, ValueError):
        return None, "文件不在允许范围"


def _src_links(cell_text, base_dir):
    """出处格里的 [编号](相对路径) 变成可点的链接——只放行 docs 根下、实存的 .md；其余照原样显示文字（防路径穿越、外链与 UNC）。"""
    e = lambda s: html.escape(str(s), quote=True)
    out, last = [], 0
    for m in _MD_LINK.finditer(cell_text or ""):
        out.append(e(cell_text[last:m.start()]))
        label, rel = m.group(1), m.group(2)
        p, why = _safe_md(rel, base_dir)
        out.append(f'<a href="{e(file_uri(p))}">{e(label)}</a>' if p else f"{e(label)}（{why}）")
        last = m.end()
    out.append(e((cell_text or "")[last:]))
    return "".join(out)


def _agreed_label(v):
    """「看过了」的显示：终端标的写明"未核实是谁"（复核 B-03）。"""
    v = str(v or "")
    return f"终端标记看过（{v[:-3].strip()}，未核实是谁）" if v.endswith(" 终端") else f"你看过了（{v}）"


def _split_why(why):
    """「为什么」格拆成正文与程序备注（"（类别：…；程序当时…）"那截尾巴）。"""
    i = (why or "").find("（类别：")
    return (why, "") if i < 0 else (why[:i].strip(), why[i:].strip())


def _say_parts(how):
    """做法句拆成"做什么"与"贴给 AI 的那句话"（后者放进可整段选中的框）。"""
    k = "把这句话贴给任一 AI 窗口："
    if how.startswith(k):
        return "把下面这句话贴给任一 AI 窗口：", how[len(k):]
    return how, ""


def write_status_page(now, table_path, sec, conds, handling, hb, scheme, st, now_utc=None):
    """处理页：第一屏只回答"现在要不要你"——要你做的事一直列着（附做法）直到解决；刚才点了什么、能撤销；
    其余按"等你确认 → 等你看一眼 → 最近生效（不用点）→ 最近撤下的（可恢复）→ 系统自己在做的"排。弹窗点正文会直达对应一区。"""
    now_utc = now_utc or datetime.now(timezone.utc)
    e = lambda s: html.escape(str(s if s is not None else ""), quote=True)
    d = os.path.dirname(os.path.abspath(table_path))
    veto = os.path.join(d, VETO_NAME)
    todo = os.path.join(d, C.TODO_NAME)
    agreed = sec.get("agreed") or {}
    rows = sec.get("rows") or {}
    btn = lambda cls, act, oid, tok, label: (f'<a class="btn {cls}" href="{scheme}:{e(act)}/{e(oid)}/{tok}">{e(label)}</a>'
                                             if scheme and tok else "")
    p = _head("协作教训 · 处理页", now_utc)
    p.append(f'<h1>处理页</h1><p class="p">生成于北京 {now:%Y-%m-%d %H:%M}。巡检每 4 小时重写一次；点完按钮这一页会自己刷新。</p>')
    unconfirmed = [r for r in sec["recent"] if r[0] not in agreed]
    if conds:
        p.append(f'<div id="now" class="banner warn"><b>要你做 {len(conds)} 件事</b>，每件下面都写了做法。</div>')
    else:
        p.append('<div id="now" class="banner ok"><b>现在不需要你。</b>'
                 + (f'最近有 {len(unconfirmed)} 条新规矩已经生效，觉得不合理可以撤（在下面）。' if unconfirmed
                    else '系统都在自己处理，可以关掉这页。') + '</div>')
    p.append('<div id="acting" class="banner info" hidden></div>')
    ld = st.get("last_decide") if isinstance(st.get("last_decide"), dict) else {}
    try:
        ld_ms = int(ld.get("ms") or 0)
    except (TypeError, ValueError):
        ld_ms = 0
    if ld_ms and now_utc.timestamp() * 1000 - ld_ms <= 10 * 60 * 1000:
        undo, ub = (ld.get("undo") if isinstance(ld.get("undo"), list) else []), ""
        # 撤销按钮的动作与编号来自状态文件：画之前先核（复核 B-06：否则改过的状态文件能在页面上塞一个外链）
        if (len(undo) == 2 and scheme and undo[0] in ("no", "unveto", "drop", "undrop") and isinstance(undo[1], str)
                and re.fullmatch(r"(LG|RP)-\d{2,4}", undo[1])):
            ua, uo = undo
            if uo.startswith("LG-"):
                rule_now = rows[uo][2] if uo in rows else ""
                ub = btn("no" if ua == "no" else "ok", ua, uo, action_token(ua, uo, rule_now) if rule_now else None,
                         "撤销（不采纳）" if ua == "no" else "撤销（恢复）")
            else:
                ent = next((x for x in (load_json(POOL_PATH, {}) or {}).get("items", []) if str(x.get("id")) == uo), None)
                if ent:
                    ub = btn("ok" if ua == "undrop" else "no", ua, uo, action_token(ua, uo, str(ent.get("rule", ""))),
                             "撤销（恢复为候选）" if ua == "undrop" else "撤销（不用）")
        p.append(f'<div id="last" class="banner info card">刚才（{e(str(ld.get("at", ""))[11:])}）：「{e(ld.get("rule", ""))}」'
                 f'<b>{e(ld.get("result", ""))}</b>　{ub}</div>')
    p.append(f'<h2 id="need">要你做的事：{len(conds)} 件</h2>')
    if conds:
        for fam, txt in conds:
            what, say = _say_parts(C.need_how(fam))
            link = ("看自动学习日志", file_uri(C.P.lessons_log)) if fam in ("stale",) else ("看巡检日志", file_uri(LOG_PATH))
            p.append(f'<div class="card fault"><div class="rule">{e(txt)}</div><div class="how">做法：{e(what)}'
                     + (f' <span class="say">{e(say)}</span>' if say else '')
                     + f'</div><div class="acts"><a class="btn" href="{e(link[1])}">{e(link[0])}</a></div></div>')
    else:
        p.append('<p class="none">没有。出了要你处理的问题，这里会一直列着，直到解决。</p>')
    untrusted = sec["untrusted"]
    if untrusted:
        p.append(f'<h2 id="untrusted">表里冒出来、等你确认的规矩：{len(untrusted)} 条</h2>')
        p.append('<p class="tip">这几条不是本机的自动学习或你在处理页上点出来的（多半是别的机器或别的窗口直接写进了表），'
                 '而且碰到了越界话题或命令、路径这类形态，所以<b>先没放进 AI 读的那份</b>。读一下：没问题点「确认生效」，不该有点「不采纳」。</p>')
        for lid, info in sorted(untrusted.items()):
            info = info if isinstance(info, dict) else {}
            rn = _rule_now(table_path, lid)
            p.append(f'<div class="card fault" id="{e(lid)}"><div class="rule">{e(info.get("rule", ""))}</div>'
                     f'<div class="how">为什么先拦着：{e(info.get("reasons", ""))}</div>'
                     f'<div class="meta">发现于 {e(info.get("since", ""))} · 内部编号 {e(lid)}（你不用记）</div><div class="acts">'
                     + btn("ok", "trust", lid, action_token("trust", lid, rn), "确认生效")
                     + btn("no", "no", lid, action_token("no", lid, rn), "不采纳") + '</div></div>')
    held = [x for x in sec["pool_items"] if x.get("_held")]
    rest = [x for x in sec["pool_items"] if not x.get("_held")]

    def pool_card(ent, cls):
        evs = ent.get("evidence") or []
        links = "　".join(f'<a href="{e(file_uri(p_))}">{e(str(ev.get("report_id", "?")))}</a>'
                          for ev in evs[:3] if isinstance(ev, dict)
                          for p_ in [_safe_md(ev.get("rel"), d)[0]] if p_)  # 与出处同一道判断（复核 B-07）
        oid = str(ent.get("id", ""))
        tok_a, tok_d = pool_token(ent), action_token("drop", oid, str(ent.get("rule", "")))
        return (f'<div class="card {cls}" id="{e(oid)}"><div class="rule">{e(ent.get("rule", ""))}</div>'
                + (f'<details><summary>为什么会有这条</summary>{e(ent.get("why", ""))}</details>' if ent.get("why") else '')
                + (f'<div class="how">为什么没自动生效：{e(ent["_held"])}</div>' if ent.get("_held") else '')
                + f'<details><summary>程序备注</summary>当时没让它直接进表的原因：{e(ent.get("reason", ""))}；'
                  f'类别 {e(ent.get("category", ""))}；入池 {e(ent.get("date", ""))}；内部编号 {e(oid)}'
                + (f'<br>证据：{links}' if links else '') + '</details><div class="acts">'
                + btn("ok", "adopt", oid, tok_a, "采纳（立即生效）") + btn("no", "drop", oid, tok_d, "不用") + '</div></div>')

    if held:
        p.append(f'<h2 id="held">等你看一眼的候选：{len(held)} 条（不点也没事）</h2>')
        p.append('<p class="tip">它们提到了权限、部署、删除、密钥这类话题，或带命令、网址、本机路径，按规定要你看过才生效。'
                 '<b>不点就一直不生效</b>，不会自己溜进去；有用点「采纳」，没用点「不用」。</p>')
        p.extend(pool_card(x, "ask") for x in held)
    recent = sec["recent"]
    p.append(f'<h2 id="recent">最近生效的规矩：{len(recent)} 条（不用点，不合理才撤）</h2>')
    if recent or sec["pending"]:
        p.append('<p class="tip">这些规矩是几个 AI 从自己写报告犯过的错里总结出来的，<b>已经生效</b>，AI 写报告前都会读。'
                 '你什么都不用做；读了觉得不合理就点「不采纳」，当场从 AI 读的那份里拿掉（点错了顶部能撤销）。'
                 '「看过了」只是以后不再简述给你。</p>')
        for lid, rule, due, why, src in recent:
            main, tail = _split_why(why)
            done = lid in agreed
            p.append(f'<div class="card {"done" if done else "info"}" id="{e(lid)}"><div class="rule">{e(rule)}</div>'
                     f'<div class="meta">已生效 · {e(due)}' + (f' · {e(_agreed_label(agreed[lid]))}' if done else '')
                     + f' · 内部编号 {e(lid)}（你不用记）</div>'
                     + (f'<details><summary>为什么会有这条</summary>{e(main)}</details>' if main else '')
                     + (f'<details><summary>出处</summary>{_src_links(src, d)}</details>' if src else '')
                     + (f'<details><summary>程序备注</summary>{e(tail)}</details>' if tail else '')
                     + '<div class="acts">'
                     + ('' if done else btn("ok", "ok", lid, action_token("ok", lid, rule), "看过了"))
                     + btn("no", "no", lid, action_token("no", lid, rule), "不采纳") + '</div></div>')
    else:
        p.append('<p class="none">最近 7 天没有新生效的规矩。</p>')
    for lid, rule, due, why, src, _raw, _auto in sec["pending"]:
        done = lid in agreed
        p.append(f'<div class="card {"done" if done else "info"}" id="{e(lid)}"><div class="rule">{e(rule)}</div>'
                 f'<div class="meta">手写的老格式：{e(due)}' + (f' · {e(_agreed_label(agreed[lid]))}' if done else '')
                 + f' · 内部编号 {e(lid)}</div><div class="acts">'
                 + ('' if done else btn("ok", "ok", lid, action_token("ok", lid, rule), "看过了"))
                 + btn("no", "no", lid, action_token("no", lid, rule), "不采纳") + '</div></div>')
    if rest or sec.get("pool_evicted"):
        p.append(f'<h2 id="pool">待自动补入的候选：{len(rest)} 条（不用点）</h2>')
        p.append('<p class="tip">程序当时没让它们直接进表（原因在程序备注里，比如证据不够、当天配额满了）。'
                 '正常情况它们当轮就已经自动生效；还留在这里的，下次 09:00 会自动补上。急着要点「采纳」，觉得不该有点「不用」。</p>')
        p.extend(pool_card(x, "info") for x in rest)
        if sec.get("pool_evicted"):
            p.append(f'<p class="tip">另有 {int(sec["pool_evicted"])} 条因为池子满了已经过期，记录还在本机的候选池文件里。</p>')
    if sec["vetoed_recent"] or sec["dropped"]:
        p.append(f'<h2 id="vetoed">最近 30 天撤下的：{len(sec["vetoed_recent"]) + len(sec["dropped"])} 条（点错了可以恢复）</h2>')
        for lid, day, who, why, rule in sec["vetoed_recent"]:
            merged = str(why).startswith("并入")
            p.append(f'<div class="card info" id="v-{e(lid)}"><div class="rule">{e(rule or "（表里已没有这条）")}</div>'
                     f'<div class="meta">{"已并入别的规矩" if merged else "已不采纳"} · {e(day)} · {e(who)}'
                     + (f' · {e(why)}' if why else '') + f' · 内部编号 {e(lid)}</div><div class="acts">'
                     + (btn("ok", "unveto", lid, action_token("unveto", lid, rule), "恢复") if rule else '') + '</div></div>')
        for ent in sec["dropped"]:
            oid = str(ent.get("id", ""))
            p.append(f'<div class="card info" id="d-{e(oid)}"><div class="rule">{e(ent.get("rule", ""))}</div>'
                     f'<div class="meta">候选，你点过「不用」 · {e(ent.get("decided", ""))} · 内部编号 {e(oid)}</div><div class="acts">'
                     + btn("ok", "undrop", oid, action_token("undrop", oid, str(ent.get("rule", ""))), "恢复为候选") + '</div></div>')
    p.append('<h2 id="auto">系统自己在做的（不需要你）</h2>')
    if handling:
        p.append('<table><tr><th>事项</th><th>做了什么</th><th></th></tr>')
        for ev, act, _n, link in handling:
            p.append(f'<tr><td>{e(ev)}</td><td>{e(act)}</td><td>'
                     + (f'<a href="{e(link[1])}">{e(link[0])}</a>' if link else '') + '</td></tr>')
        p.append('</table>')
    else:
        p.append('<p class="none">这一轮没有要记的。</p>')
    hb = hb or {}
    p.append('<h2 id="links">细节入口</h2><div class="tip">'
             f'<a href="{e(file_uri(FINDINGS_PAGE))}">逐份报告的问题清单</a>　·　<a href="{e(file_uri(todo))}">写后检查待处理清单</a>　·　'
             f'<a href="{e(file_uri(table_path))}">协作教训完整表</a>　·　<a href="{e(file_uri(veto))}">不采纳记录</a>　·　'
             f'<a href="{e(file_uri(LOG_PATH))}">巡检日志</a><br>'
             '运行情况：巡检上次按计划运行 ' + (f'<b style="color:var(--red)">{e(hb.get("task_check", "—"))}'
                                          + ('' if hb.get("task_check") == "没有记录" else '（超过 9 小时了）') + '</b>'
                                          if hb.get("task_late") else e(hb.get("task_check", "—")))
             + f'；自动学习上次开跑 {e(hb.get("daily_start", "—"))}、上次结束 {e(hb.get("daily_end", "—"))}；本页生成 {now:%m-%d %H:%M}。'
             f'套件 {e(C.SUITE_VERSION)}，{"已安装运行版" if C.P.layout == "installed" else "直接运行正本（未安装）"}。<br>'
             '暂停自动学习：PowerShell 里 <code>Disable-ScheduledTask -TaskName HandoffDaily</code>（恢复用 Enable-）；'
             '或让 AI 跑 <code>handoffctl.py doctor</code> 体检。<br>'
             '<b>这页和弹窗有一个盲区</b>：报"通知发不出"的就是发通知的这个程序本身。巡检的计划任务被禁、整机关机或长时间休眠时，'
             '没有任何东西会告诉你；隔几天看一眼上面"巡检上次按计划运行"的时刻就能发现（超过 9 小时会标红；自动学习每天跑完也会查一次巡检有没有停）。</div>')
    p.append(f'<script>{PAGE_JS}</script></body></html>')
    return _write_page(STATUS_PAGE, p)


def _rule_now(table_path, lid):
    """表里这一编号当前的规矩原文（口令要绑表里的原文，不是净化后的摘要）。"""
    try:
        row = _row_of(C.read_text(table_path), lid)
    except OSError:
        row = None
    return row[2] if row and len(row) > 2 else ""


def write_findings_page(now, table_path, sec, scan_found, scan_hours, stale=None):
    """细节页：逐份报告的问题、脚本今天自己干了什么。规矩本身在处理页（这里只给编号链接，不再重复全文）。"""
    e = lambda s: html.escape(str(s if s is not None else ""), quote=True)
    d = os.path.dirname(os.path.abspath(table_path))
    veto = os.path.join(d, VETO_NAME)
    p = _head("协作教训 · 细节清单", datetime.now(timezone.utc))
    p += [f'<h1>细节清单</h1><p class="p">生成于北京 {now:%Y-%m-%d %H:%M}。巡检每次运行重写。'
          f'要不要你、要你做什么：看 <a href="{e(file_uri(STATUS_PAGE))}">处理页</a>。</p>',
          f'<h2>一、最近 {RECENT_DAYS} 天生效的规矩</h2>']
    if sec["recent"]:
        p.append('<p class="tip">全文、理由、出处和按钮都在处理页：'
                 + "　".join(f'<a href="{e(file_uri(STATUS_PAGE))}#{e(lid)}">{e(lid)}</a>' for lid, *_ in sec["recent"]) + '</p>')
    else:
        p.append('<p class="none">最近没有新生效的规矩。</p>')
    p.append(f'<h2>二、近 {int(scan_hours)} 小时没过写后检查的报告（<b>不需要你处理</b>）</h2>')
    if scan_found:
        by_src = {}
        for path, _mt, _pr in scan_found:
            s = os.path.relpath(os.path.dirname(path), d).replace("\\", "/")
            by_src[s] = by_src.get(s, 0) + 1
        p.append('<p class="tip">这些是<b>写它们的 AI</b> 该处理的，已经写进 '
                 f'<a href="{e(file_uri(os.path.join(d, C.TODO_NAME)))}">写后检查待处理清单</a>（按来源目录分组，各 AI 开工时自查）。'
                 '"没过检查"多半是表头格式不对，程序读不出它的编号／时间／状态，内容本身不一定有错。按来源：'
                 + '，'.join(f'{e(s)} {n} 件' for s, n in sorted(by_src.items(), key=lambda kv: -kv[1])) + '</p>')
        for path, _mt, probs in scan_found[:30]:
            p.append(f'<div class="card"><b><a href="{e(file_uri(path))}">{e(os.path.basename(path))}</a></b>'
                     f'<div class="p">{e(os.path.dirname(path))}</div>' + "".join(f'<div>· {e(x)}</div>' for x in probs) + '</div>')
        if len(scan_found) > 30:
            p.append(f'<p class="tip">另有 {len(scan_found) - 30} 份，见待处理清单。</p>')
    else:
        p.append('<p class="none">全部通过。</p>')
    p.append('<h2>三、脚本今天自己干了什么</h2>')
    p.append(''.join(f'<div class="card">{e(x.split("：", 1)[-1])}</div>' for x in sec["auto_lines"]) if sec["auto_lines"]
             else '<p class="none">今天还没有自动处理记录。</p>')
    if stale:
        p.append(f'<div class="card fault"><b>自动学习异常</b><div>{e(stale)}</div></div>')
    p.append('<h2>四、常用入口</h2><div class="tip">'
             f'<a href="{e(file_uri(table_path))}">协作教训（完整表，带出处）</a>　·　'
             f'<a href="{e(file_uri(os.path.join(d, C.PUBLISH_NAME)))}">生效版（AI 实际读的那份）</a>　·　'
             f'<a href="{e(file_uri(veto))}">不采纳记录</a>　·　<a href="{e(file_uri(LOG_PATH))}">巡检日志</a><br>'
             '自己查一遍全部报告：<code>py -X utf8 docs/规范/交接写时门/handoffctl.py run scan</code></div>')
    p.append(f'<script>{PAGE_JS}</script></body></html>')
    return _write_page(FINDINGS_PAGE, p)


def ensure_published(table_path, st=None):
    """生效版版本行的「表哈希＋否决哈希」必须等于现状（v1.12 起否决记录也算：只改否决记录、表没变时以前不会重发布，
    撤下要等到第二天）。不一致就同机重发布；每日学习正占着锁时这轮先不动，连续 3 轮还没好才请负责人介入。
    返回 None（一致或已修好）或 (是否需要负责人, 说明)。"""
    pub = os.path.join(os.path.dirname(os.path.abspath(table_path)), C.PUBLISH_NAME)
    try:
        cur = C.sha(C.read_text(table_path))[:8]
        vh = C.veto_hash(table_path)
        old = C.read_text(pub) if os.path.isfile(pub) else ""
    except (OSError, UnicodeDecodeError) as e:
        return (True, f"生效版自检读文件失败：{type(e).__name__}")
    m = re.search(r"表哈希 ([0-9a-f]{8})(?: · 否决哈希 ([0-9a-f]{8}))?", old)
    if m and m.group(1) == cur and m.group(2) == vh:
        if st is not None:
            st.pop("pub_busy", None)
        return None
    why = ("生效版不存在" if not m else
           "否决记录变了、生效版还没跟上" if m.group(1) == cur else "表在上次发布之后被改过")
    if not AUTO_PUBLISH:
        return (False, why + "（自动重发布已关闭）")
    L = _lessons()
    try:
        rc = L.locked(L.publish, table_path)
    except Exception as e:
        return (True, why + f"；自动重发布出错（{type(e).__name__}: {e}）")
    if rc == 0:
        if st is not None:
            st.pop("pub_busy", None)
        return (False, why + "；已自动重发布生效版")
    if rc == 5:
        n = int((st or {}).get("pub_busy", 0)) + 1
        if st is not None:
            st["pub_busy"] = n
        if n < 3:
            return (False, why + "；每日学习正在跑（锁被占用），这轮先不刷新，下一轮再试")
        return (True, why + f"；连续 {n} 轮都因锁被占用没能重发布——可能有一轮每日学习卡住了，请看每日学习日志")
    return (True, why + f"；自动重发布失败（退出 {rc}），请看每日学习日志")


def stale_message(st, now_utc, task_present):
    """返回 (提醒文本或 None, 日志文本或 None)。只在定时任务存在时评估。"""
    if not task_present:
        st.pop("first_seen_utc", None)
        return None, None
    ls = load_json(LESSONS_STATE, {}) or {}
    last = ls.get("last_scan_utc")
    if last:
        d = C.to_bj(last)
        if d is not None:
            hours = (now_utc - d).total_seconds() / 3600
            st.pop("first_seen_utc", None)
            if hours > STALE_HOURS:
                return f"自动学习已 {int(hours)} 小时没有成功运行（上次成功：北京 {d:%m-%d %H:%M}）", None
            return None, None
    first = st.get("first_seen_utc")
    if not first:
        st["first_seen_utc"] = now_utc.isoformat()
        return None, "每日学习尚未首跑（无扫描记录），从现在起计宽限 36 小时"
    try:
        waited = (now_utc - datetime.fromisoformat(str(first))).total_seconds() / 3600
    except (TypeError, ValueError):  # 状态里的时刻坏了：从现在重新计宽限，别让巡检整轮崩（复核 B-05 同类）
        st["first_seen_utc"] = now_utc.isoformat()
        return None, "每日学习尚未首跑的计时坏了，从现在起重新计宽限 36 小时"
    if waited > STALE_HOURS:
        return f"自动学习自北京 {C.bj_str(first)} 被发现以来 {int(waited)} 小时从未成功运行", None
    return None, f"每日学习尚未首跑，宽限中（已等 {int(waited)} 小时／{STALE_HOURS}）"


# ---------- 看门狗主体 ----------
def _hard_reasons(ent):
    """池条目为什么不能自动生效（与 lessons 同一判据；lessons 已标 hold 的直接用）。"""
    if ent.get("hold"):
        return ent["hold"]
    L = _lessons()
    if not L.HOLD_SENSITIVE:
        return ""
    code = ent.get("code") or L.reason_code(ent.get("reason", ""))
    raw = L.text_field(ent.get("raw_rule")) or L.text_field(ent.get("rule"))  # 有净化前的原文就查原文（复核 N-01）
    return "；".join(L.hard_reasons(raw, code, ent.get("evidence"), check_evidence=True))


def _parse_day(s):
    try:
        return datetime.strptime(str(s or "")[:10], "%Y-%m-%d").replace(tzinfo=BJ)
    except ValueError:
        return None


def _rule_sections(text, table_path, st, ls0, now):
    """处理页上与规矩有关的各区（纯读，不改任何东西）：手写待生效、最近生效（本机加的与表外加的）、还没简述过的、
    今天的自动处理记录、最近 30 天不采纳的、最近 30 天负责人点过「不用」的、候选池。"""
    vetoed = C.veto_ids(table_path)
    agreed = st.get("agreed") or {}
    notified = st.get("notified") or {}
    held_ids = set((ls0.get("untrusted") or {}).keys())
    rows = [c for c in (cells_of(ln) for ln in text.split("\n") if ROW_PAT.match(ln)) if len(c) >= 5]
    by_id = {c[0]: c for c in rows}
    pending = []
    for c in rows:
        m = PEND_PAT.match(c[1])
        if m and c[0] not in vetoed:  # 已不采纳的不再列成"快到点"（复核 A-11）
            raw = f"{m.group(1)} {m.group(2)}"
            try:
                overdue = now >= datetime.strptime(raw, "%Y-%m-%d %H:%M").replace(tzinfo=BJ)
            except ValueError:
                overdue = False
            auto = bool(C.ADDED_ANY.search(c[4]))  # 出处格没有「加入 …（自动／人工）」标记的，promote 永远不转（复核 R2-1-8）
            due = (("已于 {0} 到期，下一次自动学习会把它转成生效" if overdue else "将于 {0} 生效") if auto
                   else "到期也不会自动生效（出处格缺「加入」标记，要手改）").format(raw)
            pending.append((c[0], c[2], due, c[3], c[4], raw, auto))  # 过期了如实说（D-06）；raw 是提醒键用的原始时刻
    recent, fresh_live = [], []
    for c in rows:
        if not c[1].startswith("生效") or c[0] in vetoed or c[0] in held_ids:
            continue
        lm = LIVE_ADDED.search(c[4])
        if not lm:
            continue
        try:
            ad = datetime.strptime(lm.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=BJ)
        except ValueError:
            continue
        if not (timedelta(minutes=-5) <= now - ad <= timedelta(days=RECENT_DAYS)):
            continue
        recent.append((c[0], c[2], f"{lm.group(1)[5:]} 加入（{lm.group(2)}）", c[3], c[4]))
        if c[0] not in agreed and f"live:{c[0]}" not in notified:
            fresh_live.append((c[0], c[2]))
    # 表外加进来、没有硬拒因、照发了的行：不带「加入」标记，上面那道逐条简述对它不起作用——单独简述，
    # 处理页同样列进「最近生效」随时可撤（复核 R2-10）
    ext_fresh = []
    for lid, info in sorted((ls0.get("ext_trusted") or {}).items()):
        c = by_id.get(lid)
        if not isinstance(info, dict) or not c or not c[1].startswith("生效") or lid in vetoed or lid in held_ids:
            continue
        try:
            ad = datetime.strptime(str(info.get("at", "")), "%Y-%m-%d %H:%M").replace(tzinfo=BJ)
        except ValueError:
            continue
        if now - ad > timedelta(days=RECENT_DAYS):
            continue
        if not any(r[0] == lid for r in recent):
            recent.append((lid, c[2], f"{str(info.get('at'))[5:]} 发现（别处加进来的）", c[3], c[4]))
        if lid not in agreed and f"live:{lid}" not in notified:
            ext_fresh.append((lid, c[2]))
    today = f"{now:%Y-%m-%d}"
    auto_lines = [ln for ln in text.split("\n") if ln.startswith(f"- {today}") and "handoff_lessons.py" in ln]
    vt = C.veto_text(table_path)  # 坏字节换成 �，不让整轮崩（复核 R2-2-1）
    vetoed_recent = []
    for ln in vt.split("\n"):
        m = C.VETO_ROW.match(ln)
        if not m:
            continue
        cc = cells_of(ln)
        d = _parse_day(cc[1] if len(cc) > 1 else "")
        if d is not None and now - d > timedelta(days=30):
            continue
        lid = m.group(1)
        vetoed_recent.append((lid, cc[1] if len(cc) > 1 else "", cc[2] if len(cc) > 2 else "", cc[3] if len(cc) > 3 else "",
                              by_id[lid][2] if lid in by_id else ""))
    pool_all = (load_json(POOL_PATH, {}) or {}).get("items") or []
    pool_items = [dict(x) for x in pool_all if str(x.get("status", "pending")) == "pending"][-20:]
    for x in pool_items:
        x["_held"] = _hard_reasons(x)
    dropped = [dict(x) for x in pool_all if str(x.get("status")) == "ignored" and not x.get("note")
               and (_parse_day(x.get("decided")) is None or now - _parse_day(x.get("decided")) <= timedelta(days=30))][-20:]
    return {"pending": pending, "recent": recent, "fresh_live": fresh_live, "ext_fresh": ext_fresh,
            "auto_lines": auto_lines, "vetoed_recent": vetoed_recent, "pool_items": pool_items, "dropped": dropped,
            "pool_evicted": sum(1 for x in pool_all if str(x.get("status", "")) == "evicted"),
            "untrusted": ls0.get("untrusted") or {}, "agreed": st.get("agreed") or {}, "rows": by_id}


_AUTO_SAY = (("否决同步", "条规矩按不采纳记录撤下了"), ("撤销否决", "条规矩的「不采纳」被撤销，已恢复生效"),
             ("", "条手写的规矩到点转成生效了"))


def _auto_text(line, skip=None, ids=False):
    """更新记录里 promote 写的那一行 → 一句人话；skip(编号, 括注) 为真的那几条不算，全不算返回 None。
    分类只看编号后面的括注：行尾括号是固定说明，三个词都在，拿整行判会把「否决同步」错当「撤销否决」（第十批实测）。"""
    head = line.split("：", 1)[-1].split(" 自动处理", 1)[0]
    groups = {}
    for lid, tag in re.findall(r"(LG-\d+)(?:\((否决同步|撤销否决)\))?", head):
        if not (skip and skip(lid, tag)):
            groups.setdefault(tag, set()).add(lid)
    parts = [(f"{'、'.join(sorted(groups[t]))}：" if ids else "") + f"{len(groups[t])} {say}"
             for t, say in _AUTO_SAY if groups.get(t)]
    return ("自动处理：" + "；".join(parts)) if parts else None


def check(table_path, now_utc=None, task_present=None, scan_root=None, scan_hours=8.0, flow_root=None, flow_days=2,
          source="task", pages_only=False):
    """巡检一轮。pages_only=True：只按现状重写处理页与细节页（拍板后当场刷新用）——不弹窗、不动提醒记录、
    不跑扫描与计划任务查询（那部分沿用上一轮巡检存下的结果）。两轮巡检同时起（睡眠唤醒后两个任务一起补跑）只让一个跑。"""
    if pages_only:
        return _check(table_path, now_utc, task_present, scan_root, scan_hours, flow_root, flow_days, source, True)
    lk = C.Lock(STATE_PATH + ".check.lock", stale_sec=600)
    if not lk.acquire(300 if source == "daily" else 5):  # 学完顺带的那轮多等一会儿：新规矩的简述别被挤到下一轮（复核 C-08）
        log("另一轮巡检正在跑，本轮跳过")
        return 0
    try:
        return _check(table_path, now_utc, task_present, scan_root, scan_hours, flow_root, flow_days, source, False)
    finally:
        lk.release()


_LS_TYPES = (("untrusted", dict), ("ext_trusted", dict), ("cap", dict), ("last_run", dict), ("last_start", dict),
             ("pending", list), ("skipped_reports", list))
_TERM_SAY = {"no": "把 1 条规矩标成了不采纳", "unveto": "恢复了 1 条不采纳过的规矩", "ok": "把 1 条新规矩标成了看过了（以后不再简述）",
             "trust": "放行了 1 条表外加进来的规矩", "adopt": "采纳了 1 条候选", "drop": "把 1 条候选标成了不用",
             "undrop": "把 1 条不用过的候选恢复了"}


def _untrusted_text(info):
    """表外加进来、碰到敏感形态被扣下的规矩：提醒与处理页第一屏共用这一句。"""
    info = info if isinstance(info, dict) else {}
    return f"表里冒出一条不是本机加的规矩，先没给 AI 读：「{cut(str(info.get('rule', '')), 30)}」"


def _veto_rows(table_path):
    """否决记录里的表格数据行 {编号: 整行}（与 common.parse_veto 同一判据：只认「| LG-xx |」开头的行）。"""
    out = {}
    for ln in C.veto_text(table_path).split("\n"):
        m = C.VETO_ROW.match(ln)
        if m:
            out.setdefault(m.group(1), ln.strip())
    return out


def _utf8_ok(p):
    """文件能按 UTF-8 解码（不存在、读不了的不在这里管）。"""
    try:
        with open(p, "rb") as f:
            f.read().decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False
    except OSError:
        return True


def _published_ok(table_path):
    """生效版的版本行与表、否决记录对得上（只读比对，不发布）。"""
    try:
        old = C.read_text(os.path.join(os.path.dirname(os.path.abspath(table_path)), C.PUBLISH_NAME))
        m = re.search(r"表哈希 ([0-9a-f]{8})(?: · 否决哈希 ([0-9a-f]{8}))?", old)
        return bool(m and m.group(1) == C.sha(C.read_text(table_path))[:8] and m.group(2) == C.veto_hash(table_path))
    except (OSError, UnicodeDecodeError):
        return False


def _coerce(d, spec):
    """状态文件里类型不对的字段换成空值（复核 B-05：一个坏字段曾让巡检每轮在同一处崩、心跳不落盘、也不自愈）。"""
    d = d if isinstance(d, dict) else {}
    for k, typ in spec:
        if k in d and not isinstance(d[k], typ):
            log(f"状态文件里 {k} 的类型不对（{type(d[k]).__name__}），这一轮当空值处理")
            d[k] = typ()
    return d


def _check(table_path, now_utc, task_present, scan_root, scan_hours, flow_root, flow_days, source, pages_only):
    st = _coerce(load_json(STATE_PATH, {"notified": {}, "attempts": {}}),
                 (("notified", dict), ("attempts", dict), ("agreed", dict), ("last_decide", dict), ("flow", dict),
                  ("page_cache", dict), ("last_check", dict)))
    if "veto_seen" in st and not isinstance(st["veto_seen"], list):
        st.pop("veto_seen")
    st["acts"] = _acts(st)
    if not st.get("page_secret") and not pages_only:  # 处理页口令的本机种子；刚读完就写回，不与 decide 抢写
        st["page_secret"] = secrets.token_hex(16)
        save_json(STATE_PATH, st)
    notified, attempts = st.setdefault("notified", {}), st.setdefault("attempts", {})
    now_utc = now_utc or datetime.now(timezone.utc)
    start_ms = int(datetime.now(timezone.utc).timestamp() * 1000)  # 真实开跑时刻（测试里 now_utc 是假的）
    now = now_utc.astimezone(BJ)
    today = f"{now:%Y-%m-%d}"
    cutoff = f"{now - timedelta(days=KEEP_DAYS):%Y-%m-%d}"
    if not pages_only:
        _prune(st, cutoff)
        if "last_task_check" not in st and isinstance(st.get("last_check"), dict) and st["last_check"].get("source") is None:
            st["last_task_check"] = dict(st["last_check"])  # 升级过渡：旧心跳没有 source，先当计划任务那一轮留着（复核 C-09）
        st["last_check"] = {"utc": now_utc.isoformat(), "pid": os.getpid(), "version": VERSION, "source": source}
        if source == "task":  # 看门狗心跳只认计划任务那一轮（每日学习顺带的那轮不冒充巡检还活着）
            st["last_task_check"] = dict(st["last_check"])
    try:
        text, bad_bytes = C.read_text(table_path), False
    except UnicodeDecodeError:  # 表里混进坏字节：照样巡检（坏字节换成 �），请负责人介入，别让整轮崩掉（复核 B-01、R2-2-1）
        with io.open(table_path, encoding="utf-8", errors="replace") as f:
            text, bad_bytes = f.read(), True
    _pub_path = os.path.join(os.path.dirname(os.path.abspath(table_path)), C.PUBLISH_NAME)
    bad_files = [nm for nm, bad in (("教训表", bad_bytes), ("不采纳记录", not _utf8_ok(C.veto_path(table_path))),
                                    ("生效版", not _utf8_ok(_pub_path))) if bad]
    msgs, conds, handling = [], [], []  # msgs：(键, 文字, 档：need/info/hold)；conds：现在成立的介入条件 (类, 文字)
    veto_keys = {}  # 不采纳记录变化的提醒键 → (送达后记到 _veto_add/_veto_remove, 编号)

    def need(family, key, txt):
        conds.append((family, txt))
        if key not in notified:
            msgs.append((key, txt, "need"))

    def tell(key, txt, kind="info"):
        if key not in notified:
            msgs.append((key, txt, kind))

    # ⓪ 生效版凭证：先发布、再读账本与 untrusted（复核 R2-04）
    if not pages_only and bad_files:
        log(f"{'、'.join(bad_files)}里有坏字节，这一轮不重发布生效版（别拿读错的表去发布）")
    elif not pages_only:
        pub_note = ensure_published(table_path, st)
        if pub_note:
            log(pub_note[1])
            if pub_note[0]:
                need("pubfail", f"pubfail:{today}", "AI 读的那份规矩没能刷新：" + cut(C.toast_scrub(pub_note[1])[0], 40))
    if bad_files and not pages_only:
        need("lint", f"lint:bytes:{today}", f"{'、'.join(bad_files)}里混进了不是 UTF-8 的坏字节（多半是用 PowerShell 的 "
                                              "Set-Content／Add-Content 写过），部分规矩可能读错")
    ls0 = _coerce(load_json(LESSONS_STATE, {}), _LS_TYPES)
    if not pages_only and not st.get("live_keys_v112"):  # 升级首轮：v1.11 已经简述过的、负责人已同意的，不再重复说
        for k in list(notified):
            if k.startswith("livenew:"):
                for lid in k.split(":", 2)[-1].split(","):
                    if re.fullmatch(r"LG-\d+", lid.strip()):
                        notified.setdefault(f"live:{lid.strip()}", notified[k])
        for lid, v in (st.get("agreed") or {}).items():
            notified.setdefault(f"live:{lid}", v)
        st["live_keys_v112"] = f"{now:%Y-%m-%d %H:%M}"
    sec = _rule_sections(text, table_path, st, ls0, now)

    if not pages_only:
        # ① 手写的老格式「拟生效」行：只告知一次（10-03 起不再常驻催——它到点自己生效，你不用做事）
        for lid, rule, due, _w, _s, due_raw, auto in sec["pending"]:
            if lid not in (st.get("agreed") or {}):  # 负责人看过了就不再说；键用原始到期时刻（到期前后文案会变）
                tell(f"pending:{lid}:{due_raw}", f"有 1 条手写的规矩{due}" + ("，不用你做事" if auto else "") + f"：「{cut(rule, 30)}」")
        # ③ 脚本自动处理的记录：弹窗只说手写行到点转生效（看过了的不说）。按不采纳记录撤下、撤销不采纳这两种不在这里说：
        #    处理页点的当时有回执，终端点的由下面 ③' 说，别处改不采纳记录的由 ⑤ 的「多了／少了 N 条」说（复核 A-02、B-04）
        cut_ms = now_utc.timestamp() * 1000 - 7 * 86400 * 1000
        agreed0 = st.get("agreed") or {}
        skip = lambda lid, tag: bool(tag) or lid in agreed0
        for ln in sec["auto_lines"]:
            if re.search(r"否决同步|撤销否决|转生效", ln):
                t = _auto_text(ln, skip)
                if t:
                    tell("auto:" + hashlib.sha256(ln.encode("utf-8")).hexdigest()[:10], t)
        # ③' 终端替负责人做的事（未核实是谁敲的）：告知一次——终端那边的回执是关掉的（复核 B-04）
        for a in st["acts"]:
            if a.get("src") == "terminal" and a["ms"] >= cut_ms and a.get("act") in _TERM_SAY:
                tell(f"term:{a['act']}:{a['oid']}:{a['ms']}",
                     f"终端里有人{_TERM_SAY[a['act']]}（未核实是谁）：「{cut(str(a.get('rule', '')), 16)}」，不同意就去处理页撤销")

    # ④ 每日学习有没有跑成：计划任务结果码按语义判；同一次运行脚本自己记了结果的，以脚本记录为准，不重复报。
    #    10-03 起偶发的一次没跑成只轻声告知（下一轮会再跑）；连续 36 小时没成功才请负责人介入（stale）
    ls = ls0
    lr = ls.get("last_run") or {}
    lstart = ls.get("last_start") or {}
    stale = None
    daily_running = False
    backlog = len(ls.get("pending") or [])
    if not pages_only:
        present = task_present if task_present is not None else task_exists()
        tfails = []
        for tname in TASK_NAMES:
            res = tuple(task_last_result(tname)) + (None,)
            rcode, rwhen, rutc = res[0], res[1], res[2]
            kind, meaning = C.task_result_meaning(rcode)
            if kind == "running":
                if source == "daily":  # 顺带的这一轮就跑在每日学习的计划任务进程里，"正在运行"说的是自己（复核 C-04）
                    continue
                daily_running = True
                continue
            if kind != "fail":
                continue
            hexc = f"0x{rcode & 0xFFFFFFFF:08X}" if isinstance(rcode, int) else "?"
            same_run = True
            if rutc:
                lr_at, t_at = C.to_bj(lr.get("utc")), C.to_bj(rutc)
                same_run = bool(lr_at and t_at and timedelta(0) <= lr_at - t_at <= timedelta(hours=2))
            explained = lr.get("rc") not in (None, 0) and 1 <= (rcode or 0) <= 9 and same_run
            if not explained:
                key = f"taskfail:{tname}:{rwhen}"
                if key not in notified:
                    log(f"计划任务 {tname} 上次自动运行没成功：{meaning}（结果码 {hexc}）" + (f"，{rwhen}" if rwhen else ""))
                known = rcode in C.TASK_RESULT or (isinstance(rcode, int) and 1 <= rcode <= 9)
                what = meaning if known else "以一个没见过的结果码结束（码已记进巡检日志）"  # 复核 A-08：码不进弹窗
                tfails.append((key, what + (f"（{rwhen}）" if rwhen else "")))
        stale, note = (None, None) if daily_running else stale_message(st, now_utc, present)  # 正在跑就这轮不评判
        if note:
            log(note)
        if stale:
            need("stale", f"stale:{today}", stale)
        # 已经请负责人介入（stale）时，同一弹窗里的"这一轮没跑成"只当原因说，不再缀"下一轮会再跑、连续没成功才请你介入"
        again, again_pg = ("", "") if stale else ("。下一轮会再跑，连续没成功才会请你介入", "；下一轮会再跑")
        for key, what in tfails:
            tell(key, ("最近一次没跑成的原因：" if stale else "自动学习的计划任务这一轮没跑成：") + what + again)
            handling.append(("自动学习的计划任务这一轮没跑成", what + again_pg, False, None))
        if not daily_running and lr.get("rc") not in (None, 0):
            err = cut(C.toast_scrub(str(lr.get("error") or ""))[0], 60)
            tell(f"dailyerr:{str(lr.get('utc', ''))[:16]}",
                 f"自动学习上次运行出错（北京 {C.bj_str(lr.get('utc'))}）：{err}" + ("" if stale else "。下一轮会再跑"))
            handling.append(("自动学习上次运行出错", f"北京 {C.bj_str(lr.get('utc'))}：{err}" + again_pg, False,
                             ("看自动学习日志", file_uri(C.P.lessons_log))))
        if lstart.get("utc") and not daily_running:
            s_at, r_at = C.to_bj(lstart.get("utc")), C.to_bj(lr.get("utc"))
            if s_at and (r_at is None or r_at < s_at) and now - s_at > timedelta(hours=2) and not C.pid_alive(lstart.get("pid")):
                tell(f"dailykilled:{str(lstart.get('utc'))[:16]}",
                     f"自动学习北京 {s_at:%m-%d %H:%M} 开跑后没跑完（多半是电脑睡眠、拔电或超时被系统终止）"
                     + ("" if stale else "，下一轮会自动补上"))
                handling.append(("自动学习开跑后没跑完", f"北京 {s_at:%m-%d %H:%M} 开跑，没有跑完的记录" + again_pg, False,
                                 ("看自动学习日志", file_uri(C.P.lessons_log))))
        cap = ls.get("cap") or {}
        cap_at = C.to_bj(str(cap.get("at", "")).replace(" ", "T") + ("+08:00" if cap.get("at") else "")) if cap.get("at") else None
        if cap.get("full") and cap_at and now - cap_at <= timedelta(hours=26):
            msg = (f"教训表满了（{cap.get('total_cap', '?')} 条），新规矩暂停自动生效（{cap.get('waiting', 0)} 条在排队）。"
                   "想腾地方：让 AI 把意思相近的规矩合并成一份方案给你")
            iso = now.isocalendar()
            tell(f"capfull:{iso[0]}-W{iso[1]:02d}", msg)  # 每周说一次就够
            handling.append(("教训表满了", msg, False, None))
        if backlog > int(C.cfg("lessons", "backlog_alert", 60)):
            tell(f"backlog:{today}", f"待读的报告积压 {backlog} 件，新规矩会晚几天才收进来，不用你做事")
        for lid, info in sorted((ls.get("untrusted") or {}).items()):
            need("untrusted", f"untrusted:{lid}:{(info if isinstance(info, dict) else {}).get('hash', '')}", _untrusted_text(info))
        # ⑤' 不采纳记录的变化。veto_seen＝负责人已经知道的不采纳编号：处理页／终端点「不采纳」当场记进去、点「恢复」当场移出。
        #     别处加的（多半是同步来的）说「多了 N 条」，别处删的说「少了 N 条」；**送达了（或三次放弃）才改 veto_seen**——
        #     这一轮挤不进弹窗的，下一轮按同一个键接着说（复核 A-01、A-02、C-03：以前当轮就并进去，挤掉了就再也不说）
        vt_rows = _veto_rows(table_path)
        disk0 = load_json(STATE_PATH, {}) or {}  # 比对前重读：开跑之后负责人点的「不采纳／恢复」以磁盘为准（复核 R2-1-3）
        if isinstance(disk0.get("veto_seen"), list):
            st["veto_seen"] = disk0["veto_seen"]
        if isinstance(disk0.get("acts"), list):
            st["acts"] = _acts(disk0)
        gen = _int(disk0.get("veto_gen"))
        if not st.get("veto_v2") or not isinstance(st.get("veto_seen"), list):
            # 升级首轮（或从没比过）：现有的不采纳都当已知、不告知——旧版 veto_seen 只增不减，拿它比会把负责人早先恢复过的
            # 误报成"少了"（复核 R2-1-5）
            st["veto_seen"] = st["_veto_reset"] = sorted(vt_rows)
            st["veto_v2"] = f"{now:%Y-%m-%d %H:%M}"
        seen = set(st["veto_seen"])
        added, removed = sorted(set(vt_rows) - seen), sorted(seen - set(vt_rows))
        latest = {}
        for a in st["acts"]:
            if a["oid"] in removed and a["ms"] >= latest.get(a["oid"], {}).get("ms", -1):
                latest[a["oid"]] = a
        mine = [lid for lid in removed if latest.get(lid, {}).get("act") == "unveto"]  # 负责人在处理页或终端恢复的
        st.setdefault("_veto_remove", []).extend(mine)
        other = [lid for lid in removed if lid not in mine]
        for ids, key, txt, how in (
                (added, f"vetoext:g{gen}:" + C.sha("\n".join(vt_rows[x] for x in added))[:10],
                 f"不采纳记录里多了 {len(added)} 条（不是从处理页或终端点的，多半是别的机器同步来的），这几条已经从 AI 读的"
                 "规矩里撤下；不同意就去处理页「最近 30 天撤下的」里点「恢复」", "_veto_add"),
                (other, f"vetoback:g{gen}:" + C.sha(",".join(other))[:10],
                 f"不采纳记录里少了 {len(other)} 条（不是从处理页或终端撤的），这几条会重新给 AI 读；不同意就让 AI 把它们加回不采纳记录",
                 "_veto_remove")):
            if not ids:
                continue
            if key in notified:  # 以前说过了（状态没来得及落盘）：直接记账，不重复说
                st.setdefault(how, []).extend(ids)
            else:
                tell(key, txt)
                veto_keys[key] = (how, ids)
        # ⑤ 表体检：认不出的状态格（LG-30 那样 10 天没人发现）、错列、编号重复、生效版里的 @导入
        try:
            pub_text = C.read_text(os.path.join(os.path.dirname(os.path.abspath(table_path)), C.PUBLISH_NAME))
        except (OSError, UnicodeDecodeError):
            pub_text = None
        lint = C.lint_table(text, pub_text)
        if lint:
            need("lint", "lint:" + C.sha(json.dumps(lint, ensure_ascii=False))[:10],
                 f"教训表里有 {len(lint)} 处程序认不出的地方，这些规矩可能既不生效也不提醒")
            for a, b in lint:
                handling.append((f"表里 {a} 认不出", b, False, ("打开完整表", file_uri(table_path))))
    else:
        # 拍板后当场重写：其余几类沿用上一轮巡检的结论；拍板会改变的两类按现状重算（纯读，不发布）——
        # 处理掉一条表外规矩后第一屏还说"要你做 1 件事"、恢复后又被扣下却说"不需要你"，是复核 A-04 抓到的自相矛盾
        cache = st.get("page_cache") or {}
        conds = [tuple(x) for x in cache.get("conds") or [] if isinstance(x, (list, tuple)) and len(x) == 2
                 and x[0] != "untrusted" and not (x[0] == "pubfail" and _published_ok(table_path))]
        conds += [("untrusted", _untrusted_text(info)) for _lid, info in sorted((ls0.get("untrusted") or {}).items())]
        handling = [tuple(x[:3]) + ((tuple(x[3]) if x[3] else None),) for x in cache.get("handling") or []
                    if isinstance(x, (list, tuple)) and len(x) >= 4]
        stale = cache.get("stale")

    # ⑥ 写后检查扫描（各 AI 自查，不弹给负责人；同一窗口一天 ≥3 份只轻声告知）
    scan_found = []
    d = os.path.dirname(os.path.abspath(table_path))
    todo_uri = file_uri(os.path.join(d, C.TODO_NAME))
    if scan_root and not pages_only:
        try:
            scan_found = scan_problems(scan_root, scan_hours)
            g = _gate()
            todo_path = os.path.join(os.path.abspath(scan_root), g.TODO_NAME)
            if not g.todo_md(scan_root, scan_found, todo_path, scan_hours, writer=TODO_WRITER):
                log(f"! 待处理清单写入失败：{todo_path}")
                need("todo_fail", f"todo_fail:{today}", "写后检查的待处理清单写不出来，各窗口的自查会失效")
            fresh = [x for x in scan_found if f"scan:{os.path.basename(x[0])}:{x[1]}" not in notified]
            for p_, mt, probs in fresh:
                src = os.path.relpath(os.path.dirname(p_), scan_root).replace("\\", "/")
                notified[f"scan:{os.path.basename(p_)}:{mt}"] = f"{now:%Y-%m-%d %H:%M} 已列入待处理清单 @{src}"
                log(f"  新的没过检查：{os.path.relpath(p_, scan_root)}（{len(probs)} 处）首条：{probs[0][:90]}")
            by_src = {}
            for k, v in notified.items():
                if k.startswith("scan:") and isinstance(v, str) and v.startswith(today) and " @" in v:
                    src = v.rsplit(" @", 1)[1]
                    by_src[src] = by_src.get(src, 0) + 1
            for src, n_ in sorted(by_src.items(), key=lambda kv: -kv[1]):
                if n_ >= 3:
                    tell(f"esc:{src}:{today}", f"「{src}」这个窗口今天 {n_} 份报告没过写后检查——想管的话去那个窗口说一句："
                                               "开工先读写后检查待处理清单里自己目录的条目")
                    handling.append((f"「{src}」今天 {n_} 份报告没过写后检查", "想管的话去那个窗口说一句：开工先读待处理清单里自己目录的条目",
                                     False, ("打开待处理清单", todo_uri)))
            line = f"写后检查扫描：近 {int(scan_hours)} 小时，不合格 {len(scan_found)} 件，新出现 {len(fresh)} 件"
            if line != st.get("last_scan_line") or fresh:
                log(line)
            st["last_scan_line"] = line
        except Exception as e:
            log(f"写后检查扫描失败（不影响其他提醒）：{type(e).__name__}: {str(e)[:120]}")
            need("todo_fail", f"todo_fail:{today}", "写后检查扫描这一轮没跑成，待处理清单没刷新，各窗口的自查会失效")
    elif pages_only:
        scan_found = [tuple(x) for x in (st.get("page_cache") or {}).get("scan_found") or []]

    # ⑦ 规范扫描（handoff_flow.py，report-only）：按稳定键比新增。发现是给写报告的各 AI 窗口看的（生效版页首要求开工先看清单），
    #    负责人什么都不用做——10-03 负责人看到"需要你介入：发现 1 条新的不规范"问"我该怎么做"，从此**不弹窗**，
    #    只进清单文件与处理页「系统自己在做的」那一行（写明本轮新增几条），新指纹当轮并进基线。扫描本身没跑成仍常驻提醒（机器坏了）。
    if flow_root and not pages_only:
        try:
            ftodo = os.path.join(os.path.abspath(flow_root), "工作传递", C.FLOW_TODO_NAME)
            r = subprocess.run([sys.executable, "-X", "utf8", "-B", os.path.join(HERE, "handoff_flow.py"), "scan", flow_root,
                                "--days", str(int(flow_days)), "--todo", ftodo, "--writer", FLOW_WRITER],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=180, creationflags=NO_WINDOW)
            out = (r.stdout or "") + (r.stderr or "")
            m = re.search(r"共 (\d+) 条", out)
            n = int(m.group(1)) if m else (0 if "无发现" in out else -1)
            if r.returncode == 2:
                n = -1
            breakdown = {k: out.count(f"- **{k}**") for k in ("W1", "W2", "W3")}
            mk = re.search(r"^#keys (\[.*\])\s*$", out, re.M)
            if not mk and re.search(r"^#keys\b", out, re.M):
                n = -1
            if mk:
                try:
                    src_keys = [str(k) for k in json.loads(mk.group(1))]
                except ValueError:
                    src_keys, n = [], -1
            else:
                try:
                    full = C.read_text(ftodo)
                except OSError:
                    full = out
                src_keys = [ln.strip() for ln in full.split("\n") if re.match(r"^- \*\*W\d\*\*", ln)]
            fps = sorted({hashlib.sha256(k.encode("utf-8", "replace")).hexdigest()[:12] for k in src_keys})
            if mk:
                breakdown = {t: sum(1 for k in src_keys if k.startswith(t + ":")) for t in ("W1", "W2", "W3")}
            kind = "keys" if mk else "lines"
            prev = st.get("flow") or {}
            prev_fps = set(prev.get("fps") or [])
            n_new = len(set(fps) - prev_fps) if (n >= 0 and prev and prev.get("kind") == kind) else 0
            if n >= 0:
                handling.append((f"规范扫描：{n} 条" + (f"（{'、'.join(f'{k}×{v}' for k, v in breakdown.items() if v)}）"
                                                        if any(breakdown.values()) else "") + (f"，本轮新增 {n_new} 条" if n_new > 0 else ""),
                                 "给写报告的各 AI 窗口看的，不用你处理：清单在 工作传递/规范扫描-待处理.md，各来源开工先看自己被点名的条目",
                                 False, ("看规范扫描清单", file_uri(ftodo))))
                st["flow"] = {"fps": fps, "kind": kind, "n": n, "at": f"{now:%Y-%m-%d %H:%M}", "new": n_new}
            else:
                need("flowerr", f"flowerr:{today}", "规范扫描这一轮没跑成（脚本出错或输出认不出），违规清单没刷新")
            line = f"规范扫描：{n} 条（新增指纹 {n_new}，不弹窗）；清单 {ftodo if n >= 0 else '未写出'}"
            if line != st.get("last_flow_line") or n_new or n < 0:
                log(line)
            st["last_flow_line"] = line
        except Exception as e:
            log(f"规范扫描失败（不影响其他提醒）：{type(e).__name__}: {str(e)[:120]}")
            need("flowerr", f"flowerr:{today}", "规范扫描这一轮没跑成（超时或起不来），违规清单没刷新")

    # ⑨ 被拒候选池：硬拒因的（越界、注入形态、冲突、超长）不会自动生效，告知一次；其余等下一轮自动补入，只上页面
    held_new = [x for x in sec["pool_items"] if x["_held"] and f"pool:{x.get('id')}" not in notified]
    if held_new and not pages_only:
        tell("poolhold:" + ",".join(str(x.get("id", "")) for x in held_new)[:60],
             f"有 {len(held_new)} 条候选没自动生效：它们提到了权限、路径这类内容，按规定要你看过才生效。"
             "不用就不管；想用去处理页点「采纳」", kind="hold")

    if not pages_only:
        last = ls.get("last_scan_utc")
        handling.insert(0, ("自动学习", (f"上次成功 北京 {C.bj_str(last)}，待读积压 {backlog} 件" if last
                                       else "还没首跑过（36 小时宽限内不算故障）") + ("；此刻正在运行" if daily_running else ""), False, None))
        for one in sec["auto_lines"]:
            handling.append(("脚本自动处理", (_auto_text(one, ids=True) if re.search(r"否决同步|撤销否决|转生效", one) else None)
                             or one.split("：", 1)[-1][:90], False, None))
        if scan_found:
            handling.append((f"{len(scan_found)} 份报告没过写后检查", "已写进待处理清单，由写它们的窗口自查；已冻结的不回改", False,
                             ("看待处理清单", todo_uri)))
        skipped = ls.get("skipped_reports") or []
        if skipped:
            handling.append((f"{len(skipped)} 份报告被跳过", "单独送模型连续 3 次都解析失败，不再重试；需要的话让 AI 手动看一眼",
                             False, ("看自动学习日志", file_uri(C.P.lessons_log))))
        if C.P.layout == "installed":
            try:
                canon = C.canon_dir()
                if os.path.abspath(canon) != os.path.abspath(HERE):
                    diff = [f for f in C.CODE_FILES if os.path.isfile(os.path.join(canon, f)) and os.path.isfile(os.path.join(HERE, f))
                            and C.sha(C.read_text(os.path.join(canon, f))) != C.sha(C.read_text(os.path.join(HERE, f)))]
                    if diff:
                        handling.append(("运行版落后于正本", f"{'、'.join(diff)} 正本改过还没部署（AI 改完脚本要跑 handoffctl.py test 与 promote）",
                                         False, None))
            except OSError:
                pass

    # 页面（拍板后的当场刷新也走这里）
    if not pages_only:
        disk = load_json(STATE_PATH, {}) or {}
        dld = disk.get("last_decide") if isinstance(disk.get("last_decide"), dict) else {}
        try:
            dms = int(dld.get("ms") or 0)
        except (TypeError, ValueError):
            dms = 0
        if dms >= start_ms:  # 复核 A-12：以前用开跑时读的状态写页面，把拍板当场写好的页面盖回旧样子
            for k, typ in (("agreed", dict), ("last_decide", dict), ("acts", list)):
                if isinstance(disk.get(k), typ):
                    st[k] = disk[k]
            st["acts"] = _acts(st)
            try:
                text = C.read_text(table_path)
            except (OSError, UnicodeDecodeError):
                pass
            ls0 = _coerce(load_json(LESSONS_STATE, {}), _LS_TYPES)
            sec = _rule_sections(text, table_path, st, ls0, now)
            conds = [c for c in conds if c[0] != "untrusted"] + [("untrusted", _untrusted_text(info))
                                                                 for _lid, info in sorted((ls0.get("untrusted") or {}).items())]
    th_at = C.to_bj(C.task_heartbeat(st).get("utc"))
    hb = {"daily_start": C.bj_str(lstart.get("utc")) if lstart.get("utc") else "—（这次部署后还没跑过）",
          "daily_end": C.bj_str(lr.get("utc")) if lr.get("utc") else "—",
          "task_check": f"{th_at:%m-%d %H:%M}" if th_at else "没有记录", "task_late": (not th_at) or now - th_at > timedelta(hours=9)}
    write_findings_page(now, table_path, sec, scan_found, scan_hours, stale)
    scheme = (RULE_SCHEME if pages_only else ensure_protocol(table_path)) if (
        sec["pending"] or sec["recent"] or sec["pool_items"] or sec["untrusted"] or sec["vetoed_recent"] or sec["dropped"]) else None
    status = write_status_page(now, table_path, sec, conds, handling, hb, scheme, st, now_utc)
    if pages_only:
        return 0
    st["page_cache"] = {"at": f"{now:%Y-%m-%d %H:%M}", "conds": [list(x) for x in conds],
                        "handling": [[a, b, c, list(dd) if dd else None] for a, b, c, dd in handling],
                        "scan_found": [list(x) for x in scan_found[:30]], "stale": stale}

    # 弹窗：需要你介入一条（常驻）＋新规矩简述一条（静音）；两样都没有时，告知类合成一条（静音、24 小时后消失）
    live_all = [(lid, rule, False) for lid, rule in sec["fresh_live"]] + [(lid, rule, True) for lid, rule in sec["ext_fresh"]]
    if not msgs and not live_all:
        log("check：无需提醒（处理页已刷新）")
        merge_save_state(st, cutoff)
        return 0
    need_m = [m for m in msgs if m[2] == "need"]
    other_m = [m for m in msgs if m[2] != "need"]
    sends = []  # (送达否, 这条弹窗里真说到了的键)
    if need_m:
        first = need_m[0]
        fam = first[0].split(":", 1)[0]
        title = (f"需要你介入：{cut(first[1], 26)}" if len(need_m) == 1
                 else f"需要你介入（{len(need_m)} 项）：{cut(first[1], 16)} 等")
        lines = [first[1], "做法：" + C.need_how(fam)]
        rest = need_m[1:] + other_m
        extra = max(0, len(conds) - len(need_m))  # 之前提醒过、仍然成立的要你做的事（同类弹窗会替换掉旧的那条，复核 A-03）
        shown = rest[:2] if (len(rest) <= 2 and not extra) else rest[:1]
        lines += [m[1] for m in shown]
        if extra:
            lines.append(f"要你做的事一共 {len(conds)} 件" + (f"，另有 {len(rest) - len(shown)} 条消息" if len(rest) > len(shown) else "")
                         + "，处理页上都列着")
        elif len(rest) > len(shown):
            lines.append(f"另有 {len(rest) - len(shown)} 件，下一轮接着说")
        ok = toast(title, "\n".join(lines), kind="need")
        sends.append((ok, [first[0]] + [m[0] for m in shown]))
    if live_all:
        shown_l = live_all[:3]  # 一次最多三条：只给真进了正文的记"已简述"，其余下一轮再说（每条恰好说一次）
        n_all = len(live_all)
        lines = ["· " + (f"（别处加进来的）「{cut(rule, 24)}」" if ext else f"「{cut(rule, 32)}」") for _lid, rule, ext in shown_l]
        lines.append("不合理去处理页点「不采纳」" if n_all <= 3 else f"共 {n_all} 条，其余下次再说；不合理去处理页点「不采纳」")
        ok = toast(f"新学到 {n_all} 条规矩（已生效，不合理可撤）", "\n".join(lines), kind="live",
                   tag="live-" + C.sha(",".join(x[0] for x in shown_l))[:8])
        sends.append((ok, ["live:" + x[0] for x in shown_l]))
    if not need_m and not live_all and other_m:
        if all(m[2] == "hold" for m in other_m):
            title, kind = f"有 {len(held_new)} 条候选没自动生效（不点也没事）", "hold"
            lines = [m[1] for m in other_m[:4]]
            shown = other_m[:4]
        else:
            kind = "info"
            shown = other_m[:4] if len(other_m) <= 4 else other_m[:3]
            if conds or any(m[0].startswith(("term:", "vetoext:", "vetoback:")) for m in shown):
                # 有仍然成立的要你做的事（复核 A-06），或说的是别处／终端做的事（不是"系统自动处理"，复核 R2-1-7）
                title = f"知会一声（{len(other_m)} 件）" if len(other_m) > 1 else "知会一声"
            else:
                title = f"自动处理了 {len(other_m)} 件事，不用你做事" if len(other_m) > 1 else "知会一声，不用你做事"
            lines = [m[1] for m in shown] + ([f"另有 {len(other_m) - len(shown)} 件，下一轮接着说"] if len(other_m) > len(shown) else [])
        ok = toast(title, "\n".join(lines), kind=kind)
        sends.append((ok, [m[0] for m in shown]))
    all_ok = True
    for ok, keys in sends:
        all_ok = all_ok and ok
        for key in keys:
            if ok or attempts.get(key, 0) >= 2:  # 送达了，或这是第三次没送达（下面记放弃）：不采纳记录的变化记账
                if key in veto_keys:
                    st.setdefault(veto_keys[key][0], []).extend(veto_keys[key][1])
            if ok:
                notified[key] = f"{now:%Y-%m-%d %H:%M}" + (" 已简述" if key.startswith("live:") else "")
                if key.startswith("poolhold:"):
                    for x in held_new:
                        notified[f"pool:{x.get('id')}"] = f"{now:%Y-%m-%d %H:%M} 已告知（需点采纳才生效）"
            else:
                attempts[key] = attempts.get(key, 0) + 1
                if attempts[key] >= 3:
                    notified[key] = f"{now:%Y-%m-%d %H:%M} 放弃（三次未送达）"
                    if key.startswith("poolhold:"):
                        for x in held_new:
                            notified[f"pool:{x.get('id')}"] = f"{now:%Y-%m-%d %H:%M} 放弃（三次未送达）"
                    log(f"放弃提醒（三次未送达）：{key[:60]}")
    merge_save_state(st, cutoff)
    return 0 if all_ok else 1


def main(a):
    if len(a) >= 3 and a[0] == "toast":
        return 0 if toast(a[1], a[2], kind="test") else 1
    opt = lambda k, d: a[a.index(k) + 1] if k in a and len(a) > a.index(k) + 1 else d
    if len(a) >= 2 and a[0] in ("rule", "veto"):
        tbl = opt("--table", None) or C.table_path()
        arg = a[1] if a[0] == "rule" else "no/" + a[1].split(":")[-1]
        return decide(arg, tbl, who=opt("--who", None))
    if a and a[0] == "register":
        return 0 if ensure_protocol(opt("--table", None) or C.table_path(), force=True) else 1
    if len(a) >= 2 and a[0] == "check":
        return check(a[1], scan_root=opt("--with-scan", None), scan_hours=float(opt("--scan-hours", C.cfg("notify", "scan_hours", 8))),
                     flow_root=opt("--with-flow", None), flow_days=float(opt("--flow-days", C.cfg("notify", "flow_days", 2))),
                     source=opt("--source", "task"))
    print(__doc__)
    return 2


def run_main(argv):
    """入口外面包一层：pythonw 下 stdout/stderr 都是空设备，任何未捕获的异常都要写进日志，不能无声消失（审查 N-09）。"""
    try:
        return main(argv)
    except Exception as e:
        import traceback
        try:
            log(f"! 看门狗异常退出：{type(e).__name__}: {e} ⏎ " + C.one_line(traceback.format_exc()[-1500:]))
        except Exception:
            pass
        _crash_notice()
        return 1


def _crash_notice():
    """pythonw 下崩溃没人看得见：常驻提醒一次（每天最多一次；记在状态文件旁的小文件里——状态文件本身可能就是坏的，复核 B-05）。"""
    try:
        mark, day = STATE_PATH + ".crash", f"{now_bj():%Y-%m-%d}"
        if os.path.isfile(mark) and C.read_text(mark).strip() == day:
            return
        C.atomic_write(mark, day + "\n")
        toast("提醒功能出错了", "巡检这一轮出错退出，弹窗和处理页可能停在旧状态。\n做法：" + C.need_how("doctor"), kind="watchdog")
    except Exception:
        pass


if __name__ == "__main__":
    C.stdio_safe()
    sys.exit(run_main(sys.argv[1:]))
