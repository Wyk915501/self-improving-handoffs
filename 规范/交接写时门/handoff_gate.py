#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
handoff_gate.py —— 交接报告写后检查（零 LLM，机械核验）
v2.7 · 2026-09-21 · fable 复验：G6 链接目标不在原址但同目录 _archive/ 下有同名件＝已归档，放行；克隆路线旧件可直接搬走不留跳转件
v2.6 · 2026-09-21 · is_target 排除 _archive/（fable 09-21 评估：克隆-调整-归档的落地前提——归档旧件相对链接深一层必断、冻结件没人能修，会永久挂清单）。检查逻辑零变化，只是范围口径与 is_index 对齐。
（v2.5 · 2026-09-09 · 按 GLM 二轮复核：G6 反斜杠项改编号 G6P（扫描/清单只滤 G6 断链、不滤 G6P）；G6/G8 文件名含 # 先整体查；
     ③类整体存在性逐段精确比对；载荷深搜跳过正文字段；目录列不出直接报
（v2.4 · 同日按 GLM 复核：G8 加③正斜杠目录前缀、同目录比对区分大小写、hook 写索引 README 当场报①③；G6 反斜杠链接判不可移植）
（v2.3 · 同日按 Astra 对抗复核修正 G8 Markdown 转义与波浪线围栏；v2.2 · 同日按 US3 Claude 1750 加 G8）

用法
  作为 Claude Code PostToolUse hook：  python handoff_gate.py --hook          （stdin 读 hook JSON）
  作为 ZCode 等其他宿主的 hook：       python handoff_gate.py --hook-strict --root <docs/工作传递>
        （原因写 stderr、退出码 2；载荷字段名不同也能用：先深搜载荷里的报告路径，找不到就兜底扫 --root 下最近改动的报告）
  手动核验若干文件：                  python handoff_gate.py 文件1.md 文件2.md   （相对路径可用；不在范围会明说）
  扫描目录（默认最近 24 小时改动）：  python handoff_gate.py --scan <docs/工作传递> [--since 小时] [--all]
        [--todo <输出文件> [--writer "<写入端说明>"]]  把没过的报告按来源目录写成待处理清单；每台机器写自己那份
        （本机 写后检查-待处理.md／US3 写后检查-待处理-US3.md），写不出退出 2。清单只是近 N 小时的收件箱，不是长期待办

只对「路径含 工作传递 且文件名以 _交接报告.md 结尾」的文件生效；其余文件 hook 模式静默放行、CLI 模式明说跳过。
它是"写后提示"：hook 在文件已写入之后运行，把不合格原因回给写的那个窗口；它拦不住写入，也不覆盖
Bash/同步/Codex 等其他写入来源——消费方在读新件、更新索引前用 CLI 再查一次即可。

检查项（全部可复放）
  G1 frontmatter 从第 1 行开始、200 行内闭合、是合法 YAML 映射、无重复键（含带引号的键）、无非法值（如坏日期）
     解析用 PyYAML 的拒绝重复键 loader；本机未装 PyYAML 时 fail-closed（报 G1，不静默放过）
  G2 status 只允许 draft | ready_for_review（引号内同样接受）
  G3 模板顶层键齐全（以仓内 docs/工作传递/交接模板.md 为准；找不到用内置清单）
     full_contract_finalize 仅 workflow_profile == multi-ai-loop/v1 时必填
  G4 ready_for_review 时 frozen_at / observed_at 必须是带时区偏移的时间；frozen_at 不得晚于现在 60 秒以上；
     observed_at ≤ frozen_at 且不得在未来
  G5 正文不引用会话临时目录（AppData/Local/Temp/claude、/tmp/claude、…/scratchpad/）；同行 gate:allow-temp 豁免
  G6 相对 markdown 链接可解析到实存文件（支持 <尖括号目标>、带标题、引用式定义；跳过围栏代码与行内代码）
     只证明"本机存在"，不证明另一台机器可达；扫描与清单会滤掉这一类（跨机假断链）。文件名含 # 的先整体查存在
  G6P 链接目标含反斜杠：即使本机能解析也报（另一台机器必断，一律用正斜杠）；扫描与清单**不**过滤本项
  G7（仅 hook 模式，提示性）本次写入的是 frozen_at 已过 30 分钟的 ready_for_review 件 → 提示"冻结件不回改"
     它按 frozen_at 年龄判断，不证明冻结历史，也抓不到改过 frozen_at 的回改
  G0 文件名含反斜杠（Windows 分隔符混进 Linux 文件名，文件没进目录、索引找不到）
  G8（只对 工作传递/**/README.md 索引；不套 G1–G7）保守检查 markdown 链接：①解释合法标点转义后，文件路径仍含反斜杠；
     ②目标是同目录裸文件名（不含 / 与 ..）但本机当前不存在（与目录清单逐字比对，大小写不同也算不存在，NTFS 下不靠 exists）；
     ③目标带正斜杠目录前缀（如 claude-code/文件）、整体不存在、但末段就在本目录——写索引的人把自己所在目录又写了一遍。
     含 ../、绝对路径、http 的一律不报（不等于证明有效）；_archive/ 下的 README 整个跳过（冻结快照，断链正常）。
     --scan 与显式指定时查①②③；hook 模式写索引 README 时当场只报①③（②留给扫描：索引常先于报告落盘）。
     文件名里的 # 不当锚点：先整体查存在，再按最后一个 # 截断重查（局限：`C#研究.md` 缺失而同目录恰有文件 `C` 时会被当
     锚点放过，报告名一律用链接原文）；③的整体存在性逐段精确比对（不靠 NTFS 的 exists）；
     索引所在目录列不出时直接报"读不到目录"，不拿空集继续判。载荷深搜跳过 content/new_string 等正文字段，
     正文里出现别件的路径不会劫持本次检查
环境变量 HANDOFF_TOOLS_DIR：状态文件目录（默认 ~/.claude/tools）；测试指到临时目录，不碰真实家目录
退出码：hook 模式永远 0（用 JSON decision 阻断）
       CLI：0 全过 · 1 有不合格 · 2 有显式指定的文件缺失/范围外，或扫描目录不存在（任何漏查都不是成功）
"""
import io, json, os, re, sys, glob, time
from datetime import datetime, date, timezone, timedelta
from urllib.parse import unquote

try:
    import yaml  # PyYAML；Windows 与 US3 均已装。缺失时 fail-closed
except Exception:  # pragma: no cover
    yaml = None

BUILTIN_KEYS = [
    "title","scope","task","type","status","workflow_profile","contract_ref","contract_revision",
    "contract_sha256","contract_mode","revision","report_id","batch_id","concern_id","effect_id",
    "implementation_status","operational_validation","owner","created","updated","source_tool",
    "source_model","source_surface","observed_at","frozen_at","review_level","independence_notes",
    "reviewed_object","stale_if","exact_refs","artifact_hashes","related_reports","intended_readers",
    "data_classification","sensitive_data","canonical_backflow","additional_backflows",
    "full_contract_finalize",
]
CONDITIONAL = {"full_contract_finalize": ("workflow_profile", "multi-ai-loop/v1")}
TOOLS_DIR = os.environ.get("HANDOFF_TOOLS_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "tools")  # 测试用 HANDOFF_TOOLS_DIR 指到临时目录，不碰真实家目录
SCAN_STAMP = os.path.join(TOOLS_DIR, "handoff_gate_lastscan")
SCAN_SEEN = os.path.join(TOOLS_DIR, "handoff_gate_reported.json")
FALLBACK_MINUTES = 15       # 载荷里找不到路径时，回退扫描"最近改动"的窗口
FALLBACK_MIN_INTERVAL = 60  # 回退扫描最短间隔（秒），避免每次工具调用都全扫
FALLBACK_MAX_FILES = 3      # 一次最多报几件，避免一次吐一墙别人的历史文件
TEMP_PAT = re.compile(r"(AppData[/\\]Local[/\\]Temp[/\\]claude|/tmp/claude|[/\\]scratchpad[/\\])")
KEY_PAT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):")
INLINE_CODE_PAT = re.compile(r"`[^`\n]*`")
LINK_INLINE_PAT = re.compile(r"\]\(\s*(<[^>\n]*>|[^\s)]+)(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)")
REF_DEF_PAT = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>\n]*>|\S+)", re.M)
FROZEN_REWRITE_MIN = 30

if yaml is not None:
    class _StrictLoader(yaml.SafeLoader):
        """拒绝重复键（含带引号的键）的 SafeLoader。"""

    def _construct_mapping(loader, node, deep=False):
        seen = set()
        for k_node, _ in node.value:
            k = loader.construct_object(k_node, deep=deep)
            if k in seen:
                raise yaml.constructor.ConstructorError(None, None, f"重复键 {k!r}", k_node.start_mark)
            seen.add(k)
        return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)

    _StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def is_target(path):
    """报告检查范围：路径含 工作传递 且以 _交接报告.md 结尾，且不在 _archive/ 里（v2.6）。
    _archive＝冻结快照，与 is_index 同一哲学；克隆-调整-归档路线的落地前提——旧件挪进去后
    相对链接深一层必断、冻结件没人能修，不排除的话会永久挂在待处理清单上（fable 09-21 评估）。"""
    p = os.path.abspath(path).replace("\\", "/")
    if "工作传递" not in p or not p.endswith("_交接报告.md"):
        return False
    return not any(seg == "_archive" for seg in p.split("/"))


def is_index(path):
    """G8 的范围：工作传递 下的 README.md 索引，且不在 _archive/ 里（冻结快照，断链是正常的）。"""
    p = os.path.abspath(path).replace("\\", "/")
    if "工作传递" not in p or not p.endswith("/README.md"):
        return False
    return not any(seg == "_archive" for seg in p.split("/"))


def find_template(path):
    d = os.path.dirname(os.path.abspath(path))
    for _ in range(8):
        cand = os.path.join(d, "交接模板.md")
        if os.path.isfile(cand):
            return cand
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return None


def template_keys(path):
    t = find_template(path)
    if not t:
        return BUILTIN_KEYS, "内置清单"
    keys = []
    with io.open(t, encoding="utf-8", errors="replace") as f:
        lines = f.read().split("\n")
    if not lines or lines[0].strip() != "---":
        return BUILTIN_KEYS, "内置清单（模板首行非 ---）"
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        m = KEY_PAT.match(ln)
        if m:
            keys.append(m.group(1))
    return (keys or BUILTIN_KEYS), (os.path.relpath(t, os.path.dirname(os.path.abspath(path))) if keys else "内置清单")


def _strip_quotes(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def parse_front(text):
    """返回 (keys, data:dict, errors:list)。errors 含 G1 级问题；YAML 解析失败时 data 为空。"""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        first = (lines[0] if lines else "")[:40]
        return [], {}, [f"G1 frontmatter 不在第 1 行（第 1 行是「{first}」）——标准解析器读不到任何字段"]
    end = None
    for i in range(1, min(len(lines), 201)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return [], {}, ["G1 frontmatter 200 行内未闭合（缺第二个 ---）"]
    block = "\n".join(lines[1:end])
    if yaml is None:
        # fail-closed：没有解析器就不声称合法；其余检查用受限解析继续，便于一次看全问题
        data = {}
        for ln in block.split("\n"):
            m = KEY_PAT.match(ln)
            if m:
                data[m.group(1)] = _strip_quotes(ln[len(m.group(1)) + 1:].split(" #", 1)[0])
        return list(data.keys()), data, ["G1 本机未装 PyYAML，无法验证 frontmatter 是否合法 YAML（fail-closed；请 pip install pyyaml）"]
    try:
        loaded = yaml.load(block, Loader=_StrictLoader)
    except Exception as e:  # YAMLError、重复键 ConstructorError、坏日期 ValueError 等一并 fail-closed
        msg = str(e).split("\n")[0][:120]
        return [], {}, [f"G1 frontmatter 无法解析（{type(e).__name__}）：{msg}"]
    if not isinstance(loaded, dict):
        return [], {}, ["G1 frontmatter 顶层不是键值映射"]
    return list(loaded.keys()), loaded, []


def sval(v):
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, bool):
        return "true" if v else "false"
    return _strip_quotes(str(v))


def parse_dt(v):
    if isinstance(v, datetime):
        return v if v.tzinfo else None
    if isinstance(v, date):
        return None
    s = sval(v)
    if not s or s.lower() == "none":
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else None


def strip_fenced_code(text):
    """去掉 CommonMark 反引号/波浪线围栏内容；闭栏须同类且长度不短于开栏。"""
    out, kind, width = [], None, 0
    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        if kind is not None:
            m = re.match(r"^ {0,3}(`{3,}|~{3,})[ \t]*$", bare)
            if m and m.group(1)[0] == kind and len(m.group(1)) >= width:
                kind, width = None, 0
            out.append("\n" if line.endswith(("\n", "\r")) else "")
            continue
        m = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", bare)
        if m and (m.group(1)[0] == "~" or "`" not in m.group(2)):
            kind, width = m.group(1)[0], len(m.group(1))
            out.append("\n" if line.endswith(("\n", "\r")) else "")
        else:
            out.append(line)
    return "".join(out)


ASCII_PUNCT = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")


def unescape_md_punctuation(target):
    """CommonMark 反斜杠只转义 ASCII 标点；`目录\\文件` 中字母/数字前的分隔符会保留。"""
    out, i = [], 0
    while i < len(target):
        if target[i] == "\\" and i + 1 < len(target) and target[i + 1] in ASCII_PUNCT:
            out.append(target[i + 1])
            i += 2
        else:
            out.append(target[i])
            i += 1
    return "".join(out)


def scan_links(text):
    body = strip_fenced_code(text)
    body = INLINE_CODE_PAT.sub("", body)
    targets = [m.group(1) for m in LINK_INLINE_PAT.finditer(body)]
    targets += [m.group(1) for m in REF_DEF_PAT.finditer(body)]
    out = []
    for t in targets:
        t = t.strip()
        if t.startswith("<") and t.endswith(">"):
            t = t[1:-1].strip()
        out.append(unescape_md_punctuation(t))
    return out


def name_problems(base_name):
    """文件名本身的问题（与内容无关）。G0：Linux 上允许反斜杠当文件名字符，Windows 路径分隔符混进来后，
    文件会躺在子任务根目录下叫 `claude-code\\2026-…`，既不在目录里也不在索引里（09-09 US3 实例两份）。"""
    out = []
    if "\\" in base_name:
        out.append("G0 文件名里含反斜杠「\\」——Windows 路径分隔符被当成了文件名的一部分，文件没进它该在的目录、索引找不到它；请 mv 进目录再改索引")
    return out


def check(path, hook_mode=False):
    probs = list(name_problems(os.path.basename(path)))
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        return probs + [f"读不到文件：{e}"]
    keys, kv, ferr = parse_front(text)
    probs.extend(ferr)
    if not keys:
        return probs  # frontmatter 读不到/解析失败，后续字段检查只会产生连带噪声
    now = datetime.now(timezone.utc)

    st = sval(kv.get("status"))
    if st not in ("draft", "ready_for_review"):
        probs.append(f"G2 status=「{st}」不合法；报告文件只允许 draft | ready_for_review（处置写在索引 disposition）")

    req, src = template_keys(path)
    missing = []
    for k in req:
        if k in CONDITIONAL:
            ck, cv = CONDITIONAL[k]
            if sval(kv.get(ck)) != cv:
                continue
        if k not in keys:
            missing.append(k)
    if missing:
        probs.append(f"G3 缺 {len(missing)} 个模板顶层键（依据 {src}）：{', '.join(missing[:12])}{' …' if len(missing) > 12 else ''}")

    fz = parse_dt(kv.get("frozen_at"))
    ob = parse_dt(kv.get("observed_at"))
    if st == "ready_for_review":
        if fz is None:
            probs.append(f"G4 ready_for_review 但 frozen_at=「{sval(kv.get('frozen_at'))}」不是带时区偏移的时间")
        elif fz - now > timedelta(seconds=60):
            probs.append(f"G4 frozen_at {fz.isoformat()} 比现在晚 {int((fz - now).total_seconds())} 秒——预盖；冻结时刻不得早于实际落盘")
        if ob is None:
            probs.append(f"G4 observed_at=「{sval(kv.get('observed_at'))}」不是带时区偏移的时间")
        else:
            if ob - now > timedelta(seconds=60):
                probs.append(f"G4 observed_at {ob.isoformat()} 在未来")
            if fz is not None and ob > fz:
                probs.append(f"G4 observed_at 晚于 frozen_at（{ob.isoformat()} > {fz.isoformat()}）——观测不可能发生在冻结之后")
        if hook_mode and fz is not None and now - fz > timedelta(minutes=FROZEN_REWRITE_MIN):
            mins = int((now - fz).total_seconds() // 60)
            probs.append(f"G7（提示）本次写入的是 frozen_at 已过 {mins} 分钟的 ready_for_review 件——冻结件不回改，要改请另写前向更正件并在索引 disposition 指过去。本项只按 frozen_at 年龄判断，不证明冻结历史")

    hits = [i for i, ln in enumerate(text.split("\n"), 1) if TEMP_PAT.search(ln) and "gate:allow-temp" not in ln]
    if hits:
        probs.append(f"G5 引用了会话临时目录（复核方打不开），行 {', '.join(map(str, hits[:8]))}{' …' if len(hits) > 8 else ''}；把文件落进仓内改相对链接，或同行加 gate:allow-temp 标明只是举证")

    base = os.path.dirname(os.path.abspath(path))
    broken, nonportable = [], []
    for tgt in scan_links(text):
        if tgt.startswith(("http://", "https://", "mailto:", "#", "data:")):
            continue
        whole = unquote(tgt)
        if "\\" in whole.split("#", 1)[0]:
            # Windows 上 os.path.join 认反斜杠、本机能解析，同步到 Linux 就断——不可移植，单独报（GLM 09-09）
            nonportable.append(unquote(tgt.rsplit("#", 1)[0]) if "#" in tgt else whole)  # 报文件路径部分，不带锚点
            continue
        # 文件名本身可能含 #：先整体试存在，不存在再按最后一个 # 剥锚点重试（GLM 09-09 二轮）
        cands = [whole] + ([unquote(tgt.rsplit("#", 1)[0])] if "#" in tgt else [])
        cands = [c for c in cands if c]
        if not cands:
            continue
        if not any(os.path.exists(c if os.path.isabs(c) else os.path.join(base, c)) for c in cands):
            # v2.7（fable 09-21 复验）：目标不在原址、但它所在目录的 _archive/ 里有同名文件＝已归档，不算断链。
            # 这样"克隆-调整-归档"可以把旧件直接搬走、原址不留跳转件（跳转件自己过不了 G2/G3，还会被数进碎片化），
            # 别人冻结件里指向旧址的链接也不用改（它们也改不了）。
            def _archived(c):
                full = c if os.path.isabs(c) else os.path.join(base, c)
                name = os.path.basename(full.rstrip("/"))
                # 只对交接报告放行：README 之类的同名件在 _archive/ 里很常见，不能因此放过真断链
                return name.endswith("_交接报告.md") and os.path.isfile(os.path.join(os.path.dirname(full.rstrip("/")), "_archive", name))
            if any(_archived(c) for c in cands):
                continue
            broken.append(whole)  # 报原文，不报剥过锚点的串（GLM 09-09 三轮）
    if nonportable:
        probs.append(f"G6P {len(nonportable)} 个链接目标含反斜杠「\\」（本机 Windows 能解析，另一台机器上必断；一律用正斜杠；扫描与清单不过滤本项）：{'；'.join(nonportable[:5])}{' …' if len(nonportable) > 5 else ''}")
    if broken:
        probs.append(f"G6 {len(broken)} 个链接在本机解析不到文件：{'；'.join(broken[:5])}{' …' if len(broken) > 5 else ''}（本机存在也不证明对方机器可达）")
    return probs


def exists_exact(base, rel):
    """逐段精确（区分大小写）比对相对路径是否存在；NTFS 的 os.path.exists 不分大小写，Linux 分（GLM 09-09 二轮）。"""
    cur = base
    for seg in [x for x in rel.replace("\\", "/").split("/") if x and x != "."]:
        try:
            if seg not in os.listdir(cur):
                return False
        except OSError:
            return False
        cur = os.path.join(cur, seg)
    return True


def index_problems(path, hook_mode=False):
    """G8：索引 README 里的链接可达性，保守检查两类常见问题（09-09 US3 Claude 1750 指出的残留：三份索引把链接目标写成
    `claude-code\\2026-…`，README 自己就在 claude-code/ 里，相对解析成 claude-code/claude-code\\…，三条全断；
    而报告文件本身放对了——"文件放错"（G0）与"索引行写错"是两个独立缺陷、同一根因）。
      ① 目标含反斜杠：确定性错误，就是这次的根因
      ② 目标是同目录裸文件名（不含 / 与 ..、非绝对路径）但本机当前不存在：提示先确认同步完成，再核链接或文件归位
    含 ../ 的、绝对 POSIX 路径（/root/…）、http(s) 一律不报——那些是跨机同步不对称，早有定论不修。
    不套报告那套模板键/状态词/时间戳检查。"""
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        return [f"读不到文件：{e}"]
    base = os.path.dirname(os.path.abspath(path))
    try:
        siblings = set(os.listdir(base))  # 精确（大小写敏感）比对：NTFS 的 os.path.exists 不分大小写，两机会判不同（GLM 09-09）
    except OSError as e:
        return [f"G8 读不到索引所在目录，无法核对链接：{e}"]  # 不拿空集继续判（GLM 09-09 二轮）
    bs, missing, prefixed = [], [], []
    for tgt in scan_links(text):
        if tgt.startswith(("http://", "https://", "mailto:", "#", "data:")):
            continue
        # scan_links 已解释合法的 CommonMark 标点转义；锚点不属于文件路径——但文件名本身可能含 #，
        # 所以先整体试一次存在性，不存在再剥锚点（GLM 09-09）
        whole = unquote(tgt)
        if "/" not in whole and ".." not in whole and "\\" not in whole and whole in siblings:
            continue
        path_part = tgt.rsplit("#", 1)[0] if "#" in tgt else tgt  # 锚点只认最后一个 #（文件名里的 # 保留）
        if "\\" in path_part:
            bs.append(tgt)
            continue
        t = unquote(path_part)
        if not t or ".." in t or os.path.isabs(t):
            continue  # 上级、绝对路径：不在 G8 的保守覆盖范围，不报，也不证明有效
        if "/" in t:
            # ③ 同根因的另一种拼写（GLM 09-09）：写成 `claude-code/文件` 而 README 自己就在 claude-code/ 里，
            #    解析成 claude-code/claude-code/文件 必断。只在"整体不存在、但最后一段裸名就在同目录"时报，误报面极窄
            last = t.rsplit("/", 1)[-1]
            if last and last in siblings and not exists_exact(base, t):
                prefixed.append(tgt)
            continue
        if t not in siblings:
            missing.append(unquote(tgt))  # 报原文
    out = []
    if bs:
        out.append(f"G8 索引链接目标含反斜杠「\\」{len(bs)} 处（写索引时拼路径带了目录前缀，相对解析成 目录/目录\\文件 必断；README 与文件同目录时只写裸文件名）：{'；'.join(x[:60] for x in bs[:3])}{' …' if len(bs) > 3 else ''}")
    if prefixed:
        out.append(f"G8 索引链接疑似多带了目录前缀 {len(prefixed)} 处（目标整体不存在，但最后一段文件名就在本目录；README 与文件同目录时只写裸文件名）：{'；'.join(x[:60] for x in prefixed[:3])}{' …' if len(prefixed) > 3 else ''}")
    if missing and not hook_mode:
        # 写索引那一刻文件可能还没落盘（先写行再写件是常见顺序），所以 hook 模式不报这一类，只在扫描时报
        out.append(f"G8 索引链接在本机当前找不到同目录目标 {len(missing)} 个（精确大小写比对；请先确认索引与报告已同步完成，再核对链接写法或文件是否归位）：{'；'.join(x[:60] for x in missing[:3])}{' …' if len(missing) > 3 else ''}")
    return out


def fmt(path, probs):
    return f"✗ {path}\n" + "".join(f"    - {p}\n" for p in probs)


BJ = timezone(timedelta(hours=8))
TODO_NAME = "写后检查-待处理.md"


def report_status(path):
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            _, kv, _ = parse_front(f.read())
        return sval(kv.get("status")) or "?"
    except Exception:
        return "?"


def todo_md(root, findings, out_path, hours, writer=None):
    """把没过检查的报告按来源目录分组，写成给"写报告的 AI"看的待处理清单（活文档，脚本生成）。
    findings: [(abs_path, mtime, probs)]。负责人不需要读这份；它是给各来源目录的 AI 开工时自查用的。
    writer: 写入端说明（哪台机器、哪个定时任务）。每台机器写自己那份文件，不共用路径——docs 是双向同步域，
            两端写同一路径会互相覆盖（Codex 1557 与 US3 Claude 1550 独立同结论）。
    返回写成的路径；写不进去返回 None（调用方必须检查，不能打印"已写"）。"""
    from collections import defaultdict
    root = os.path.abspath(root)
    by = defaultdict(list)
    for p, mt, probs in findings:
        rel = os.path.relpath(p, root).replace("\\", "/")
        # 按"子任务/…/来源目录"整条路径分组：同名 claude-code 目录属于不同窗口，得分开
        src = rel.rsplit("/", 1)[0] if "/" in rel else "?"
        # 索引 README 不是报告，没有 draft/ready_for_review；清单里标成「索引」让读者一眼看出是索引问题（G8）
        by[src].append((rel, mt, probs, "索引" if os.path.basename(p) == "README.md" else report_status(p)))
    now = datetime.now(BJ)
    L = ["现役", "", "# 写后检查 · 待处理（脚本生成，勿手改）", "",
         f"生成：{now:%Y-%m-%d %H:%M}（北京）。写入端：{writer or '未标注'}。范围：近 {int(hours)} 小时改动、没过写后检查的交接报告，按**来源目录**分组。",
         "**这份给写报告的 AI 看，不是给负责人看的**：开工先看自己来源目录（claude-code／codex／claude-code-US3-claude／Zcode-glm／claude-code-glm）下有没有条目。",
         f"**它只是近 {int(hours)} 小时的收件箱，不是长期待办账**：超出窗口的条目下次生成时会消失，写入端停机超过窗口会漏。每台机器只写自己那份（本机 写后检查-待处理.md／US3 写后检查-待处理-US3.md），看你这台机器的。",
         "", "怎么处理：",
         "- 状态 `draft`：就地改，改完再交出。",
         "- 状态 `ready_for_review`（已冻结）：**不回改内容**。纯格式修补（把 frontmatter 挪到第 1 行、补缺的模板键、把 `frozen_at` 改成真实落盘时刻）算不算回改，待负责人定规则；定之前先不动，但下一份别再犯。",
         "- 只有断链、且目标在另一台机器上存在的：不算问题（跨机同步不对称），本清单已过滤。",
        "- 状态标 `索引` 的条目是 README 索引本身的链接风险（G8：解释合法标点转义后路径仍含反斜杠，或本机当前找不到同目录裸文件名）：先确认同步完成，再核对链接或文件归位；只改路径写法，不动登记内容。",
         "- 故意做坏的验收样本：请挪出 `工作传递/` 或改名不带 `_交接报告`，否则每轮都被扫到。",
         ""]
    if not by:
        L.append("（当前没有条目，全部通过。）")
    for src in sorted(by):
        items = by[src]
        L.append(f"## {src}（{len(items)} 件）")
        L.append("")
        for rel, mt, probs, st in sorted(items):
            when = datetime.fromtimestamp(mt, BJ).strftime("%m-%d %H:%M")
            L.append(f"- [{rel.split('/')[-1]}]({rel})　改动 {when}　状态 `{st}`")
            L += [f"  - {x}" for x in probs]
        L.append("")
    L.append("## 更新记录")
    L.append("")
    L.append(f"- {now:%Y-%m-%d %H:%M}：由 handoff_gate.py 自动重写。写入端：{writer or '未标注'}；各端的调度方式见 交接写时门/README「各端要装什么」。")
    text = "\n".join(L) + "\n"
    # 内容没变就不重写：这个文件在 docs 同步树里，每 4 小时换个时间戳会被当成假改动来回同步
    def _body(s):
        return [x for x in s.split("\n") if not x.startswith("生成：") and not x.startswith("- 20")]
    try:
        if os.path.isfile(out_path):
            with io.open(out_path, encoding="utf-8", errors="replace") as f:
                if _body(f.read()) == _body(text):
                    return out_path
        tmp = out_path + ".tmp"
        with io.open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, out_path)
        return out_path
    except OSError:
        return None


BODY_KEYS = {"content", "new_string", "old_string", "new_str", "old_str", "text", "body", "edits"}  # 载荷里的正文字段，深搜不进


def find_target_in(obj, depth=0):
    """在钩子载荷里深搜一个交接报告的真实路径。不依赖具体字段名，兼容不同宿主。"""
    if depth > 6:
        return None
    if isinstance(obj, str):
        s = obj.strip().strip('"')
        if s.endswith("_交接报告.md") and os.path.isfile(s) and is_target(s):
            return s
        return None
    if isinstance(obj, dict):
        for k in ("tool_input", "toolInput", "tool_response", "toolResponse", "input", "params", "arguments", "args"):
            if k in obj:
                r = find_target_in(obj[k], depth + 1)
                if r:
                    return r
        for k, v in obj.items():
            if k in BODY_KEYS:
                continue  # 写入正文里出现的路径不是本次写入的对象（GLM 09-09 二轮：正文含别件绝对路径会劫持）
            r = find_target_in(v, depth + 1)
            if r:
                return r
        return None
    if isinstance(obj, list):
        for v in obj:
            r = find_target_in(v, depth + 1)
            if r:
                return r
    return None


def find_index_in(obj, depth=0):
    """在钩子载荷里深搜一个索引 README 的真实路径（工作传递 下、非 _archive）。"""
    if depth > 6:
        return None
    if isinstance(obj, str):
        s = obj.strip().strip('"')
        if s.endswith("README.md") and os.path.isfile(s) and is_index(s):
            return s
        return None
    if isinstance(obj, dict):
        for k in ("tool_input", "toolInput", "tool_response", "toolResponse", "input", "params", "arguments", "args"):
            if k in obj:
                r = find_index_in(obj[k], depth + 1)
                if r:
                    return r
        for k, v in obj.items():
            if k in BODY_KEYS:
                continue
            r = find_index_in(v, depth + 1)
            if r:
                return r
        return None
    if isinstance(obj, list):
        for v in obj:
            r = find_index_in(v, depth + 1)
            if r:
                return r
    return None


def guess_root(explicit=None):
    """找 工作传递 目录：优先显式给的，其次从 cwd 往上找。"""
    if explicit and os.path.isdir(explicit):
        return os.path.abspath(explicit)
    d = os.path.abspath(os.getcwd())
    for _ in range(8):
        for cand in (os.path.join(d, "工作传递"), os.path.join(d, "docs", "工作传递")):
            if os.path.isdir(cand):
                return cand
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return None


def fallback_scan(root):
    """载荷里没找到路径时的兜底：扫最近改动的交接报告。
    三重收敛，免得把别人的历史文件当成本次问题吐一墙：
      · 限流：距上次兜底扫描不足 FALLBACK_MIN_INTERVAL 秒直接返回空
      · 去重：同一 (路径, 改动时刻) 只报一次，记在 SCAN_SEEN
      · 限量：一次最多 FALLBACK_MAX_FILES 件
    另外这里用 hook_mode=False（不查 G7）：我们不知道这些文件是不是本进程写的，
    只是同步下来或别的窗口写的，不该按"回改冻结件"提醒。
    """
    if not root:
        return []
    try:
        if time.time() - os.path.getmtime(SCAN_STAMP) < FALLBACK_MIN_INTERVAL:
            return []
    except OSError:
        pass
    try:
        os.makedirs(TOOLS_DIR, exist_ok=True)
        with io.open(SCAN_STAMP, "w", encoding="utf-8") as f:
            f.write(datetime.now(timezone.utc).isoformat())
    except OSError:
        pass
    try:
        seen = json.load(io.open(SCAN_SEEN, encoding="utf-8"))
        if not isinstance(seen, dict):
            seen = {}
    except Exception:
        seen = {}
    cutoff = time.time() - FALLBACK_MINUTES * 60
    out, changed = [], False
    for p in sorted(glob.glob(os.path.join(root, "**", "*_交接报告.md"), recursive=True)):
        try:
            mt = os.path.getmtime(p)
        except OSError:
            continue
        if mt < cutoff or not is_target(p):
            continue
        ap = os.path.abspath(p)
        key = f"{int(mt)}"
        if seen.get(ap) == key:
            continue
        probs = check(ap, hook_mode=False)
        seen[ap] = key
        changed = True
        if probs:
            out.append((ap, probs))
            if len(out) >= FALLBACK_MAX_FILES:
                break
    if changed:
        try:
            for k in [k for k, _ in sorted(seen.items(), key=lambda kv: kv[1])][:-400]:
                seen.pop(k, None)  # 只留最近 400 条
            atomic = SCAN_SEEN + ".tmp"
            with io.open(atomic, "w", encoding="utf-8") as f:
                json.dump(seen, f, ensure_ascii=False)
            os.replace(atomic, SCAN_SEEN)
        except OSError:
            pass
    return out


def main(argv):
    if argv and argv[0] in ("--hook", "--hook-strict"):
        # --hook       ：Claude Code 协议（stdout 出 JSON，退出 0，宿主按 decision 回给模型）
        # --hook-strict：通用协议（原因写 stderr，退出 2），给不认 JSON 决策的宿主（如 ZCode）
        # --root <工作传递目录>：载荷里找不到路径时，兜底扫该目录最近改动的报告（限流，见 FALLBACK_*）
        strict = argv[0] == "--hook-strict"
        root_arg = argv[argv.index("--root") + 1] if "--root" in argv and len(argv) > argv.index("--root") + 1 else None
        try:
            data = json.load(sys.stdin)
        except Exception:
            data = {}
        path = ""
        if isinstance(data, dict):
            ti = data.get("tool_input")
            if isinstance(ti, dict):
                path = ti.get("file_path") or ""
            if not path:
                tr = data.get("tool_response")
                if isinstance(tr, dict):
                    path = tr.get("filePath") or ""
        if path and not (os.path.isfile(path) and is_target(path)):
            path = ""
        if not path:
            path = find_target_in(data) or ""   # 字段名不同的宿主：深搜载荷
        findings = []
        ipath = "" if path else find_index_in(data)
        if ipath:
            # 索引 README 写完也当场查（GLM 09-09 指出"只能扫描时发现"是自设约束）：只报确定性的两类
            # （反斜杠、多带目录前缀），"同目录文件不存在"留给扫描——写索引行时报告可能还没落盘
            probs = index_problems(ipath, hook_mode=True)
            if probs:
                findings = [(os.path.abspath(ipath), probs)]
        elif path:
            probs = check(path, hook_mode=True)
            if probs:
                findings = [(os.path.abspath(path), probs)]
        elif root_arg:
            findings = fallback_scan(guess_root(root_arg))
        if not findings:
            return 0
        n = sum(len(pr) for _, pr in findings)
        head = (f"交接报告写后检查未通过（{n} 处；文件已写入，请就地修正后再交出）：" if len(findings) == 1
                else f"交接报告写后检查未通过（{len(findings)} 件 / {n} 处；文件已写入，请就地修正后再交出）：")
        body = []
        for p, probs in findings:
            if len(findings) > 1:
                body.append(os.path.basename(p) + "：")
            body += [f"- {x}" for x in probs]
        reason = head + "\n" + "\n".join(body) + "\n"
        if strict:
            sys.stderr.write(reason)
            return 2
        print(json.dumps({
            "decision": "block",
            "reason": reason,
            "systemMessage": (f"写后检查：{os.path.basename(findings[0][0])} {n} 处不合格" if len(findings) == 1
                              else f"写后检查：{len(findings)} 件 {n} 处不合格"),
        }, ensure_ascii=False))
        return 0

    files, idx, skipped = [], [], []
    if argv and argv[0] == "--scan":
        root = os.path.abspath(argv[1] if len(argv) > 1 and not argv[1].startswith("--") else ".")
        if not os.path.isdir(root):
            print(f"! 扫描目录不存在：{root}")
            return 2
        since_h, allf = 24.0, "--all" in argv
        if "--since" in argv:
            since_h = float(argv[argv.index("--since") + 1])
        cutoff = time.time() - since_h * 3600
        for p in glob.glob(os.path.join(root, "**", "*_交接报告.md"), recursive=True):
            if is_target(p) and (allf or os.path.getmtime(p) >= cutoff):
                files.append(os.path.abspath(p))
        # G8：索引 README 只查链接（同窗口口径；_archive 下的由 is_index 排除）
        for p in glob.glob(os.path.join(root, "**", "README.md"), recursive=True):
            if is_index(p) and (allf or os.path.getmtime(p) >= cutoff):
                idx.append(os.path.abspath(p))
    else:
        for a in argv:
            if a.startswith("--"):
                continue
            ap = os.path.abspath(a)
            if not os.path.isfile(ap):
                skipped.append(f"缺失（文件不存在）：{a}")
            elif is_target(ap):
                files.append(ap)
            elif is_index(ap):
                idx.append(ap)  # 显式指定索引 README：只做 G8
            else:
                skipped.append(f"跳过（不在检查范围：路径不含「工作传递」，或文件名既不以 _交接报告.md 结尾、也不是非 _archive 的 README.md）：{a}")
    bad, bad_idx, found = 0, 0, []
    for p in sorted(files):
        probs = check(p)
        if probs:
            bad += 1
            sys.stdout.write(fmt(p, probs))
            found.append((p, os.path.getmtime(p), [x for x in probs if not x.startswith("G6 ")]))  # 只滤跨机断链，G6P 反斜杠照报
    for p in sorted(idx):
        probs = index_problems(p)
        if probs:
            bad_idx += 1
            sys.stdout.write(fmt(p, probs))
            found.append((p, os.path.getmtime(p), probs))
    for s in skipped:
        print("! " + s)
    print(f"\n检查 {len(files)} 件，不合格 {bad} 件，通过 {len(files) - bad} 件" + (f"，未检查 {len(skipped)} 件。" if skipped else "。")
          + (f"\n索引 README {len(idx)} 份，链接不合格 {bad_idx} 份（G8）。" if idx else ""))
    bad += bad_idx
    todo_failed = False
    if "--todo" in argv and argv[0] == "--scan":
        out = argv[argv.index("--todo") + 1]
        writer = argv[argv.index("--writer") + 1] if "--writer" in argv and len(argv) > argv.index("--writer") + 1 else None
        res = todo_md(root, [f for f in found if f[2]], out, since_h if not allf else 24 * 365, writer)
        if res:
            print(f"待处理清单已写：{res}")
        else:
            print(f"! 待处理清单写入失败（目录不存在／只读／无权限）：{out}")  # 静默失败口，Codex 1557 §三.2
            todo_failed = True
    if skipped or todo_failed:
        return 2  # 任何显式指定却没查到的文件、清单写不出，都不算成功
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
