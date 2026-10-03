#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""弹窗与处理页（第十批）的回归测试：弹窗 XML 的转义与上限、按类别定常驻／静音／同类替换、出口兜底、传输层环境隔离、
ps1 演练（只在 Windows 上真跑，别处记 SKIP 不记 PASS）、处理页脚本与 CSP、出处链接白名单、拍板后当场刷新与撤销、
终端推翻负责人决定要 --confirm-held、新规矩一次最多简述三条、巡检心跳只认计划任务那一轮。临时目录，不弹窗、不碰注册表。"""
import io, os, re, sys, json, base64, hashlib, shutil, tempfile, platform, subprocess, importlib.util
import xml.etree.ElementTree as ET
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
for _k in [k for k in os.environ if k.upper().startswith(("HANDOFF_", "HN_", "HL_"))]:
    os.environ.pop(_k)  # 继承来的运行目录变量（HANDOFF_HOME 等）会压过下面的临时目录、让测试写进真目录（第十批打包干净检出时发现）
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
CANON = os.path.dirname(HERE)
ROOT = tempfile.mkdtemp(prefix="hu_")
DOCS = os.path.join(ROOT, "docs")
WT = os.path.join(DOCS, "工作传递")
os.makedirs(os.path.join(WT, "自我改进循环"))
T = os.path.join(WT, "协作教训.md")
VT = os.path.join(WT, "协作教训-否决记录.md")
CFG = os.path.join(ROOT, "config.json")
json.dump({"paths": {"docs_root": DOCS, "table": T}}, io.open(CFG, "w", encoding="utf-8"), ensure_ascii=False)
os.environ["HANDOFF_TOOLS_DIR"] = os.path.join(ROOT, "tools")
os.environ["HANDOFF_CONFIG"] = CFG
os.environ["HN_STATE_PATH"] = os.path.join(ROOT, "notify_state.json")
os.environ["HL_STATE_PATH"] = os.path.join(ROOT, "lessons_state.json")
os.environ["HN_LOG_PATH"] = os.path.join(ROOT, "log.txt")
os.environ["HANDOFF_NO_REGISTER"] = "1"
spec = importlib.util.spec_from_file_location("notify", os.path.join(CANON, "handoff_notify.py"))
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)
C = n.C
n.AUTO_PUBLISH = False
n.DECIDE_LOCK_WAIT = 0.5
n.task_last_result = lambda name: (None, None)
IS_WIN = platform.system() == "Windows"

sent, sent_meta = [], []
_real_send = n._send
n._send = lambda title, body, buttons=None, persistent=True, meta=None: (sent.append((title, body, buttons, persistent)),
                                                                           sent_meta.append(meta), True)[2]
results, skips = [], []
HDR = "现役\n\n| 编号 | 状态 | 一句话规矩 | 为什么 | 出处 |\n|---|---|---|---|---|\n"
VHDR = "现役\n\n| 编号 | 日期 | 谁 | 理由 |\n|---|---|---|---|\n"
NOW = datetime.now(timezone.utc)
BJ = n.BJ


def ok(name, cond):
    results.append((name, bool(cond)))
    print(("  PASS " if cond else "  FAIL ") + name)


def skip(name, why):
    skips.append(name)
    print(f"  SKIP {name}（{why}）")


def put(rows, veto_rows=(), updates=()):
    io.open(T, "w", encoding="utf-8", newline="\n").write(HDR + "\n".join(rows) + "\n\n## 更新记录\n\n" + "".join(u + "\n" for u in updates) + "- 建档\n")
    io.open(VT, "w", encoding="utf-8", newline="\n").write(VHDR + "".join(r + "\n" for r in veto_rows) + "\n## 更新记录\n\n- 建档\n")


def reset():
    for p in (os.environ["HN_STATE_PATH"], os.environ["HL_STATE_PATH"], n.POOL_PATH):
        if os.path.exists(p):
            os.remove(p)
    sent.clear()
    sent_meta.clear()


def added(hours_ago):
    return f"加入 {(NOW - timedelta(hours=hours_ago)).astimezone(BJ):%Y-%m-%d %H:%M}（自动）"


def page():
    return io.open(n.STATUS_PAGE, encoding="utf-8").read()


def parse(xml):
    try:
        return ET.fromstring(xml)
    except ET.ParseError:
        return None


print("== U1 弹窗 XML：一律转义、去掉 XML 不允许的字符、标题正文按钮有上限、总长 ≤4800 字节 ==")
evil = '标题<script>alert("x")</script>&\'"]]>\x00\x1b\ud800尾'
x = n.build_toast_xml(evil, "第一行 <b>&amp;</b>\x07\n第二行", [("看<看>", 'handoff-rule:ok/LG-01/abc"onload="x')], persistent=True)
r = parse(x)
ok("U1a 恶意标题／正文／按钮：XML 解析得了，原样文字回得来（尖括号与引号不会变成标签或属性）",
   r is not None and r.find("visual/binding/text").text.startswith('标题<script>alert("x")</script>&\'"]]>')
   and r.findall("actions/action")[0].get("arguments") == 'handoff-rule:ok/LG-01/abc"onload="x')
ok("U1a' 控制字符与孤立代理都去掉了（留着 Windows 那端 LoadXml 会失败、弹窗静默发不出）",
   r is not None and not re.search("[\x00-\x08\x0b\x0c\x0e-\x1f]", x) and "\ud800" not in x and "尾" in x)
x = n.build_toast_xml("长" * 100, "\n".join(f"第{i}行" + "字" * 80 for i in range(10)), None)
r = parse(x)
ts = r.findall("visual/binding/text") if r is not None else []
ok("U1b 标题 ≤60 字（带省略号）；正文最多 4 行、每行 ≤60 字；hint-maxLines=4",
   len(ts) >= 2 and len(ts[0].text) == 60 and ts[0].text.endswith("…") and ts[1].get("hint-maxLines") == "4"
   and len(ts[1].text.split("\n")) == 4 and all(len(ln) <= 60 for ln in ts[1].text.split("\n")))
x = n.build_toast_xml("t", "b", [("a", "u:1"), ("b", "u:2"), ("", "u:3"), ("c", ""), ("d", "u:4"), ("e", "u:5")])
acts = parse(x).findall("actions/action")
ok("U1c 按钮最多 3 个（空标签／空链接的丢掉），最后总有一个系统的「知道了」",
   [a.get("content") for a in acts] == ["a", "b", "d", "知道了"] and acts[-1].get("activationType") == "system"
   and all(a.get("activationType") == "protocol" for a in acts[:-1]))
x = n.build_toast_xml("t", "b", [("a", "u:1"), ("b", "u:2"), ("c", "u:3")], persistent=True, snooze=True)
r = parse(x)
ok("U1c' 开稍后提醒：自定义按钮 ≤2 个，带时长选择与系统的「稍后提醒」",
   r is not None and [a.get("content") for a in r.findall("actions/action")] == ["a", "b", "稍后提醒", "知道了"]
   and r.find("actions/input") is not None)
rp = parse(n.build_toast_xml("t", "b", None, persistent=True, launch="file:///C:/x.html#need"))
rq = parse(n.build_toast_xml("t", "b", None, persistent=False, silent=True))
ok("U1d 常驻＝reminder 场景、点正文按协议打开处理页；普通的不带场景；静音的带 <audio silent>",
   rp.get("scenario") == "reminder" and rp.get("launch") == "file:///C:/x.html#need" and rp.get("activationType") == "protocol"
   and rq.get("scenario") is None and rq.find("audio").get("silent") == "true" and rp.find("audio") is None)
fu = "file:///C:/Users/x/%E5%8D%8F%E4%BD%9C%E6%95%99%E8%AE%AD/handoff_status.html#need"
mid = n.build_toast_xml("题" * 60, "\n".join("字" * 60 for _ in range(4)), [("去处理", fu), ("看日志", fu), ("看表", fu)],
                        launch=fu, attribution="署" * 1200)
rm_ = parse(mid)
ok("U1e 署名行太长：先只去掉署名行，标题、4 行正文、3 个按钮都保住",
   len(mid.encode("utf-8")) <= 4800 and rm_ is not None and not any(t.get("placement") == "attribution" for t in rm_.iter("text"))
   and len(rm_.findall("visual/binding/text")[1].text.split("\n")) == 4 and len(rm_.findall("actions/action")) == 4)
big = n.build_toast_xml("题" * 60, "\n".join("字" * 60 for _ in range(4)), [("按钮", "handoff-rule:" + "x" * 1500)] * 3,
                        attribution="署" * 200)
rb = parse(big)
ok("U1e' 按钮链接离谱地长：上限照样是硬的（最后从后往前去按钮），仍是合法 XML、「知道了」还在",
   len(big.encode("utf-8")) <= 4800 and rb is not None and rb.findall("actions/action")[-1].get("content") == "知道了")

print("== U2 toast()：按类别定常驻／静音／同类替换／过期／点正文去哪一区；出口兜底挡内部词 ==")
sent.clear(); sent_meta.clear()
n.toast("需要你介入：x", "y", kind="need")
n.toast("知会一声", "y", kind="info")
n.toast("新学到 1 条规矩", "y", kind="live", tag="live-" + "a" * 80)
n.toast("好，看过了", "y", kind="receipt")
n.toast("t", "y", kind="不存在的类别")
m0, m1, m2, m3, m4 = sent_meta[:5]
ok("U2a need：常驻、出声、不过期、点正文到「要你做的事」、默认按钮「去处理」",
   sent[0][3] is True and m0["silent"] is False and m0["expire_min"] == 0 and m0["launch"].endswith("handoff_status.html#need")
   and m0["tag"] == "need" and m0["group"] == "handoff" and sent[0][2] == [("去处理", m0["launch"])])
ok("U2b info：普通、静音、24 小时后自动从通知中心消失、点正文到「系统自己在做的」、默认按钮「看处理页」",
   sent[1][3] is False and m1["silent"] is True and m1["expire_min"] == 1440 and m1["launch"].endswith("#auto")
   and sent[1][2] == [("看处理页", m1["launch"])])
ok("U2c live：同一批的新弹窗按 tag 替换旧的（tag ≤63 字）；回执 receipt 1 小时后消失、到「刚才的操作」",
   len(m2["tag"]) == 63 and m2["tag"].startswith("live-") and m3["expire_min"] == 60 and m3["launch"].endswith("#last"))
ok("U2d 不认识的类别按 info 处理（不会意外变成常驻）", sent[4][3] is False and m4["kind"] == "不存在的类别" and m4["expire_min"] == 1440)
ok("U2e 每条弹窗的 XML 都过得了解析，标题与正文就是交给系统的那份", all(parse(m["xml"]) is not None for m in sent_meta[:5]))
sent.clear(); sent_meta.clear(); n.SCRUB_HITS.clear()
n.toast("协作教训 · LG-12 否决了", "每日学习 RP-003 入池；HandoffDaily 失败（结果码 0xC000013A）；看门狗日志在 handoff_notify.py 旁；"
        "做法：handoffctl.py doctor", kind="info")
t_, b_ = sent[0][0], sent[0][1]
ok("U2f 出口兜底：内部编号、内部词、任务名、十六进制码都换成人话；应用名前缀去掉；体检命令原样保留",
   not t_.startswith("协作教训") and "LG-" not in t_ + b_ and "RP-" not in b_ and "否决" not in t_ + b_ and "每日学习" not in b_
   and "HandoffDaily" not in b_ and "0xC000013A" not in b_ and "看门狗" not in b_ and "handoff_notify.py" not in b_
   and "handoffctl.py doctor" in b_ and "不采纳" in t_)
ok("U2g 兜底命中会记下来（测试据此要求生产路径一次都不命中）", len(n.SCRUB_HITS) == 1)
n.SCRUB_HITS.clear()

print("== U3 传输层 _send：整段 XML 走环境变量；不继承父进程的 HN_* 与名字像密钥的变量；失败如实返回 False ==")
calls = []


class _R:
    def __init__(self, rc, err=""):
        self.returncode, self.stderr, self.stdout = rc, err, ""


_osys, _orun = n.platform.system, n.subprocess.run
os.environ["HN_DRYRUN_OUT"] = os.path.join(ROOT, "不该被带过去.xml")
os.environ["HN_TITLE"] = "父进程残留"
os.environ["GLM_API_KEY"] = "sk-test-not-a-real-key"
os.environ["ANTHROPIC_AUTH_TOKEN"] = "tok-test"
os.environ["GITHUB_PAT"] = "ghp_test"
os.environ["HTTPS_PROXY"] = "http://user:pw@proxy.invalid:8080"
try:
    n.platform.system = lambda: "Linux"
    n.subprocess.run = lambda *a, **k: (calls.append((a, k)), _R(0))[1]
    meta = {"kind": "info", "tag": "t" * 80, "group": "handoff", "expire_min": 1440, "silent": True, "suppress": False,
            "xml": n.build_toast_xml("标题", "正文")}
    r_lin = _real_send("标题", "正文", [], False, meta)
    ok("U3a 不是 Windows：直接返回 False（记「未送达」），不起子进程", r_lin is False and not calls)
    n.platform.system = lambda: "Windows"
    r_win = _real_send("标题含<尖括号>", "正文", [], False, meta)
    a0, k0 = calls[0] if calls else ((None,), {})
    env = k0.get("env") or {}
    ok("U3b Windows：XML 原样经 HN_XML 交过去；tag 截到 63 字、带 group 与过期分钟数；命令行里没有任何弹窗文字",
       r_win is True and env.get("HN_XML") == meta["xml"] and env.get("HN_TAG") == "t" * 63 and env.get("HN_GROUP") == "handoff"
       and env.get("HN_EXPIRE_MIN") == "1440" and "HN_SUPPRESS" not in env and not any("标题" in str(x) for x in a0[0]))
    ok("U3c 子进程环境是白名单：父进程的 HN_DRYRUN_OUT／HN_TITLE、GLM_API_KEY、*_AUTH_TOKEN、GITHUB_PAT、带口令的代理串都不带（复核 B-08）",
       "HN_DRYRUN_OUT" not in env and "HN_TITLE" not in env and "GLM_API_KEY" not in env and "ANTHROPIC_AUTH_TOKEN" not in env
       and "GITHUB_PAT" not in env and "HTTPS_PROXY" not in env and "PATH" in {k.upper() for k in env}
       and all(k.upper() in n._PS_ENV or k.startswith("HN_") for k in env))
    n.subprocess.run = lambda *a, **k: _R(1, "boom")
    ok("U3d powershell 非 0 退出：返回 False", _real_send("t", "b", [], False, meta) is False)

    def _raise(*a, **k):
        raise OSError("no powershell")
    n.subprocess.run = _raise
    ok("U3e 起不了子进程：返回 False、不抛异常", _real_send("t", "b", [], False, meta) is False)
finally:
    n.platform.system, n.subprocess.run = _osys, _orun
    for k in ("HN_DRYRUN_OUT", "HN_TITLE", "GLM_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GITHUB_PAT", "HTTPS_PROXY"):
        os.environ.pop(k, None)

print("== U4 ps1 演练（Windows 真跑 powershell 与 WinRT 的 XML 解析器；不弹窗）==")
PS1 = os.path.join(CANON, "handoff_toast.ps1")


def ps1(env_add):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("HN_")}
    env.update(env_add)
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", PS1],
                          env=env, capture_output=True, text=True, timeout=60)


def _winrt_ok():
    """这台机器的 Windows PowerShell 能不能加载 WinRT 的 XML 组件（CI 的 Windows 镜像不一定有）。"""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null; 'ok'"],
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 0 and "ok" in r.stdout
    except Exception:
        return False


raw = io.open(PS1, "rb").read()
ok("U4d ps1 仍是纯 ASCII（Windows PowerShell 5.1 按系统代码页读无 BOM 文件）", all(b < 128 for b in raw))
if not IS_WIN or not _winrt_ok():
    for nm in ("U4a", "U4b", "U4c"):
        skip(nm, "不是 Windows，或这台 Windows 加载不了 WinRT 通知组件")
else:
    out = os.path.join(ROOT, "dry.xml")
    sent.clear(); sent_meta.clear()
    n.toast("标题<script>&\"'", "正文\x00\x1b第一行\n第二行 & <b>", [("按钮\"<>", "handoff-rule:ok/LG-01/0123456789")], kind="need")
    xml0 = sent_meta[0]["xml"]
    _orun2 = n.subprocess.run

    def _dry(cmd, **kw):  # 走生产传输层（白名单环境），只在它交给 ps1 的环境上加演练开关
        kw["env"] = dict(kw.get("env") or {}, HN_DRYRUN_OUT=out)
        return _orun2(cmd, **kw)
    n.subprocess.run = _dry
    try:
        okd = _real_send("标题", "正文", [], True, sent_meta[0])
    finally:
        n.subprocess.run = _orun2
    ok("U4a 生产传输层（白名单环境）起的 powershell：Windows 自己的解析器认得生产 XML（含恶意字符），演练写出的就是这份",
       okd is True and os.path.isfile(out) and io.open(out, encoding="utf-8").read() == xml0)
    r = ps1({"HN_XML": "<toast><visual><binding template=\"ToastGeneric\"><text>坏</text></binding></visual>", "HN_DRYRUN_OUT": out + "2"})
    ok("U4b 坏 XML：演练也先解析一遍，退出码非 0、不写文件（上线前就能发现）", r.returncode != 0 and not os.path.exists(out + "2"))
    r = ps1({"HN_TITLE": "T<&>'\"", "HN_BODY": "第一行\n第二行", "HN_PERSIST": "1", "HN_BTN1_LABEL": "看", "HN_BTN1_ARG": "x:y?a=1&b=2",
             "HN_DRYRUN_OUT": out + "3"})
    golden = ('<toast scenario="reminder"><visual><binding template="ToastGeneric"><text>T&lt;&amp;&gt;&apos;&quot;</text>'
              '<text hint-maxLines="6">第一行\n第二行</text></binding></visual><actions>'
              '<action content="看" arguments="x:y?a=1&amp;b=2" activationType="protocol"/>'
              '<action content="OK" arguments="dismiss" activationType="system"/></actions></toast>')
    got = io.open(out + "3", encoding="utf-8").read() if os.path.isfile(out + "3") else None
    ok("U4c 不给 HN_XML 的老调用方（antd 周检等）：生成的 XML 与旧版逐字节一致", r.returncode == 0 and got == golden)

print("== U5 处理页：唯一一段脚本与 CSP 哈希对得上、没有内联事件；第一屏回答要不要你；规矩原文转义；出处链接只放行 docs 下实存 .md ==")
reset()
io.open(os.path.join(WT, "自我改进循环", "R1.md"), "w", encoding="utf-8").write("x")
io.open(os.path.join(WT, "自我改进循环", "R2.txt"), "w", encoding="utf-8").write("x")
io.open(os.path.join(ROOT, "外面.md"), "w", encoding="utf-8").write("x")
src = ("[R1](自我改进循环/R1.md)；[R2](自我改进循环/R2.txt)；[外](../../外面.md)；[JS](javascript:alert(1))；"
       "[缺](自我改进循环/没有.md)；" + added(1))
put(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |",
     f"| LG-02 | 生效（自动） | 别信<img src=x onerror=alert(1)>这种写法 | 为什么<b>粗</b> | {src} |"])
n.check(T, now_utc=NOW, task_present=False)
p = page()
scripts = re.findall(r"<script>(.*?)</script>", p, re.S)
csp = re.search(r"script-src 'sha256-([A-Za-z0-9+/=]+)'", p)
ok("U5a 只有一段脚本，就是固定常量；CSP 只放行它的哈希", len(scripts) == 1 and scripts[0] == n.PAGE_JS and csp
   and csp.group(1) == base64.b64encode(hashlib.sha256(scripts[0].encode("utf-8")).digest()).decode("ascii"))
ok("U5b 没有内联事件处理器、没有 javascript: 链接；CSP 默认全拒", not re.search(r"<[^>]+\son[a-z]+\s*=", p, re.I)
   and "javascript:" not in p.lower().replace("[js](javascript:", "") and "default-src 'none'" in p)
ok("U5c 规矩原文与「为什么」里的尖括号被转义（不会变成图片或粗体）", "&lt;img src=x onerror=alert(1)&gt;" in p and "<img" not in p
   and "&lt;b&gt;粗&lt;/b&gt;" in p)
ok("U5d 出处：docs 下实存的 .md 给链接；非 .md、跑出 docs、带协议的都不给链接；找不到的写明",
   re.search(r'<a href="file:///[^"]*R1\.md">R1</a>', p) and "R2（文件不在允许范围）" in p and "外（文件不在允许范围）" in p
   and "JS（文件不在允许范围）" in p and "缺（找不到文件）" in p and 'href="javascript' not in p)
ok("U5e 第一屏：没有要你做的事时说「现在不需要你」，并提示最近有新规矩生效", 'id="now" class="banner ok"' in p
   and "现在不需要你" in p and "最近有 1 条新规矩已经生效" in p)
ok("U5f 各区锚点都在（弹窗点正文直达）", all(f'id="{a}"' in p for a in ("now", "need", "recent", "auto", "links")))
put(["| LG-01 | 待定 | 规矩一 | 事一 | 源 |"])
sent.clear()
n.check(T, now_utc=NOW + timedelta(minutes=5), task_present=False)
p = page()
ok("U5g 有要你做的事：横幅说「要你做 N 件事」，「要你做的事」区列着、附做法与可整段复制的那句话",
   'class="banner warn"' in p and "要你做 1 件事" in p and re.search(r'<div class="card fault"><div class="rule">教训表里有 1 处程序认不出', p)
   and "做法：把下面这句话贴给任一 AI 窗口：" in p and '<span class="say">' in p)
ok("U5h 对应的弹窗：常驻、标题「需要你介入」、正文带做法、不出现内部编号", len(sent) == 1 and sent[0][3] is True
   and "需要你介入" in sent[0][0] and "做法：" in sent[0][1] and "LG-" not in sent[0][1])

print("== U6 拍板后当场重写处理页：顶部「刚才的操作」带撤销按钮；点撤销能恢复；磁盘上的这条记录不会被巡检冲掉 ==")
reset()
put(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |", f"| LG-02 | 生效（自动） | 规矩二 | 事二 | {added(1)} |"])
n.check(T, now_utc=NOW, task_present=False)
tk = re.search(r"handoff-rule:no/LG-02/([0-9a-f]{10})", page())
rc = n.decide(f"handoff-rule:no/LG-02/{tk.group(1)}" if tk else "no/LG-02/0000000000", T)
p = page()
ub = re.search(r"handoff-rule:unveto/LG-02/([0-9a-f]{10})", p)
ok("U6a 点「不采纳」：返回 0、否决记录有了这条；处理页当场重写，顶部写着刚才做了什么、带「撤销」",
   rc == 0 and "| LG-02 |" in io.open(VT, encoding="utf-8").read() and 'id="last"' in p and "不采纳了" in p and ub
   and "撤销" in p)
st = json.load(io.open(os.environ["HN_STATE_PATH"], encoding="utf-8"))
ok("U6b 状态里记了最近一次拍板（谁、做了什么、怎么撤）", (st.get("last_decide") or {}).get("oid") == "LG-02"
   and st["last_decide"].get("undo") == ["unveto", "LG-02"])
rc2 = n.decide(f"handoff-rule:unveto/LG-02/{ub.group(1)}" if ub else "unveto/LG-02/0000000000", T)
p = page()
ok("U6c 点「撤销」：否决记录里那行删掉、状态恢复，顶部改成「恢复了」",
   rc2 == 0 and "| LG-02 |" not in io.open(VT, encoding="utf-8").read() and "恢复了" in p)
stale_mem = dict(st)
stale_mem["last_decide"] = {"oid": "LG-99", "act": "ok", "ms": 1}
n.merge_save_state(stale_mem)
ok("U6d 巡检手里是拍板之前读的旧状态：落盘时以磁盘上的「刚才的操作」为准",
   json.load(io.open(os.environ["HN_STATE_PATH"], encoding="utf-8")).get("last_decide", {}).get("act") == "unveto")
sent.clear()
rc3 = n.decide("handoff-rule:ok/LG-02/0000000000", T)
ok("U6e 口令不对：不改任何东西、返回非 0，弹一条说明", rc3 != 0 and len(sent) == 1 and sent[0][3] is False)

print("== U7 终端推翻负责人的决定（恢复不采纳、恢复不用）要显式 --confirm-held；处理页带口令的按钮不需要 ==")
reset()
put(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |", "| LG-03 | 否决（见否决记录；原：生效） | 规矩三 | 事三 | 源 |"],
    veto_rows=[f"| LG-03 | {NOW.astimezone(BJ):%Y-%m-%d} | 负责人 | 不要 |"])
v0 = io.open(VT, encoding="utf-8").read()
rc = n.decide("unveto/LG-03", T, require_token=False, allow_held=False)
ok("U7a 终端 unveto 不加 --confirm-held：返回 2、否决记录一个字不变", rc == 2 and io.open(VT, encoding="utf-8").read() == v0)
rc = n.decide("unveto/LG-03", T, require_token=False, allow_held=True)
ok("U7b 加了：恢复成功，状态格回到原状态", rc == 0 and "| LG-03 |" not in io.open(VT, encoding="utf-8").read()
   and "| LG-03 | 生效 |" in io.open(T, encoding="utf-8").read())
json.dump({"items": [{"id": "RP-005", "rule": "交付前把复跑命令写进报告", "why": "w", "category": "其他", "reason": "当天配额满",
                      "status": "ignored", "decided": f"{NOW.astimezone(BJ):%Y-%m-%d %H:%M}"}]},
          io.open(n.POOL_PATH, "w", encoding="utf-8"), ensure_ascii=False)
n.check(T, now_utc=NOW, task_present=False)
p = page()
ok("U7c 处理页「最近撤下的」列着点过「不用」的候选，只给「恢复为候选」", re.search(r"handoff-rule:undrop/RP-005/[0-9a-f]{10}", p)
   and not re.search(r"(?<!un)drop/RP-005/", p))
rc = n.decide("undrop/RP-005", T, require_token=False, allow_held=False)
ok("U7d 终端 undrop 不加 --confirm-held：返回 2、池里不变",
   rc == 2 and json.load(io.open(n.POOL_PATH, encoding="utf-8"))["items"][0]["status"] == "ignored")
tk = re.search(r"handoff-rule:undrop/RP-005/([0-9a-f]{10})", p)
rc = n.decide(f"handoff-rule:undrop/RP-005/{tk.group(1)}" if tk else "x", T)
ent = json.load(io.open(n.POOL_PATH, encoding="utf-8"))["items"][0]
ok("U7e 处理页按钮（带口令）：恢复为候选、记下谁什么时候恢复的", rc == 0 and ent["status"] == "pending" and ent.get("restored"))

print("== U8 新规矩一次最多简述三条：只给真说到了的记「已简述」，其余下一轮说，每条恰好说一次 ==")
reset()
put(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |"] + [f"| LG-0{i} | 生效（自动） | 新规矩{i} | 事 | {added(1)} |" for i in range(2, 7)])
n.check(T, now_utc=NOW, task_present=False)
s1 = list(sent)
st = json.load(io.open(os.environ["HN_STATE_PATH"], encoding="utf-8"))
told = sorted(k for k in st.get("notified", {}) if k.startswith("live:"))
ok("U8a 第一轮：一条静音弹窗，标题说共 5 条，正文列 3 条、写明其余下次再说；只给这 3 条记了已简述",
   len(s1) == 1 and s1[0][3] is False and "新学到 5 条规矩" in s1[0][0] and s1[0][1].count("· ") == 3
   and "其余下次再说" in s1[0][1] and told == ["live:LG-02", "live:LG-03", "live:LG-04"])
sent.clear()
n.check(T, now_utc=NOW + timedelta(hours=4), task_present=False)
s2 = list(sent)
ok("U8b 第二轮：剩下 2 条", len(s2) == 1 and "新学到 2 条规矩" in s2[0][0] and "新规矩5" in s2[0][1] and "新规矩6" in s2[0][1]
   and "新规矩2" not in s2[0][1])
sent.clear()
n.check(T, now_utc=NOW + timedelta(hours=8), task_present=False)
ok("U8c 第三轮：没有新的就不弹", not any("新学到" in s[0] for s in sent))

print("== U9 表满了每周只说一次（按 ISO 周）；两个计划任务各自偶发一次没跑成：普通告知，不常驻 ==")
reset()
put(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |"])
mon = (NOW.astimezone(BJ) - timedelta(days=NOW.astimezone(BJ).weekday())).replace(hour=10, minute=0, second=0, microsecond=0)
for i, dt in enumerate((mon, mon + timedelta(days=2), mon + timedelta(days=7))):
    json.dump({"cap": {"full": True, "at": f"{dt:%Y-%m-%d %H:%M}", "total_cap": 40, "waiting": 3},
               "last_scan_utc": dt.astimezone(timezone.utc).isoformat(), "last_run": {"utc": dt.astimezone(timezone.utc).isoformat(), "rc": 0}},
              io.open(os.environ["HL_STATE_PATH"], "w", encoding="utf-8"))
    sent.clear()
    n.check(T, now_utc=dt.astimezone(timezone.utc) + timedelta(minutes=5), task_present=True)
    said = [s for s in sent if "教训表满了" in s[1]]
    if i == 0:
        ok("U9a 本周第一次：普通告知（不常驻）", len(said) == 1 and said[0][3] is False)
    elif i == 1:
        ok("U9b 同一周再满：不重复", not said)
    else:
        ok("U9c 下一周还满：再说一次", len(said) == 1)
iso = (mon + timedelta(days=7)).isocalendar()
ok("U9d 记录键用 ISO 周（跨平台一致，不依赖 C 库的 %G/%V）",
   f"capfull:{iso[0]}-W{iso[1]:02d}" in json.load(io.open(os.environ["HN_STATE_PATH"], encoding="utf-8")).get("notified", {}))

print("== U10 巡检心跳只认计划任务那一轮：每日学习跑完顺带的那轮不冒充（看门狗、status、doctor 同一处）==")
ok("U10a 只有顺带的那轮：算没有心跳", C.task_heartbeat({"last_check": {"utc": "x", "source": "daily"}}) == {})
ok("U10b 旧状态没有 source：照旧认", C.task_heartbeat({"last_check": {"utc": "x"}}) == {"utc": "x"})
ok("U10c 两样都有：认计划任务那一轮", C.task_heartbeat({"last_task_check": {"utc": "a"}, "last_check": {"utc": "b", "source": "daily"}})
   == {"utc": "a"})
reset()
put(["| LG-01 | 生效 | 规矩一 | 事一 | 源 |"])
n.check(T, now_utc=NOW, task_present=False, source="task")
n.check(T, now_utc=NOW + timedelta(hours=1), task_present=False, source="daily")
st = json.load(io.open(os.environ["HN_STATE_PATH"], encoding="utf-8"))
ok("U10d check(source=daily) 只刷新 last_check，不动计划任务那一轮的心跳",
   st["last_check"]["source"] == "daily" and st["last_task_check"]["utc"] == NOW.isoformat()
   and C.task_heartbeat(st)["utc"] == NOW.isoformat())

print("== U12 分档：每一类造一次触发，断言弹窗类别与常驻与否（复核 D-07）==")
import types
TODAY = f"{NOW.astimezone(BJ):%Y-%m-%d}"
BASE = ["| LG-01 | 生效 | 规矩一 | 事一 | 源 |"]
n.task_exists = lambda: False  # 走入口（run_main）的用例不去查真机的计划任务


def lstate(d):
    json.dump(d, io.open(os.environ["HL_STATE_PATH"], "w", encoding="utf-8"), ensure_ascii=False)


def nstate(d):
    json.dump(d, io.open(os.environ["HN_STATE_PATH"], "w", encoding="utf-8"), ensure_ascii=False)


def nload():
    return json.load(io.open(os.environ["HN_STATE_PATH"], encoding="utf-8"))


def hit(text):
    return [(s_, m_) for s_, m_ in zip(sent, sent_meta) if text in (s_[1] or "") or text in (s_[0] or "")]


def _patch(obj, attr, val):
    old = getattr(obj, attr)
    setattr(obj, attr, val)
    return lambda: setattr(obj, attr, old)


def _both(*undos):
    return lambda: [u() for u in undos]


def tier(name, prep, kw, text, kind, persistent):
    reset()
    put(BASE)
    undo = prep()
    try:
        n.check(T, now_utc=NOW, **kw)
    finally:
        if callable(undo):
            undo()
    h = hit(text)
    ok(f"U12 {name}：{'常驻' if persistent else '不常驻'}、类别 {kind}", bool(h) and h[0][1]["kind"] == kind and h[0][0][3] is persistent)


def _timeout(*a, **k):
    raise subprocess.TimeoutExpired("handoff_flow.py", 180)


def _pool_held():
    json.dump({"items": [{"id": "RP-007", "rule": "写报告前先跑 `git status` 自查", "why": "w", "category": "其他",
                          "reason": "证据不足", "evidence": [], "date": TODAY, "status": "pending"}]},
              io.open(n.POOL_PATH, "w", encoding="utf-8"), ensure_ascii=False)


H = lambda h: (NOW - timedelta(hours=h)).isoformat()
tier("生效版刷新不了（pubfail）", lambda: _patch(n, "ensure_published", lambda t, st=None: (True, "生效版连续 3 轮刷新不了")),
     {"task_present": False}, "AI 读的那份规矩没能刷新", "need", True)
tier("写后检查清单写不出来（todo_fail）", lambda: _both(_patch(n, "scan_problems", lambda root, hours, cap=None: []),
                                                _patch(n, "_gate", lambda: types.SimpleNamespace(TODO_NAME="t.md", todo_md=lambda *a, **k: False))),
     {"task_present": False, "scan_root": WT}, "待处理清单写不出来", "need", True)
tier("规范扫描超时（flowerr；复核 A-07：以前超时只记日志）", lambda: _patch(n.subprocess, "run", _timeout),
     {"task_present": False, "flow_root": DOCS}, "规范扫描这一轮没跑成", "need", True)
tier("连续 36 小时没成功（stale）", lambda: lstate({"last_scan_utc": H(40), "last_run": {"utc": H(40), "rc": 0}}),
     {"task_present": True}, "没有成功运行", "need", True)
tier("开跑后没跑完（dailykilled）", lambda: lstate({"last_scan_utc": H(20), "last_run": {"utc": H(20), "rc": 0},
                                              "last_start": {"utc": H(3), "pid": 4999999}}),
     {"task_present": True}, "开跑后没跑完", "info", False)
tier("待读积压超过 60 件（backlog）", lambda: lstate({"last_scan_utc": H(2), "pending": [f"r{i}" for i in range(70)]}),
     {"task_present": True}, "积压 70 件", "info", False)
tier("同一窗口一天 3 份没过写后检查（esc）",
     lambda: nstate({"notified": {f"scan:a{i}.md:1": f"{TODAY} 00:0{i} 已列入待处理清单 @某窗口" for i in range(3)}}),
     {"task_present": False, "scan_root": WT}, "这个窗口今天 3 份报告", "info", False)
tier("碰到敏感形态的候选（hold）", _pool_held, {"task_present": False}, "候选没自动生效", "hold", False)
sent.clear(); sent_meta.clear()
n.toast("t", "b", kind="hold")
ok("U12z hold 类 24 小时后从通知中心消失（复核 D-14：以前用系统默认的 3 天）", sent_meta[-1]["expire_min"] == 1440)

print("== U13 出处里的 UNC／盘符／绝对路径：不碰文件系统就拒（复核 B-01：连不上让巡检整轮崩，实测；对端是恶意主机时还可能带出本机凭据，推断、未抓包）==")
import time as _tm
_evil = ["//192.0.2.1/s/x.md", "\\\\192.0.2.1\\s\\x.md", "%5C%5C192.0.2.1%5Cs%5Cx.md", "%2F%2F192.0.2.1%2Fs%2Fx.md",
         "\\\\?\\UNC\\192.0.2.1\\s\\x.md", "C:x.md", "/etc/x.md", "file:x.md",
         "\\??\\UNC\\192.0.2.1\\s\\x.md", "%5C%3F%3F%5CUNC%5C192.0.2.1%5Cs%5Cx.md"]  # NT 直通前缀（复核 RA-1）
_t0 = _tm.time()
_res = [n._safe_md(r_, WT)[1] for r_ in _evil]
ok("U13a 十种写法都判「不在允许范围」，而且没有去连网络（全部加起来 < 0.5 秒）",
   all(x == "文件不在允许范围" for x in _res) and _tm.time() - _t0 < 0.5)
reset()
put(BASE + [f"| LG-02 | 生效（自动） | 报告里的数字要带出处 | 事二 | [r](//192.0.2.1/s/x.md)；{added(1)} |"])
_t1 = _tm.time()
_rc = n.run_main(["check", T])
ok("U13b 表里有这样一行：巡检照常（入口返回 0、页面写出、心跳落盘、没有去连网络）",
   _rc == 0 and "r（文件不在允许范围）" in page() and bool(nload().get("last_task_check")) and _tm.time() - _t1 < 5)

print("== U14 状态文件里字段类型不对：巡检照常、心跳落盘；入口真崩了常驻提醒一次（复核 B-05）==")
n.task_exists = lambda: True
for _i, _bad in enumerate([{"acts": 5}, {"acts": [{"ms": "x", "oid": "LG-01", "act": "no"}]}, {"last_decide": ["ok"]},
                           {"last_decide": {"ms": "abc", "undo": 5}}, {"notified": []}, {"agreed": "LG-01"}, {"veto_seen": 3},
                           {"attempts": "x"}, {"first_seen_utc": "不是时间"}]):
    reset()
    put(BASE)
    nstate(dict(_bad, page_secret="ab" * 16))  # 生产形态：有口令种子（复核 R2-2-3）
    _rc = n.run_main(["check", T])
    ok(f"U14{chr(97 + _i)} 巡检状态里 {json.dumps(_bad, ensure_ascii=False)[:40]}：返回 0、心跳落盘",
       _rc == 0 and bool(nload().get("last_task_check")))
for _i, _bad in enumerate([{"untrusted": [1]}, {"cap": [1]}, {"pending": 3}, {"ext_trusted": ["x"]}, {"last_run": [1]},
                           {"last_start": 5}]):
    reset()
    put(BASE)
    lstate(_bad)
    _rc = n.run_main(["check", T])
    ok(f"U14{chr(106 + _i)} 学习状态里 {json.dumps(_bad, ensure_ascii=False)[:40]}：返回 0、心跳落盘",
       _rc == 0 and bool(nload().get("last_task_check")))
n.task_exists = lambda: False
sent.clear(); sent_meta.clear()
for _ in range(2):
    n.run_main(["check", os.path.join(ROOT, "没有这张表.md")])
_w = [s_ for s_, m_ in zip(sent, sent_meta) if m_ and m_["kind"] == "watchdog"]
ok("U14z 入口崩了：常驻提醒一次、写明做法；同一天第二次不再弹", len(_w) == 1 and _w[0][3] is True and "doctor" in _w[0][1])

print("== U15 不采纳记录的变化：送达才记账；恢复后别处再否决要说；别处删掉要说；负责人自己恢复不说；终端替你做的要说 ==")
ROWS = BASE + [f"| LG-03 | 生效（自动） | 规矩三 | 事三 | {added(1)} |"]
VROW = f"| LG-03 | {TODAY} | 别的机器 | 不要 |"
reset()
put(ROWS)
n.check(T, now_utc=NOW, task_present=False)
put(ROWS + [f"| LG-04 | 生效（自动） | 规矩四 | 事四 | {added(1)} |"], veto_rows=[VROW])
sent.clear(); sent_meta.clear()
n.check(T, now_utc=NOW + timedelta(hours=1), task_present=False)
_r1 = list(sent)
sent.clear(); sent_meta.clear()
n.check(T, now_utc=NOW + timedelta(hours=5), task_present=False)
ok("U15a 同一轮有新规矩简述：不采纳记录的变化这一轮没挤进去，下一轮照说（复核 A-01：以前当轮就记账，再也不说）",
   any("新学到" in s_[0] for s_ in _r1) and not any("不采纳记录里多了" in s_[1] for s_ in _r1)
   and any("不采纳记录里多了 1 条" in s_[1] for s_ in sent))
sent.clear()
n.check(T, now_utc=NOW + timedelta(hours=9), task_present=False)
ok("U15b 说过就记账：不再重复", not any("不采纳记录里多了" in s_[1] for s_ in sent))
reset()
put(ROWS)
n.check(T, now_utc=NOW, task_present=False)
put(ROWS, veto_rows=[VROW])
_sendok = n._send
n._send = lambda *a, **k: (sent.append((a[0], a[1], None, False)), False)[1]
sent.clear()
try:
    for _h in (1, 5, 9):
        n.check(T, now_utc=NOW + timedelta(hours=_h), task_present=False)
finally:
    n._send = _sendok
ok("U15c 没送达：每轮重试，第三次放弃后才记账", sum(1 for s_ in sent if "不采纳记录里多了" in s_[1]) == 3
   and "LG-03" in nload().get("veto_seen", []))
reset()
put(ROWS)
n.check(T, now_utc=NOW, task_present=False)
_tk = re.search(r"handoff-rule:no/LG-03/([0-9a-f]{10})", page())
n.decide(f"handoff-rule:no/LG-03/{_tk.group(1) if _tk else 'x'}", T)
_ub = re.search(r"handoff-rule:unveto/LG-03/([0-9a-f]{10})", page())
_rcu = n.decide(f"handoff-rule:unveto/LG-03/{_ub.group(1) if _ub else 'x'}", T)
sent.clear()
n.check(T, now_utc=NOW + timedelta(hours=1), task_present=False)
ok("U15d 处理页「不采纳」再「撤销」：编号移出 veto_seen；下一轮什么都不说（复核 A-02、C-03）",
   _rcu == 0 and "LG-03" not in nload().get("veto_seen", []) and not any("不采纳记录" in s_[1] for s_ in sent))
put(ROWS, veto_rows=[f"| LG-03 | {TODAY} | 别的机器 | 还是不要 |"])
sent.clear()
n.check(T, now_utc=NOW + timedelta(hours=2), task_present=False)
ok("U15e 负责人恢复之后，别处又把它写进不采纳：照样告知（以前 veto_seen 只增不减，认不出来）",
   any("不采纳记录里多了 1 条" in s_[1] for s_ in sent))
reset()
put(ROWS, veto_rows=[VROW])
n.check(T, now_utc=NOW, task_present=False)
put(ROWS)
sent.clear()
n.check(T, now_utc=NOW + timedelta(hours=2), task_present=False)
n.check(T, now_utc=NOW + timedelta(hours=6), task_present=False)  # 同一轮有"新学到"简述时告知类等下一轮（A-01 的规矩）
ok("U15f 别处把不采纳删掉了：告知「少了 1 条」，只说一次（复核 A-02：以前全程无声）",
   sum(1 for s_ in sent if "不采纳记录里少了 1 条" in s_[1]) == 1)
reset()
put(ROWS)
n.check(T, now_utc=NOW, task_present=False)
n.decide("no/LG-03", T, require_token=False, reason="终端试一下", allow_held=False)
sent.clear()
n.check(T, now_utc=NOW + timedelta(hours=2), task_present=False)
_r2 = list(sent)
sent.clear()
n.check(T, now_utc=NOW + timedelta(hours=6), task_present=False)
ok("U15g 终端里替负责人点了不采纳：下一轮告知一次，只说一次（复核 B-04：终端那边没有回执）",
   any("终端里有人不采纳了「" in s_[1] for s_ in _r2) and not any("终端里有人" in s_[1] for s_ in sent))

print("== U16 终端「看过了」要 --confirm-held、记成终端标的（复核 B-03）==")
reset()
put(BASE + [f"| LG-02 | 生效（自动） | 规矩二 | 事二 | {added(1)} |"])
n.check(T, now_utc=NOW, task_present=False)
_rc = n.decide("ok/LG-02", T, require_token=False, allow_held=False)
ok("U16a 终端「看过了」不加 --confirm-held：拒绝、不记", _rc == 2 and "LG-02" not in (nload().get("agreed") or {}))
_rc = n.decide("ok/LG-02", T, require_token=False, allow_held=True)
ok("U16b 加了：记成终端标的，处理页写「终端标记看过（…，未核实是谁）」",
   _rc == 0 and str((nload().get("agreed") or {}).get("LG-02", "")).endswith(" 终端") and "终端标记看过" in page())

print("== U17 表外敏感规矩：确认生效后第一屏当场变；恢复后回执照实说还差确认（复核 A-04、A-05、D-10）==")
_L9 = "| LG-09 | 生效 | 部署前先问负责人 | 别处加的 | 别处 |"
_U9 = {"untrusted": {"LG-09": {"rule": "部署前先问负责人", "reasons": "越界话题", "since": TODAY, "hash": "h1"}},
       "ledger": {"LG-01": n._lessons().rule_hash("规矩一")}}  # 本机账本里有 LG-01、没有 LG-09（别处加进来的）
reset()
put(BASE + [_L9])
lstate(_U9)
n.check(T, now_utc=NOW, task_present=False)
_p = page()
_tk = re.search(r"handoff-rule:trust/LG-09/([0-9a-f]{10})", _p)
ok("U17 前提：被扣下时第一屏是「要你做 1 件事」", 'class="banner warn"' in _p and bool(_tk))
_rc = n.decide(f"handoff-rule:trust/LG-09/{_tk.group(1) if _tk else 'x'}", T)
ok("U17a 处理页「确认生效」之后：第一屏当场变成「现在不需要你」（以前沿用上一轮的缓存，最长 4 小时自相矛盾）",
   _rc == 0 and 'class="banner ok"' in page())
reset()
put(BASE + [_L9])
lstate(_U9)
n.check(T, now_utc=NOW, task_present=False)
_tk = re.search(r"handoff-rule:no/LG-09/([0-9a-f]{10})", page())
n.decide(f"handoff-rule:no/LG-09/{_tk.group(1) if _tk else 'x'}", T)
n.check(T, now_utc=NOW + timedelta(hours=1), task_present=False)
_ub = re.search(r'id="v-LG-09".*?handoff-rule:unveto/LG-09/([0-9a-f]{10})', page(), re.S)
sent.clear()
_rc = n.decide(f"handoff-rule:unveto/LG-09/{_ub.group(1) if _ub else 'x'}", T)
ok("U17b 「最近 30 天撤下的」卡片上的「恢复」按钮能用", bool(_ub) and _rc == 0)
ok("U17c 恢复的是别处加进来、碰到敏感话题的规矩：回执照实说还差你确认；第一屏当场变回「要你做」",
   bool(sent) and sent[0][0] == "恢复了，还差你确认一下" and 'class="banner warn"' in page())

print("== U18 已经要你介入时：文案自洽（复核 A-06）==")
reset()
put(BASE)
lstate({"last_scan_utc": H(40), "last_run": {"utc": H(40), "rc": 0}, "last_start": {"utc": H(3), "pid": 4999999}})
n.check(T, now_utc=NOW, task_present=True)
_h = hit("开跑后没跑完")
ok("U18a 连续没成功＋开跑后没跑完：常驻弹窗里不缀「下一轮会自动补上」", bool(_h) and _h[0][0][3] is True
   and "下一轮会自动补上" not in _h[0][0][1])
lstate({"last_scan_utc": H(40), "last_run": {"utc": H(-1), "rc": 3, "error": "模型接口超时"}})
sent.clear(); sent_meta.clear()
n.check(T, now_utc=NOW + timedelta(hours=2), task_present=True)
_h = hit("自动学习上次运行出错")
ok("U18b 要你做的事还没解决：告知类弹窗的标题不说「不用你做事」", bool(_h) and "不用你做事" not in _h[0][0][0])

print("== U19 认不出的结果码：弹窗说人话、不带数字码（复核 A-08）==")
reset()
put(BASE)
_undo = _patch(n, "task_last_result", lambda name: (2147942401, "北京 10-02 09:00"))
try:
    n.check(T, now_utc=NOW, task_present=True)
finally:
    _undo()
_h = hit("这一轮没跑成")
ok("U19 正文写「没见过的结果码」，不出现十进制或十六进制码（码只进日志）", bool(_h) and "没见过的结果码" in _h[0][0][1]
   and "2147942401" not in _h[0][0][1] and "0x" not in _h[0][0][1])

print("== U20 不采纳记录写不进去：回执不拼异常原文、不带本机路径（复核 A-09）==")
reset()
put(BASE + [f"| LG-02 | 生效（自动） | 规矩二 | 事二 | {added(1)} |"])
n.check(T, now_utc=NOW, task_present=False)
_tk = re.search(r"handoff-rule:no/LG-02/([0-9a-f]{10})", page())


def _deny(*a, **k):
    raise PermissionError(13, "拒绝访问", "C:\\Users\\someone\\docs\\协作教训-否决记录.md")


_undo = _patch(n.C, "atomic_write", _deny)
sent.clear()
try:
    _rc = n.decide(f"handoff-rule:no/LG-02/{_tk.group(1) if _tk else 'x'}", T)
finally:
    _undo()
ok("U20 返回 2；回执「不采纳没写成」不含路径与异常原文", _rc == 2 and bool(sent) and sent[0][0] == "不采纳没写成"
   and ":\\" not in sent[0][1] and "拒绝访问" not in sent[0][1])

print("== U21 已不采纳的手写老格式行：不再列成快到点、也不告知（复核 A-11）==")
reset()
_due = (NOW + timedelta(days=2)).astimezone(BJ)
put(BASE + [f"| LG-05 | 拟生效（至 {_due:%Y-%m-%d %H:%M}） | 手写规矩五 | 事 | 源；加入 {(NOW - timedelta(days=1)).astimezone(BJ):%Y-%m-%d %H:%M}（人工） |"],
    veto_rows=[f"| LG-05 | {TODAY} | 负责人 | 不要 |"])
sent.clear(); sent_meta.clear()
n.check(T, now_utc=NOW, task_present=False)
ok("U21 页面「撤下的」之前没有它；弹窗里也没有", "手写规矩五" not in page().split('id="vetoed"')[0] and not hit("手写规矩五"))

print("== U22 巡检跑着的时候负责人点了按钮：这一轮写出的页面按点完的样子（复核 A-12）==")
reset()
put(BASE + [f"| LG-02 | 生效（自动） | 规矩二 | 事二 | {added(1)} |"])
n.check(T, now_utc=NOW, task_present=False)
_tk = re.search(r"handoff-rule:ok/LG-02/([0-9a-f]{10})", page())


def _mid(root, hours, cap=None):
    n.decide(f"handoff-rule:ok/LG-02/{_tk.group(1) if _tk else 'x'}", T)
    return []


_undo = _patch(n, "scan_problems", _mid)
try:
    n.check(T, now_utc=NOW + timedelta(minutes=1), task_present=False, scan_root=WT)
finally:
    _undo()
_p = page()
ok("U22 页面顶部有「刚才的操作」，那条标「你看过了」", 'id="last"' in _p and "你看过了" in _p)

print("== U23 处理页写计划任务那一轮巡检的时刻，超过 9 小时标红（复核 D-02）==")
reset()
put(BASE)
n.check(T, now_utc=NOW - timedelta(hours=50), task_present=False, source="task")
n.check(T, now_utc=NOW, task_present=False, source="daily")
_p = page()
ok("U23 「本页生成」被顺带那轮刷新了，但「巡检上次按计划运行」仍是 50 小时前、标红",
   "巡检上次按计划运行 <b" in _p and f"{(NOW - timedelta(hours=50)).astimezone(BJ):%m-%d %H:%M}" in _p and "超过 9 小时了" in _p)

print("== U24 「最近 30 天撤下的」：只列 30 天内的；系统按近似标成不用的候选不给恢复（复核 D-10）==")
reset()
put(BASE + ["| LG-03 | 否决（见否决记录；原：生效） | 规矩三 | 事 | 源 |", "| LG-04 | 否决（见否决记录；原：生效） | 规矩四 | 事 | 源 |"],
    veto_rows=[f"| LG-03 | {(NOW - timedelta(days=40)).astimezone(BJ):%Y-%m-%d} | 负责人 | 旧 |", f"| LG-04 | {TODAY} | 负责人 | 新 |"])
json.dump({"items": [{"id": "RP-008", "rule": "与负责人不用过的那条近似", "status": "ignored", "note": "与负责人不用过的 RP-001 近似",
                      "decided": f"{TODAY} 08:00"}]}, io.open(n.POOL_PATH, "w", encoding="utf-8"), ensure_ascii=False)
n.check(T, now_utc=NOW, task_present=False)
_p = page()
ok("U24a 40 天前那条不列、今天那条列着", 'id="v-LG-04"' in _p and 'id="v-LG-03"' not in _p)
ok("U24b 系统标的「不用」：页面不给「恢复为候选」，终端加了 --confirm-held 也恢复不了", "undrop/RP-008" not in _p
   and n.decide("undrop/RP-008", T, require_token=False, allow_held=True) == 2)

print("== U25 负责人看过的手写行到点转生效：不算进告知（复核 D-11）==")
reset()
put(BASE, updates=[f"- {TODAY} 09:08：LG-07、LG-08 自动处理（否决记录同步／撤销否决恢复／遗留拟生效到期转生效）。（handoff_lessons.py）"])
nstate({"agreed": {"LG-07": f"{TODAY} 08:00"}})
sent.clear(); sent_meta.clear()
n.check(T, now_utc=NOW, task_present=False)
ok("U25 只说 1 条（LG-08）", bool(hit("自动处理：1 条手写的规矩到点转成生效了")))

print("== U26 另一轮巡检正在跑：这一轮跳过（复核 D-13）==")
reset()
put(BASE)
_lk = n.C.Lock(n.STATE_PATH + ".check.lock", stale_sec=600)
_lk.acquire(1)
sent.clear()
try:
    _rc = n.check(T, now_utc=NOW, task_present=False)
finally:
    _lk.release()
ok("U26 返回 0、不弹窗、日志写明跳过", _rc == 0 and not sent and "本轮跳过" in io.open(os.environ["HN_LOG_PATH"], encoding="utf-8").read())

print("== U27 找不到条目的点击：没口令的只记日志；带口令的同一小时最多弹 3 次（复核 B-02）==")
reset()
put(BASE)
n.check(T, now_utc=NOW, task_present=False)
sent.clear()
for _ in range(5):
    n.decide("handoff-rule:ok/LG-99/", T)
_a = len(sent)
for _ in range(5):
    n.decide("handoff-rule:ok/LG-99/0123456789", T)
ok("U27 没口令 0 条；带口令 ≤3 条", _a == 0 and 1 <= len(sent) <= 3)

print("== U28 状态文件里被改过的撤销按钮：不画（复核 B-06；第二轮 R2-3-1：原用例页面上本来就没有按钮可画，测不到守卫）==")
reset()
put(BASE + [f"| LG-02 | 生效（自动） | 规矩二 | 事二 | {added(1)} |"])
n.check(T, now_utc=NOW, task_present=False)
for _i, (_undo, _what) in enumerate(((["\"><a href=\"https://evil.example/\">去那边</a><a href=\"handoff-rule:", "LG-01"], "动作"),
                                     (["no", "LG-01\"><a href=\"https://evil.example/\">去那边</a>"], "编号"))):
    _st = nload()
    _st["last_decide"] = {"oid": "LG-02", "act": "ok", "ms": int(datetime.now(timezone.utc).timestamp() * 1000), "rule": "x",
                          "result": "r", "undo": _undo}
    nstate(_st)
    n.check(T, now_utc=NOW, task_present=False)
    _p = page()
    ok(f"U28{chr(97 + _i)} 撤销按钮的{_what}被改过：不画，页面没有外链（页面上别的按钮照常画）", "evil.example" not in _p and "handoff-rule:" in _p)

print("== U29 候选的证据链接：跑出 docs 的、UNC 的都不给链接（复核 B-07）==")
reset()
put(BASE)
json.dump({"items": [{"id": "RP-009", "rule": "交付前把复跑命令写进报告", "why": "w", "category": "其他", "reason": "当天配额满",
                      "status": "pending", "date": TODAY, "evidence": [{"report_id": "ev", "rel": "../../外面.md"},
                                                                       {"report_id": "unc", "rel": "//192.0.2.1/s/x.md"}]}]},
          io.open(n.POOL_PATH, "w", encoding="utf-8"), ensure_ascii=False)
n.check(T, now_utc=NOW, task_present=False)
ok("U29 两条证据都不成链接", "外面.md" not in page() and "192.0.2.1" not in page())

print("== U30 参数不合法的日志：口令段打码（复核 B-09）==")
n.decide("handoff-rule:no/LG-01/aaaaaaaaaa/extra", T)
for _tail in ("bbbbbbbbbb?x=1", "cccccccccc#frag", "ddddddddddx", "eeeeeeeeee extra"):  # 第二轮 R2-2-5 的几种尾巴（复核 RA-6）
    n.decide(f"handoff-rule:no/LG-01/{_tail}", T)
_log30 = io.open(os.environ["HN_LOG_PATH"], encoding="utf-8").read()
ok("U30 日志里没有那段口令（含 ?x=1、#frag、紧跟字母、空格几种尾巴）", not any(x * 10 in _log30 for x in "abcde"))

print("== U31 「」里引的规矩原文原样保留，不算命中兜底（复核 A-10）==")
sent.clear(); sent_meta.clear()
_h0 = len(n.SCRUB_HITS)
n.toast("知会一声", "规矩原文：「LG-12 那条否决记录别手改」", kind="info")
ok("U31 引号里一个字没改、兜底没命中", "「LG-12 那条否决记录别手改」" in sent[-1][1] and len(n.SCRUB_HITS) == _h0)

print("== U32 每日学习跑完顺带的那轮：计划任务报「正在运行」说的是自己（复核 C-04）==")
reset()
put(BASE)
lstate({"last_scan_utc": H(40), "last_run": {"utc": H(40), "rc": 0}})
_undo = _patch(n, "task_last_result", lambda name: (267009, "北京 10-03 09:00"))
sent.clear(); sent_meta.clear()
try:
    n.check(T, now_utc=NOW, task_present=True, source="daily")
finally:
    _undo()
ok("U32 照样评判连续没成功（需要你介入），处理页不写「此刻正在运行」", bool(hit("没有成功运行")) and "此刻正在运行" not in page())

print("== U33 升级过渡：旧心跳没有 source，先留成计划任务那一轮的（复核 C-09）==")
reset()
put(BASE)
nstate({"last_check": {"utc": H(2)}})
n.check(T, now_utc=NOW, task_present=False, source="daily")
_st = nload()
ok("U33 顺带那轮之后 last_task_check 仍是旧心跳", (_st.get("last_task_check") or {}).get("utc") == H(2)
   and C.task_heartbeat(_st).get("utc") == H(2))

print("== U34 第二件要你做的事来时：常驻弹窗写明一共几件（同类弹窗会替换掉上一条，复核 A-03）==")
# 锚在当天北京 10:00：两轮相隔 1 小时不跨午夜。复核 RB-4：北京 23 点以后跑，「连续 36 小时没成功」的键换了日期、被当成新的
# 又说一遍，正文就不写「一共 2 件」了——那一小时里 promote 会拒绝部署
_N34 = NOW.astimezone(BJ).replace(hour=10, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
_H34 = lambda h: (_N34 - timedelta(hours=h)).isoformat()
reset()
put(BASE + [_L9])
lstate({"last_scan_utc": _H34(40), "last_run": {"utc": _H34(40), "rc": 0}})
n.check(T, now_utc=_N34, task_present=True)
lstate({"last_scan_utc": _H34(40), "last_run": {"utc": _H34(40), "rc": 0}, **_U9})
sent.clear(); sent_meta.clear()
n.check(T, now_utc=_N34 + timedelta(hours=1), task_present=True)
_h = hit("表里冒出一条不是本机加的规矩")
ok("U34 正文写「要你做的事一共 2 件」", bool(_h) and _h[0][0][3] is True and "一共 2 件" in _h[0][0][1])

print("== U35 需要你介入＋3 件告知同一轮：只给真进了正文的记已通知，其余下一轮说（复核 D-08，N-03 那类回归）==")
reset()
put(["| LG-01 | 待定 | 规矩一 | 事一 | 源 |"])
lstate({"last_scan_utc": H(2), "pending": [f"r{i}" for i in range(70)], "last_run": {"utc": H(20), "rc": 0},
        "last_start": {"utc": H(3), "pid": 4999999},
        "cap": {"full": True, "at": f"{NOW.astimezone(BJ):%Y-%m-%d %H:%M}", "total_cap": 40, "waiting": 2}})
sent.clear(); sent_meta.clear()
n.check(T, now_utc=NOW, task_present=True)
_fams = {k.split(":")[0] for k in nload().get("notified", {})}
ok("U35a 第一轮：认不出的行（需要你介入）＋第一件告知记了已通知，另外两件没记", "lint" in _fams and "dailykilled" in _fams
   and "capfull" not in _fams and "backlog" not in _fams)
sent.clear(); sent_meta.clear()
n.check(T, now_utc=NOW + timedelta(hours=4), task_present=True)
ok("U35b 第二轮把剩下两件说完", bool(hit("教训表满了")) and bool(hit("积压 70 件")))

print("== U36 别处同步来的不采纳被你恢复后，同一行原样又回来：照样告知（复核 R2-1-1：以前同一行的提醒键 14 天内去重，静默）==")
reset()
put(ROWS)
n.check(T, now_utc=NOW, task_present=False)
put(ROWS, veto_rows=[VROW])
sent.clear()
n.check(T, now_utc=NOW + timedelta(hours=1), task_present=False)
_told1 = any("不采纳记录里多了 1 条" in s_[1] for s_ in sent)
_ub = re.search(r"handoff-rule:unveto/LG-03/([0-9a-f]{10})", page())
_rcu = n.decide(f"handoff-rule:unveto/LG-03/{_ub.group(1) if _ub else 'x'}", T)
put(ROWS, veto_rows=[VROW])
sent.clear()
n.check(T, now_utc=NOW + timedelta(hours=2), task_present=False)
n.check(T, now_utc=NOW + timedelta(hours=6), task_present=False)
ok("U36 第一次告知、你点恢复、同一行回来后再告知一次", _told1 and _rcu == 0 and sum(1 for s_ in sent if "不采纳记录里多了 1 条" in s_[1]) == 1)

print("== U37 你恢复之后、下一轮巡检之前别处又写进不采纳：照样告知（复核 R2-1-9 ①）==")
reset()
put(ROWS)
n.check(T, now_utc=NOW, task_present=False)
_tk = re.search(r"handoff-rule:no/LG-03/([0-9a-f]{10})", page())
n.decide(f"handoff-rule:no/LG-03/{_tk.group(1) if _tk else 'x'}", T)
_ub = re.search(r"handoff-rule:unveto/LG-03/([0-9a-f]{10})", page())
n.decide(f"handoff-rule:unveto/LG-03/{_ub.group(1) if _ub else 'x'}", T)
put(ROWS, veto_rows=[VROW])
sent.clear()
n.check(T, now_utc=NOW + timedelta(hours=1), task_present=False)
ok("U37 告知「多了 1 条」", any("不采纳记录里多了 1 条" in s_[1] for s_ in sent))

print("== U38 拍板后当场重写页面：生效版还没追平时「刷新不了」仍列着，追平后当场消失（复核 R2-1-9 ③）==")
reset()
put(BASE)
_undo = _patch(n, "ensure_published", lambda t, st=None: (True, "生效版连续 3 轮刷新不了"))
try:
    n.check(T, now_utc=NOW, task_present=False)
finally:
    _undo()
n.check(T, now_utc=NOW, task_present=False, pages_only=True)
_a = "AI 读的那份规矩没能刷新" in page()
n._lessons().publish(T)
n.check(T, now_utc=NOW, task_present=False, pages_only=True)
ok("U38 没追平：仍列着；追平：消失", _a and "AI 读的那份规矩没能刷新" not in page())


def _scan_boom(root, hours, cap=None):
    raise OSError("扫描目录读不了")


tier("写后检查扫描抛错（todo_fail；复核 R2-1-9 ④）", lambda: _patch(n, "scan_problems", _scan_boom),
     {"task_present": False, "scan_root": WT}, "写后检查扫描这一轮没跑成", "need", True)

print("== U40 手写行：到期前告知一次（写「将于」）；到期后文案变了也不再说第二遍（复核 R2-1-9 ⑤、R2-3-10）==")
reset()
_due = (NOW + timedelta(hours=10)).astimezone(BJ)
put(BASE + [f"| LG-05 | 拟生效（至 {_due:%Y-%m-%d %H:%M}） | 手写规矩五 | 事 | 源；加入 {(NOW - timedelta(days=3)).astimezone(BJ):%Y-%m-%d %H:%M}（人工） |"])
sent.clear(); sent_meta.clear()
n.check(T, now_utc=NOW, task_present=False)
_s1 = hit("手写规矩五")
sent.clear(); sent_meta.clear()
n.check(T, now_utc=NOW + timedelta(hours=12), task_present=False)
ok("U40 第一次写「将于」、到期后不再说", bool(_s1) and "将于" in _s1[0][0][1] and not hit("手写规矩五"))

print("== U41 终端采纳一条候选：下一轮告知（复核 R2-1-2：以前来源被采纳分支的局部变量盖掉，永远不说）==")
reset()
put(BASE)
json.dump({"items": [{"id": "RP-010", "rule": "交付前把复跑命令写进报告", "why": "w", "category": "其他", "reason": "当天配额满",
                      "evidence": [], "date": TODAY, "status": "pending"}]}, io.open(n.POOL_PATH, "w", encoding="utf-8"), ensure_ascii=False)
n.check(T, now_utc=NOW, task_present=False)
_rc = n.decide("adopt/RP-010", T, require_token=False, allow_held=True)
sent.clear()
n.check(T, now_utc=NOW + timedelta(hours=1), task_present=False)
n.check(T, now_utc=NOW + timedelta(hours=5), task_present=False)
ok("U41 告知「终端里有人采纳了候选…」", _rc == 0 and any("终端里有人采纳了候选「" in s_[1] for s_ in sent))

print("== U42 教训表／否决记录里混进坏字节：巡检照常、要你介入、说清是哪份（复核 R2-2-1：以前发布自检那一步就崩了）==")
reset()
put(BASE)
io.open(T, "ab").write(b"\n| LG-02 | \xff\xfe | x | y | z |\n")
sent.clear(); sent_meta.clear()
_rc = n.run_main(["check", T])
ok("U42a 教训表有坏字节：入口返回 0、心跳落盘、常驻提醒点名教训表",
   _rc == 0 and bool(nload().get("last_task_check")) and any(s_[3] is True and "坏字节" in s_[1] and "教训表" in s_[1] for s_ in sent))
reset()
put(BASE)
io.open(VT, "ab").write(b"\n\xff\n")
sent.clear(); sent_meta.clear()
_rc = n.run_main(["check", T])
ok("U42b 否决记录有坏字节：同样不崩、点名不采纳记录", _rc == 0 and any("不采纳记录" in s_[1] and "坏字节" in s_[1] for s_ in sent))

print("== U43 出处按 docs 根写（工作传递/…）也认得（复核 R2-2-7）==")
reset()
io.open(os.path.join(WT, "自我改进循环", "R3.md"), "w", encoding="utf-8").write("x")
put(BASE + [f"| LG-02 | 生效（自动） | 规矩二 | 事二 | [R3](工作传递/自我改进循环/R3.md)；{added(1)} |"])
n.check(T, now_utc=NOW, task_present=False)
ok("U43 给了链接", bool(re.search(r'<a href="file:///[^"]*R3\.md">R3</a>', page())))

print("== U44 升级首轮：旧版 veto_seen 里有、否决记录里没有的编号，不当成「少了」误报（复核 R2-1-5）==")
reset()
put(BASE)
nstate({"veto_seen": ["LG-07"], "page_secret": "ab" * 16})
sent.clear()
n.check(T, now_utc=NOW, task_present=False)
_st = nload()
ok("U44 不告知；veto_seen 对齐成现状、记下升级标记", not any("不采纳记录里少了" in s_[1] for s_ in sent)
   and _st.get("veto_seen") == [] and bool(_st.get("veto_v2")))

print("== U45 新规矩简述：规矩原文放进「」、一个字不改（复核 R2-1-6）==")
reset()
put(BASE + [f"| LG-02 | 生效（自动） | 每日学习跑完要看一眼看门狗 | 事 | {added(1)} |"])
_h0 = len(n.SCRUB_HITS)
sent.clear(); sent_meta.clear()
n.check(T, now_utc=NOW, task_present=False)
ok("U45 原文照引、兜底没命中", bool(hit("「每日学习跑完要看一眼看门狗」")) and len(n.SCRUB_HITS) == _h0)

print("== U46 缺「加入」标记的手写拟生效行：表体检要你介入，页面写明到期也不会自动生效（复核 R2-1-8）==")
reset()
put(BASE + [f"| LG-06 | 拟生效（至 {_due:%Y-%m-%d %H:%M}） | 没标记的手写规矩 | 事 | 源 |"])
sent.clear(); sent_meta.clear()
n.check(T, now_utc=NOW, task_present=False)
ok("U46 常驻提醒说有认不出的地方；页面写「到期也不会自动生效」；不说「不用你做事」",
   any(s_[3] is True and "认不出" in s_[1] for s_ in sent) and "到期也不会自动生效" in page()
   and not any("没标记的手写规矩" in s_[1] and "不用你做事" in s_[1] for s_ in sent))

print("== U47 你恢复之后别处又加了一行（已告知「多了」）、再被别处删掉：照样告知「少了」（第十一批，R2-1-4：以前当成你自己恢复，静默）==")
reset()
put(ROWS)
n.check(T, now_utc=NOW, task_present=False)
_tk = re.search(r"handoff-rule:no/LG-03/([0-9a-f]{10})", page())
n.decide(f"handoff-rule:no/LG-03/{_tk.group(1) if _tk else 'x'}", T)
_ub = re.search(r"handoff-rule:unveto/LG-03/([0-9a-f]{10})", page())
_rcu = n.decide(f"handoff-rule:unveto/LG-03/{_ub.group(1) if _ub else 'x'}", T)
put(ROWS, veto_rows=[VROW])
sent.clear()
n.check(T, now_utc=NOW + timedelta(hours=1), task_present=False)
_more = [s_[1] for s_ in sent if "不采纳记录里多了 1 条" in s_[1]]
put(ROWS)
sent.clear()
n.check(T, now_utc=NOW + timedelta(hours=2), task_present=False)
n.check(T, now_utc=NOW + timedelta(hours=6), task_present=False)
ok("U47 先告知「多了 1 条」（指向处理页「最近 30 天撤下的」，第二轮 R2-3-10 ⑥），别处删掉后告知「少了 1 条」",
   _rcu == 0 and bool(_more) and "「最近 30 天撤下的」" in _more[0] and any("不采纳记录里少了 1 条" in s_[1] for s_ in sent))

print("== U48 你点「恢复」时 veto_seen 没来得及改（写状态失败）：巡检按最近操作认出是你自己恢复的，不说「少了」"
      "（第二轮 R2-3-10 ⑧：两套机制原来只有合起来才有测试）==")
reset()
put(ROWS)
n.check(T, now_utc=NOW, task_present=False)
_tk = re.search(r"handoff-rule:no/LG-03/([0-9a-f]{10})", page())
n.decide(f"handoff-rule:no/LG-03/{_tk.group(1) if _tk else 'x'}", T)
_tm.sleep(0.02)
_undo = _patch(n, "_forget_veto", lambda oid: None)
try:
    _ub = re.search(r"handoff-rule:unveto/LG-03/([0-9a-f]{10})", page())
    _rcu = n.decide(f"handoff-rule:unveto/LG-03/{_ub.group(1) if _ub else 'x'}", T)
finally:
    _undo()
_still = "LG-03" in nload().get("veto_seen", [])
sent.clear()
n.check(T, now_utc=NOW + timedelta(hours=1), task_present=False)
n.check(T, now_utc=NOW + timedelta(hours=5), task_present=False)
ok("U48 不说「少了」；veto_seen 随后对齐", _rcu == 0 and _still and not any("不采纳记录里少了" in s_[1] for s_ in sent)
   and "LG-03" not in nload().get("veto_seen", []))

print("== U49 一轮有 5 件告知：先说 3 件、写明另有 2 件，下一轮说完，每件恰好一次（第二轮 R2-3-10 ②）==")
reset()
put(BASE + [f"| LG-0{_i} | 生效 | 规矩{_i} | 事 | 源 |" for _i in range(2, 7)])
n.check(T, now_utc=NOW, task_present=False)
for _i in range(2, 7):
    n.decide(f"no/LG-0{_i}", T, require_token=False, reason="终端试一下", allow_held=False)
sent.clear(); sent_meta.clear()
n.check(T, now_utc=NOW + timedelta(hours=1), task_present=False)
_r49a = [s_[1] for s_ in sent]
n.check(T, now_utc=NOW + timedelta(hours=5), task_present=False)
n.check(T, now_utc=NOW + timedelta(hours=9), task_present=False)
_n49 = sum(b_.count("终端里有人") for b_ in (s_[1] for s_ in sent))
ok("U49 第一轮一条弹窗：3 件＋「另有 2 件」；三轮合计恰好 5 件",
   len(_r49a) == 1 and _r49a[0].count("终端里有人") == 3 and "另有 2 件" in _r49a[0] and _n49 == 5)

print("== U50 「最近 30 天撤下的」里你点过不用的候选：也只列 30 天内的（第二轮 R2-3-10 ③）==")
reset()
put(BASE)
json.dump({"items": [{"id": "RP-011", "rule": "四十天前点过不用的候选", "status": "ignored",
                      "decided": f"{(NOW - timedelta(days=40)).astimezone(BJ):%Y-%m-%d} 08:00"},
                     {"id": "RP-012", "rule": "今天点过不用的候选", "status": "ignored", "decided": f"{TODAY} 08:00"}]},
          io.open(n.POOL_PATH, "w", encoding="utf-8"), ensure_ascii=False)
n.check(T, now_utc=NOW, task_present=False)
_p = page()
ok("U50 今天那条列着、能恢复为候选；40 天前那条不列", 'id="d-RP-012"' in _p and "undrop/RP-012" in _p and 'id="d-RP-011"' not in _p)

print("== U51 学完顺带的那轮等巡检锁 300 秒，计划任务那轮只等 5 秒（复核 C-08；第二轮 R2-1-9 M26）==")
_waits = []


class _LockSpy:
    def __init__(self, path, stale_sec=None):
        self.path = path

    def acquire(self, wait=0):
        _waits.append((os.path.basename(self.path), wait))
        return False

    def release(self):
        pass


_undo = _patch(n.C, "Lock", _LockSpy)
try:
    n.check(T, now_utc=NOW, task_present=False, source="daily")
    n.check(T, now_utc=NOW, task_present=False, source="task")
finally:
    _undo()
ok("U51 顺带那轮 300 秒、计划任务那轮 5 秒", [w_ for p_, w_ in _waits if p_.endswith(".check.lock")] == [300, 5])

print("== U52 「多了 N 条」上一轮已经说过、记账却没落盘：这一轮直接记账，不重复说（第二轮 R2-1-9 M32）==")
reset()
put(ROWS)
n.check(T, now_utc=NOW, task_present=False)
put(ROWS, veto_rows=[VROW])
_st = nload()
_key = f"vetoext:g{n._int(_st.get('veto_gen'))}:" + C.sha("\n".join(n._veto_rows(T)[x] for x in ["LG-03"]))[:10]
_st.setdefault("notified", {})[_key] = f"{TODAY} 00:00"
nstate(_st)
sent.clear()
n.check(T, now_utc=NOW + timedelta(hours=1), task_present=False)
ok("U52 不重复说；veto_seen 里记上了", not any("不采纳记录里多了" in s_[1] for s_ in sent) and "LG-03" in nload().get("veto_seen", []))

tier("规范扫描输出认不出（flowerr；第二轮 R2-3-10 ①：以前只有超时那一支有测试）",
     lambda: _patch(n.subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="不认识的输出", stderr="")),
     {"task_present": False, "flow_root": DOCS}, "脚本出错或输出认不出", "need", True)

print("== U53 巡检正在发「多了 1 条」时你就点了「恢复」：之后不说「少了」（复核 RB-1：并进「已知」的时刻曾按落盘时刻记，"
      "你自己的恢复被当成别处删的，还劝你加回去）==")
reset()
put(ROWS)
n.check(T, now_utc=NOW, task_present=False)
put(ROWS, veto_rows=[VROW])
n.check(T, now_utc=NOW, task_present=False, pages_only=True)  # 处理页上已经列着这条、带「恢复」
_ub53 = re.search(r"handoff-rule:unveto/LG-03/([0-9a-f]{10})", page())
_send53 = n._send


def _send_click(title, body, buttons=None, persistent=True, meta=None):
    sent.append((title, body, buttons, persistent))
    sent_meta.append(meta)
    if "不采纳记录里多了" in (body or "") and _ub53:
        n.decide(f"handoff-rule:unveto/LG-03/{_ub53.group(1)}", T)  # 看到弹窗当场点了「恢复」，这一轮巡检还没收尾
    return True


n._send = _send_click
sent.clear(); sent_meta.clear()
try:
    n.check(T, now_utc=NOW + timedelta(hours=1), task_present=False)
finally:
    n._send = _send53
_told53 = any("不采纳记录里多了" in s_[1] for s_ in sent)
sent.clear(); sent_meta.clear()
n.check(T, now_utc=NOW + timedelta(hours=2), task_present=False)
n.check(T, now_utc=NOW + timedelta(hours=6), task_present=False)
ok("U53 「多了」照常告知；你当场点的「恢复」算你自己的，之后不说「少了」",
   bool(_ub53) and _told53 and not any("不采纳记录里少了" in s_[1] for s_ in sent))

print("== U54 升级前就在「已知」里、没有时刻的编号：补上时刻；以前恢复过、后来又被加回、现在被别处删掉，照样告知「少了」（复核 RB-9）==")
reset()
put(ROWS, veto_rows=[VROW])
n.check(T, now_utc=NOW, task_present=False)  # 升级首轮：LG-03 对齐进「已知」
_st54 = nload()
_st54.pop("veto_seen_ms", None)  # 上一版留下的状态：「已知」里有、没有时刻
_st54["acts"] = [{"oid": "LG-03", "act": "unveto", "ms": int((NOW - timedelta(hours=3)).timestamp() * 1000), "src": "page", "rule": "规矩三"}]
nstate(_st54)
n.check(T, now_utc=NOW + timedelta(hours=1), task_present=False)  # 这一轮给老编号补上时刻
put(ROWS)  # 别处删掉了那一行
sent.clear(); sent_meta.clear()
n.check(T, now_utc=NOW + timedelta(hours=2), task_present=False)
n.check(T, now_utc=NOW + timedelta(hours=6), task_present=False)
ok("U54 告知「少了 1 条」", any("不采纳记录里少了 1 条" in s_[1] for s_ in sent))

print("== U55 状态文件里时刻或代数是无穷大（1e999 读进来是 inf）：巡检照常、心跳落盘（复核 RB-6：以前每轮在同一处崩）==")
_ms55 = int(NOW.timestamp() * 1000)
for _i, _bad in enumerate([{"veto_seen": ["LG-03"], "veto_v2": "x", "veto_seen_ms": {"LG-03": float("inf")},
                            "acts": [{"oid": "LG-03", "act": "unveto", "ms": _ms55, "src": "page"}]},
                           {"veto_gen": float("-inf")},
                           {"acts": [{"oid": "LG-03", "act": "unveto", "ms": float("inf"), "src": "page"}]}]):
    reset()
    put(ROWS)
    nstate(dict(_bad, page_secret="ab" * 16))
    _rc = n.run_main(["check", T])
    ok(f"U55{chr(97 + _i)} {json.dumps(_bad, ensure_ascii=False)[:48]}：返回 0、心跳落盘", _rc == 0 and bool(nload().get("last_task_check")))

print("== U56 已经要你介入、又挤掉了几条告知：「处理页上都列着」只说要你做的事，挤掉的写「下一轮接着说」（第二轮 R2-1-7 ⓐ）==")
reset()
put(BASE + [_L9, "| LG-02 | 生效 | 规矩二 | 事 | 源 |", "| LG-03 | 生效 | 规矩三 | 事 | 源 |"])
lstate({"last_scan_utc": _H34(40), "last_run": {"utc": _H34(40), "rc": 0}})
n.check(T, now_utc=_N34, task_present=True)  # 第一轮：说了「连续 36 小时没成功」（之后仍然成立）
lstate({"last_scan_utc": _H34(40), "last_run": {"utc": _H34(40), "rc": 0}, **_U9})  # 第二轮又冒出表外规矩：新的要你做的事
for _lid in ("LG-02", "LG-03"):
    n.decide(f"no/{_lid}", T, require_token=False, reason="终端试一下", allow_held=False)  # 两条终端替你做的决定（告知类）
sent.clear(); sent_meta.clear()
n.check(T, now_utc=_N34 + timedelta(hours=1), task_present=True)
_h56 = [s_[1] for s_ in sent if s_[3] is True]
ok("U56 常驻弹窗写「要你做的事一共 2 件，处理页上都列着；另有 1 条消息，下一轮接着说」",
   bool(_h56) and "要你做的事一共 2 件，处理页上都列着；另有 1 条消息，下一轮接着说" in _h56[0])

print("== U57 告知超过 4 件、终端替你做的那件排在后面没列出来：标题也不说「不用你做事」（第二轮 R2-1-7 ⓑ）==")
reset()  # 锚在北京 10:00：自动处理记录只认「今天」开头的，两轮跨午夜就不算了（复核 RC-2，和 U34 同一类）
put(BASE + ["| LG-02 | 生效 | 规矩二 | 事 | 源 |"])
n.check(T, now_utc=_N34, task_present=False)
put(BASE + ["| LG-02 | 生效 | 规矩二 | 事 | 源 |"],
    updates=[f"- {_N34.astimezone(BJ):%Y-%m-%d} 09:0{_i}：LG-2{_i} 自动处理（否决记录同步／撤销否决恢复／遗留拟生效到期转生效）。（handoff_lessons.py）"
             for _i in range(4)])
n.decide("no/LG-02", T, require_token=False, reason="终端试一下", allow_held=False)
sent.clear(); sent_meta.clear()
n.check(T, now_utc=_N34 + timedelta(hours=1), task_present=False)
_i57 = [s_[0] for s_, m_ in zip(sent, sent_meta) if m_ and m_["kind"] == "info"]
ok("U57 标题是「知会一声（5 件）」、不说「不用你做事」", bool(_i57) and "知会一声（5 件）" in _i57[0] and "不用你做事" not in _i57[0])

print("== U58 终端替你不采纳：告知里写的撤法是处理页上真有的按钮（「最近 30 天撤下的」→「恢复」；第二轮 R2-1-7 ⓒ）==")
reset()
put(BASE + [f"| LG-03 | 生效（自动） | 报告里写的数字必须带上出处与观测时点，并且注明是谁在什么时候测的 | 事三 | {added(1)} |"])  # 真实长度的规矩（复核 RC-3）
n.check(T, now_utc=NOW, task_present=False)
n.decide("no/LG-03", T, require_token=False, reason="终端试一下", allow_held=False)
sent.clear(); sent_meta.clear()
n.check(T, now_utc=NOW + timedelta(hours=2), task_present=False)
n.check(T, now_utc=NOW + timedelta(hours=6), task_present=False)
_x58 = [m_["xml"] for s_, m_ in zip(sent, sent_meta) if m_ and "终端里有人" in (s_[1] or "")]
ok("U58 真弹出去的弹窗（每行最多 60 字）里有撤法「要撤：处理页「最近 30 天撤下的」点「恢复」」；处理页那一区真有这条的「恢复」按钮",
   bool(_x58) and "要撤：处理页「最近 30 天撤下的」点「恢复」" in _x58[0] and 'id="vetoed"' in page() and "unveto/LG-03/" in page())
ok("U58b 七种终端动作的告知：规矩原文再长，这一行也在 60 字以内，撤法不会被截掉（复核 RC-3）",
   len(n._TERM_LINE) == 7 and all(len(t.replace("{r}", n.cut("很长很长的规矩原文" * 5, 10))) <= 60 for t in n._TERM_LINE.values()))

print("== U59 只有生效版混进了坏字节（教训表与不采纳记录都好）：巡检当轮重新生成，不再每天请你介入（复核 RA-5）==")
reset()
put(BASE)
n._lessons().publish(T)
_pub59 = os.path.join(WT, C.PUBLISH_NAME)
io.open(_pub59, "ab").write(b"\xff\xfe")
_ap59 = n.AUTO_PUBLISH
n.AUTO_PUBLISH = True
sent.clear(); sent_meta.clear()
try:
    _rc59 = n.run_main(["check", T])
finally:
    n.AUTO_PUBLISH = _ap59
try:
    io.open(_pub59, encoding="utf-8").read()
    _ok59 = True
except UnicodeDecodeError:
    _ok59 = False
ok("U59 返回 0、生效版重新读得出、没有「坏字节」的常驻提醒",
   _rc59 == 0 and _ok59 and not any(s_[3] is True and "坏字节" in s_[1] for s_ in sent))

print("== U60 手写拟生效行到期距加入不足 48 小时（每日学习永远不会转它）：照实说要手改，表体检也报（复核 RA-8）==")
reset()
_a60, _d60 = (NOW - timedelta(hours=20)).astimezone(BJ), (NOW + timedelta(hours=4)).astimezone(BJ)
put(BASE + [f"| LG-08 | 拟生效（至 {_d60:%Y-%m-%d %H:%M}） | 短等待的手写规矩 | 事 | 源；加入 {_a60:%Y-%m-%d %H:%M}（人工） |"])
sent.clear(); sent_meta.clear()
n.check(T, now_utc=NOW, task_present=False)
ok("U60 页面写「到期也不会自动生效（到期距加入不足 48 小时，要手改）」；常驻提醒说有认不出的地方；不说「不用你做事」",
   "到期也不会自动生效（到期距加入不足 48 小时，要手改）" in page() and any(s_[3] is True and "认不出" in s_[1] for s_ in sent)
   and not any("短等待的手写规矩" in s_[1] and "不用你做事" in s_[1] for s_ in sent))

print("== U61 巡检开跑之后、比对不采纳记录之前你点了「不采纳」：不当成别处加的（第二轮 R2-1-3；复核 RA-6）==")
reset()
put(ROWS)
n.check(T, now_utc=NOW, task_present=False)
_tk61 = re.search(r"handoff-rule:no/LG-03/([0-9a-f]{10})", page())
_ep61 = n.ensure_published


def _click_then_publish(t, st=None):
    n.decide(f"handoff-rule:no/LG-03/{_tk61.group(1) if _tk61 else 'x'}", T)  # 巡检正在跑（先发布、后比对），你在处理页点了「不采纳」
    return _ep61(t, st)


n.ensure_published = _click_then_publish
sent.clear(); sent_meta.clear()
try:
    n.check(T, now_utc=NOW + timedelta(hours=1), task_present=False)
finally:
    n.ensure_published = _ep61
n.check(T, now_utc=NOW + timedelta(hours=5), task_present=False)
ok("U61 不说「多了」", bool(_tk61) and not any("不采纳记录里多了" in s_[1] for s_ in sent))

print("== U62 恢复一条老格式「否决（见否决记录）」的规矩（状态格没记原状态）：回执照实说还要手改（第二轮 R2-1-8；复核 RA-6）==")
reset()
put(BASE + ["| LG-04 | 否决（见否决记录） | 老格式规矩四 | 事 | 源 |"], veto_rows=[f"| LG-04 | {TODAY} | 负责人 | 旧 |"])
n.check(T, now_utc=NOW, task_present=False)
_ub62 = re.search(r"handoff-rule:unveto/LG-04/([0-9a-f]{10})", page())
sent.clear(); sent_meta.clear()
n.decide(f"handoff-rule:unveto/LG-04/{_ub62.group(1) if _ub62 else 'x'}", T)
ok("U62 回执标题写「还要手改一下」", bool(_ub62) and any("还要手改一下" in (s_[0] or "") for s_ in sent))

print("== U63 状态文件里 veto_seen 坏成了字典：点「不采纳」照常记账（第二轮 R2-2-3；复核 RA-6）==")
reset()
put(ROWS)
n.check(T, now_utc=NOW, task_present=False)
_st63 = nload()
_st63["veto_seen"] = {"x": 1}
nstate(_st63)
_tk63 = re.search(r"handoff-rule:no/LG-03/([0-9a-f]{10})", page())
_rc63 = n.decide(f"handoff-rule:no/LG-03/{_tk63.group(1) if _tk63 else 'x'}", T)
ok("U63 返回 0、veto_seen 变回列表、只记 LG-03", _rc63 == 0 and nload().get("veto_seen") == ["LG-03"])

print("== U65 同一轮新冒出 3 件要你做的事：没列出来的那件已算在「一共 N 件」里，不再说成「另有 1 条消息」（复核 RC-4）==")
reset()
put(BASE + [_L9])
lstate({"last_scan_utc": _H34(40), "last_run": {"utc": _H34(40), "rc": 0}})
n.check(T, now_utc=_N34, task_present=True)  # 第一轮：「连续 36 小时没成功」（之后仍然成立）
put(BASE + [_L9, "| LG-07 | 乱写的状态 | 规矩七 | 事 | 源 |"])  # 第二轮新冒出：认不出的状态格
io.open(VT, "ab").write(b"\n\xff\n")  # ……不采纳记录里的坏字节
lstate({"last_scan_utc": _H34(40), "last_run": {"utc": _H34(40), "rc": 0}, **_U9})  # ……表外规矩
sent.clear(); sent_meta.clear()
n.check(T, now_utc=_N34 + timedelta(hours=1), task_present=True)
_h65 = [s_[1] for s_ in sent if s_[3] is True]
ok("U65 常驻弹窗写「要你做的事一共 4 件，处理页上都列着」，不另说「另有 N 条消息」",
   bool(_h65) and "要你做的事一共 4 件，处理页上都列着" in _h65[0] and "另有" not in _h65[0])

ok("U11 这一套跑下来，出口兜底一次都没命中（各调用点的源文案本身就是干净的）", n.SCRUB_HITS == [])

n_fail = sum(1 for _, c in results if not c)
print(f"\n合计 {len(results)} 项，失败 {n_fail} 项" + (f"；跳过 {len(skips)} 项（{'、'.join(skips)}）" if skips else ""))
shutil.rmtree(ROOT, ignore_errors=True)
sys.exit(1 if n_fail else 0)
