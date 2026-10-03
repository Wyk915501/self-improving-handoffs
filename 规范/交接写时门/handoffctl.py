#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""handoffctl.py —— 自我改进循环（交接写时门＋协作教训）的统一入口（2026-10-02 起）

为什么有它：原来这套是"几支脚本＋手抄的计划任务命令行＋散在 ~/.claude/tools/ 的状态文件"，装、看、修、卸都靠记性。
现在：一个入口、一个配置文件、一个运行目录；计划任务、钩子、处理页按钮全部跑**运行版**（install 时从正本测过再复制），
正本（docs/规范/交接写时门/，跨机同步）随便改都不会让本机的自动任务跑到半成品——改完 `promote` 才生效。

  status                     一屏看全：两个任务上次跑得怎样、积压、生效条数/上限、待你看的候选、表体检、运行版是否最新
  doctor                     体检（只读）：逐项 ✓/!/✗；退出码 0＝没有 ✗
  test                       跑五套回归测试（正本目录里的），打印被测文件的 SHA（LG-08）
  promote                    跑测试 → 全过才把正本复制进运行目录 bin/（MANIFEST.sha256 钉住每个文件）
  install [--dry-run]        建运行目录 ~/.claude/handoff/、迁移旧状态文件、写配置、promote、
                             把计划任务／Claude Code 钩子／ZCode 钩子／处理页协议改指运行版、计划任务允许电池运行与 90 分钟上限、
                             装 skill、最后跑 doctor。可重复执行（幂等）
  uninstall [--yes] [--purge] 删计划任务、协议、两处钩子、skill（不加 --yes 只打印要做什么）；状态与日志保留，--purge 才删运行目录
  run daily|check|publish|promote-rules|adopt-pool|scan|flow   手动跑一次（与计划任务同一入口、同一配置、同一把锁）；
                             run daily 跑完顺带巡检一轮（新规矩当场简述，不用等下一轮）
  veto LG-xx [理由] | confirm LG-xx | trust LG-xx --confirm-held | adopt RP-xx [--confirm-held] | drop RP-xx
  unveto LG-xx --confirm-held | undrop RP-xx --confirm-held
                             终端里的拍板（与处理页按钮同一套逻辑）。终端没有口令可核、谁都能敲：只在负责人当面明确要求时用；
                             署名"本机终端（未核实是谁敲的）"；放行"等负责人看一眼"的条目、或推翻负责人已做的决定（恢复不采纳、
                             恢复不用）都要 --confirm-held
  evidence-stats             证据主通道在真实树上的放行率（能认出原始事件的判决件占比）
  table-check                表体检：认不出的状态格、错列、编号重复、否决记录里不在表格内的行、生效版凭证
  logs [lessons|notify] [-n 40]   看日志尾巴
  config                     打印生效配置（默认值＋配置文件）与各文件位置
运行目录：~/.claude/handoff/{bin,state,logs,pages,config.json}；机密（GLM_API_KEY）只走环境变量，永不写进配置或日志。
"""
import io, os, sys, json, glob, shutil, subprocess, platform, hashlib, time, re
from datetime import datetime, timezone, timedelta

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import handoff_common as C  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
IS_WIN = platform.system() == "Windows"
# 测试与演练用：旧布局目录可改指临时目录；HANDOFF_NO_SYSTEM=1 时不动计划任务与注册表（测试里跑真 install 也碰不到真实系统）
LEGACY_DIR = os.environ.get("HANDOFF_LEGACY_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "tools")
NO_SYSTEM = os.environ.get("HANDOFF_NO_SYSTEM") == "1"
TASKS = (("HandoffDaily", "run daily", 90), ("HandoffNotify", "run check", 30))
SKILL_NAME = "handoff-loop"
TEST_SUITES = ("test_gate.py", "test_lessons.py", "test_notify.py", "test_ui.py", "test_flow.py", "test_ctl.py")


# ---------- 小工具 ----------
def canon():
    return C.canon_dir()


def project_root():
    return os.path.dirname(C.docs_root())


def bin_dir():
    return C.P.bin_dir


def pyw():
    p = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return p if os.path.exists(p) else sys.executable


def file_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 16), b""):
            h.update(b)
    return h.hexdigest()


def ps(script, timeout=60):
    """跑一段 PowerShell，返回 (退出码, 标准输出, 标准错误)。"""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=C.NO_WINDOW)
        return r.returncode, r.stdout or "", r.stderr or ""
    except Exception as e:
        return 1, "", f"{type(e).__name__}: {e}"


def psq(s):
    return "'" + str(s).replace("'", "''") + "'"


def manifest(d):
    out = {}
    for f in C.CODE_FILES:
        p = os.path.join(d, f)
        if os.path.isfile(p):
            out[f] = file_sha(p)
    return out


def drift():
    """正本与运行版不一致的文件（运行版不存在时返回 None）。"""
    b = bin_dir()
    if not os.path.isdir(b):
        return None
    mc, mb = manifest(canon()), manifest(b)
    return sorted(f for f in set(mc) | set(mb) if mc.get(f) != mb.get(f))


def load(p):
    return C.load_json(p, {}) or {}


def say(s=""):
    print(s)


# ---------- test / promote ----------
def run_tests(src=None, quiet=False):
    src = src or canon()
    res = []
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for t in TEST_SUITES:
        p = os.path.join(src, "tests", t)
        if not os.path.isfile(p):
            res.append((t, 2, "测试文件不存在"))
            continue
        try:
            r = subprocess.run([sys.executable, "-X", "utf8", "-B", p], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=600, env=env, creationflags=C.NO_WINDOW)
            m = re.search(r"合计 (\d+) 项，失败 (\d+) 项", r.stdout or "")
            fails = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip().startswith("FAIL")]
            summary = (f"{m.group(1)} 项，失败 {m.group(2)}" if m else "没读到汇总行") + (("：" + "；".join(fails[:3])) if fails else "")
            res.append((t, r.returncode, summary))
        except Exception as e:
            res.append((t, 2, f"{type(e).__name__}: {e}"))
    if not quiet:
        shas = manifest(src)
        for t, rc, s in res:
            say(f"  {'✓' if rc == 0 else '✗'} {t}：{s}")
        say("  被测文件 SHA（前 12 位）：" + "，".join(f"{k} {v[:12]}" for k, v in shas.items() if k.endswith((".py", ".ps1"))))
    return res, all(rc == 0 for _, rc, _ in res)


def cmd_test(args):
    _, ok = run_tests()
    return 0 if ok else 1


def promote(skip_tests=False, quiet=False):
    src, dst = canon(), bin_dir()
    if os.path.abspath(src) == os.path.abspath(dst):
        say("! 正本与运行目录是同一个位置，没法 promote")
        return 1
    if not skip_tests:
        say("跑回归测试（全过才部署）……")
        _, ok = run_tests(src, quiet=quiet)
        if not ok:
            say("✗ 有测试没过：运行版保持原样，没有部署")
            return 1
    missing = [f for f in C.CODE_FILES if not os.path.isfile(os.path.join(src, f))]
    if missing:
        say(f"✗ 正本缺文件：{missing}")
        return 1
    os.makedirs(dst, exist_ok=True)
    lines = []
    for f in C.CODE_FILES:
        s, d = os.path.join(src, f), os.path.join(dst, f)
        tmp = d + f".{os.getpid()}.tmp"
        shutil.copyfile(s, tmp)
        os.replace(tmp, d)
        lines.append(f"{file_sha(d)}  {f}")
    C.atomic_write(os.path.join(dst, "MANIFEST.sha256"), "\n".join(lines) + "\n", newline="\n")
    C.atomic_write(os.path.join(dst, "SOURCE"), os.path.abspath(src) + "\n", newline="\n")
    C.atomic_write(os.path.join(dst, "VERSION"), f"{C.SUITE_VERSION} · 部署于北京 {C.now_bj():%Y-%m-%d %H:%M}\n", newline="\n")
    say(f"✓ 已部署 {len(lines)} 个文件到 {dst}（MANIFEST.sha256 已写）")
    sk_src = os.path.join(src, "skill", "SKILL.md")
    sk_dst = os.path.join(project_root(), ".claude", "skills", SKILL_NAME, "SKILL.md")
    if os.path.isfile(sk_src) and os.path.isdir(os.path.dirname(sk_dst)):  # 装过 skill 才同步，没装过不替人装
        if not os.path.isfile(sk_dst) or file_sha(sk_src) != file_sha(sk_dst):
            shutil.copyfile(sk_src, sk_dst)
            say(f"✓ skill 操作手册已同步：{sk_dst}")
    return 0


def cmd_promote(args):
    return promote()


# ---------- install / uninstall ----------
def _backup(p):
    if not os.path.isfile(p):
        return None
    bdir = os.path.join(C.P.new_home, "backup")
    os.makedirs(bdir, exist_ok=True)
    dst = os.path.join(bdir, f"{os.path.basename(os.path.dirname(p))}_{os.path.basename(p)}.{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}")
    shutil.copy2(p, dst)
    return dst


def _gate_cmd_args(gate_path):
    return ["-X", "utf8", "-B", gate_path.replace("\\", "/"), "--hook"]


def update_claude_hook(gate_path, remove=False, dry=False):
    """项目级 .claude/settings.local.json 里的 PostToolUse 写后检查钩子：改指 gate_path（或摘掉）。别的钩子一个不碰。"""
    p = os.path.join(project_root(), ".claude", "settings.local.json")
    if not os.path.isfile(p):
        return "跳过（没有 .claude/settings.local.json）"
    d = json.load(io.open(p, encoding="utf-8"))
    hooks = (d.get("hooks") or {}).get("PostToolUse") or []
    found, changed = 0, False
    for entry in list(hooks):
        hs = entry.get("hooks") or []
        for h in list(hs):
            if "handoff_gate.py" in json.dumps(h, ensure_ascii=False):
                found += 1
                if remove:
                    hs.remove(h)
                    changed = True
                else:
                    want = _gate_cmd_args(gate_path)
                    if h.get("args") != want or h.get("command") != sys.executable.replace("\\", "/"):
                        h["command"], h["args"] = sys.executable.replace("\\", "/"), want
                        changed = True
        if remove and not hs:
            hooks.remove(entry)
    if not found and not remove:
        hooks.append({"matcher": "Write|Edit|MultiEdit", "hooks": [{"type": "command", "command": sys.executable.replace("\\", "/"),
                      "args": _gate_cmd_args(gate_path), "timeout": 20, "statusMessage": "交接报告写时门"}]})
        d.setdefault("hooks", {})["PostToolUse"] = hooks
        changed = True
    if not changed:
        return "已指向目标，无需改动"
    if dry:
        return "将改写（演练，未动）"
    bk = _backup(p)
    C.atomic_write(p, json.dumps(d, ensure_ascii=False, indent=2) + "\n", newline="\n")
    back = json.load(io.open(p, encoding="utf-8"))  # 回读确认（本机常有别的窗口改 settings）
    ok = ("handoff_gate.py" in json.dumps(back, ensure_ascii=False)) != remove
    return ("已改写" if ok else "✗ 回读没对上") + f"（备份 {bk}）"


def update_zcode_hook(gate_path, remove=False, dry=False):
    p = os.path.join(project_root(), ".zcode", "config.json")
    if not os.path.isfile(p):
        return "跳过（没有 .zcode/config.json）"
    d = json.load(io.open(p, encoding="utf-8"))
    evs = ((d.get("hooks") or {}).get("events") or {}).get("PostToolUse") or []
    changed = False
    for entry in list(evs):
        hs = entry.get("hooks") or []
        for h in list(hs):
            cmd = str(h.get("command", ""))
            if "handoff_gate.py" in cmd:
                if remove:
                    hs.remove(h)
                    changed = True
                    continue
                new = re.sub(r'"[^"]*handoff_gate\.py"', '"' + gate_path.replace("\\", "/") + '"', cmd)
                new = new.replace('-X utf8 "', '-X utf8 -B "') if " -B " not in new else new
                if new != cmd:
                    h["command"] = new
                    changed = True
        if remove and not hs:
            evs.remove(entry)
    if not changed:
        return "已指向目标，无需改动"
    if dry:
        return "将改写（演练，未动）"
    bk = _backup(p)
    C.atomic_write(p, json.dumps(d, ensure_ascii=False, indent=2) + "\n", newline="\n")
    back = C.read_text(p)  # 回读确认：ZCode 可能同时在写自己的配置
    ok = (gate_path.replace("\\", "/") in back) if not remove else ("handoff_gate.py" not in back)
    return ("已改写" if ok else "✗ 回读没对上（可能被 ZCode 同时改了），请重跑 install") + f"（备份 {bk}）"


def tasks_script(remove=False):
    """生成更新/删除两个计划任务的 PowerShell。已有任务只换动作与设置、保留原触发时刻（UTC 锚定，不随本机时区漂）。"""
    if remove:
        return "; ".join(f"Unregister-ScheduledTask -TaskName {psq(n)} -Confirm:$false -ErrorAction SilentlyContinue" for n, _, _ in TASKS)
    parts = [f"$pyw = {psq(pyw())}", f"$ctl = {psq(os.path.join(bin_dir(), 'handoffctl.py'))}"]
    for n, sub, lim in TASKS:
        trig = ("New-ScheduledTaskTrigger -Daily -At ([DateTime]::SpecifyKind([DateTime]'2026-01-01 01:00:00','Utc').ToLocalTime())"
                if n == "HandoffDaily" else
                "New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddHours(1) -RepetitionInterval (New-TimeSpan -Hours 4)")
        parts.append(
            f"$a = New-ScheduledTaskAction -Execute $pyw -Argument ('-X utf8 -B \"' + $ctl + '\" {sub}'); "
            f"$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable "
            f"-ExecutionTimeLimit (New-TimeSpan -Minutes {lim}) -MultipleInstances IgnoreNew; "
            f"if (Get-ScheduledTask -TaskName {psq(n)} -ErrorAction SilentlyContinue) "
            f"{{ Set-ScheduledTask -TaskName {psq(n)} -Action $a -Settings $s | Out-Null; 'updated {n}' }} "
            f"else {{ Register-ScheduledTask -TaskName {psq(n)} -Action $a -Settings $s -Trigger ({trig}) | Out-Null; 'created {n}' }}")
    return "; ".join(parts)


def preflight():
    """动手前的检查：有一项不过就不装（返回问题清单）。"""
    probs = []
    try:
        import yaml  # noqa: F401
    except Exception:
        probs.append(f"当前解释器 {sys.executable} 没装 PyYAML——钩子和任务会指向它，写后检查会全报 G1。换装了 PyYAML 的 Python 再跑")
    if IS_WIN and not os.path.exists(os.path.join(os.path.dirname(sys.executable), "pythonw.exe")):
        probs.append(f"{sys.executable} 旁边没有 pythonw.exe——计划任务会每轮闪一下控制台。换带 pythonw 的 Python 再跑")
    legacy_lock = os.path.join(LEGACY_DIR, "handoff_lessons.lock")
    for lp in (legacy_lock, C.P.lessons_lock):
        raw, pid, age = C.Lock(lp)._info()
        if raw is not None and pid and C.pid_alive(pid) and pid != os.getpid():
            probs.append(f"每日学习正在跑（进程 {pid} 持有 {lp}）——等它跑完再装，免得新旧两把锁同时放行")
    if IS_WIN and not NO_SYSTEM:
        rc, out, _ = ps("foreach ($n in @(" + ",".join(psq(n) for n, _, _ in TASKS) + ")) { $t = Get-ScheduledTask -TaskName $n "
                        "-ErrorAction SilentlyContinue; if ($t -and $t.State -eq 'Running') { $n } }")
        for n in [x.strip() for x in out.splitlines() if x.strip()]:
            probs.append(f"计划任务 {n} 正在运行——等它跑完再装")
    return probs


def _strip_secret_copy(path):
    """迁移后留底的旧看门狗状态里剥掉口令种子：种子只该有一份（复核 S-10）。"""
    try:
        d = C.load_json(path, None)
        if isinstance(d, dict) and d.pop("page_secret", None) is not None:
            C.save_json(path, d)
    except Exception:
        pass


def _migrate_copy(home, dry):
    """迁移第一段：旧布局的状态复制进运行目录并核哈希，原件一律不动。返回 (计划, 错误)。
    计划 = [(旧名, 原件, 现行位置, 复制时原件哈希)]，只含第二段要改名留底的状态文件。
    state/ 还不存在时先复制进 state.staging/，全部成功再整目录改名成 state/——中途失败只删暂存目录，
    resolve_paths 仍判旧布局（复核 R2-02：原来先建 state/ 再迁，回滚后所有进程悄悄改读空状态）。
    state/ 已存在（重装）时直接写进去：原件在改名留底前一直是权威，上次半途而废留下的副本照样覆盖；
    已留底过、原处又冒出来的不拿它覆盖现行状态。日志只在运行目录里还没有时复制，出错只提示。"""
    state = os.path.join(home, "state")
    staging = os.path.join(home, "state.staging")
    fresh = not os.path.isdir(state)
    tgt_state = staging if fresh else state
    plan, made, cur = [], [], None
    if not dry and fresh:
        shutil.rmtree(staging, ignore_errors=True)  # 上次崩掉留下的暂存目录从来没生效过，直接清
        os.makedirs(staging)
    try:
        for old, new in C.LEGACY_TO_NEW:
            po = os.path.join(LEGACY_DIR, old.replace("/", os.sep))
            if not os.path.isfile(po):
                continue
            is_state = new.startswith("state/")
            final = os.path.join(home, new.replace("/", os.sep))
            dst = os.path.join(tgt_state, new[len("state/"):].replace("/", os.sep)) if is_state else final
            if not is_state:  # 日志与图标：只在缺时复制；出错只提示（日志正被追加时哈希本来就会对不上）
                if os.path.isfile(final) or dry:
                    continue
                try:
                    os.makedirs(os.path.dirname(final), exist_ok=True)
                    shutil.copy2(po, final)
                except OSError as e:
                    say(f"  ! 复制 {old} 没成（不影响安装）：{e}")
                continue
            if glob.glob(glob.escape(po) + ".migrated-*"):
                say(f"  ! {old} 早已迁移留底、原处又出现一份：不拿它覆盖运行目录里的现行状态（真要用旧的请手工处理）")
                continue
            h = file_sha(po)
            plan.append((old, po, final, h))
            if dry:
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            cur = dst
            shutil.copy2(po, dst)
            made.append(dst)
            cur = None
            if file_sha(dst) != h:
                raise OSError(f"复制 {old} 后哈希对不上")
        if not dry and fresh:
            os.replace(staging, state)  # 这一刻起新代码才改读新布局
        return plan, None
    except OSError as e:
        if fresh:
            shutil.rmtree(staging, ignore_errors=True)
        else:
            for p in made + ([cur] if cur else []):
                try:
                    os.remove(p)
                except OSError:
                    pass
        return [], str(e)


def _migrate_finish(plan):
    """迁移第二段：原件改名为 *.migrated-日期 留底、留底副本剥掉口令种子。复制之后原件若又被旧任务写过
    （改任务那几秒里正好跑了一轮），先重新复制再改名。单个文件失败只记一句，下次 install 会再处理。"""
    stamp = f"{datetime.now(timezone.utc):%Y%m%d}"
    done, bad = [], []
    for old, po, pn, h in plan:
        try:
            if os.path.isfile(po) and file_sha(po) != h:
                shutil.copy2(po, pn)
                if file_sha(pn) != file_sha(po):
                    raise OSError("重新复制后哈希对不上")
            dst = po + f".migrated-{stamp}"
            if os.path.exists(dst):
                dst = po + f".migrated-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"
            os.replace(po, dst)
            if old.endswith("notify_state.json"):
                _strip_secret_copy(dst)
            done.append(old)
        except OSError as e:
            bad.append(f"{old}（{e}；原件还在，下次 install 会再处理）")
    return ("、".join(done) or "无") + ("；没改成：" + "、".join(bad) if bad else "") \
        + ("（口令种子已从留底副本里剥掉）" if any(o.endswith("notify_state.json") for o in done) else "")


def cmd_install(args):
    dry = "--dry-run" in args
    tag = "（演练，不动手）" if dry else ""
    home = C.P.new_home
    say(f"== 安装自我改进循环{tag}：运行目录 {home}")
    probs = preflight()
    if probs:
        for p in probs:
            say(f"  ✗ {p}")
        if not dry:
            say("== 没有安装：先解决上面的问题")
            return 1
    # ① 先测试、部署运行版代码：只建 bin/，不建 state/——state/ 一出现新代码就改读新布局；测试不过时旧布局一点没动
    if dry:
        say("  · 将跑五套测试，全过才复制正本到 bin/")
    else:
        os.makedirs(os.path.join(home, "bin"), exist_ok=True)
        if promote() != 0:
            say("== 没有安装：测试没全过，旧状态、钩子与计划任务都没动")
            return 1
    # ② 迁移第一段：复制并核哈希，原件不动（计划任务改指运行版之前，旧任务仍读写原件，原件是权威）
    plan, err = _migrate_copy(home, dry)
    if err:
        say(f"  ✗ 迁移中途失败：{err}——本次复制的已删掉、暂存目录已清，原件没动，还是旧布局，什么都没改")
        return 1
    for d in ("logs", "pages"):
        if not dry:
            os.makedirs(os.path.join(home, d), exist_ok=True)
    names = [old for old, _, _, _ in plan]
    say(f"  {'✓' if not dry else '·'} 运行目录与状态{'就位' if not dry else '将就位'}：{'复制了 ' + '、'.join(names) if names else '没有需要迁移的旧状态'}"
        + ("（原件等计划任务改指运行版后再改名留底）" if names and not dry else ""))
    cfgp = os.path.join(home, "config.json")
    if not os.path.isfile(cfgp):
        sparse = {"_说明": "这里只写本机要改的项；没写的用 handoff_common.py 里 DEFAULT_CONFIG 的默认值。改完下一轮自动生效。"
                          "GLM_API_KEY 之类的机密不要写进来。",
                  "paths": {"docs_root": C.docs_root().replace("\\", "/"), "table": C.table_path().replace("\\", "/")},
                  "lessons": {"provider": C.cfg("lessons", "provider", "glm")}}
        if not dry:
            C.atomic_write(cfgp, json.dumps(sparse, ensure_ascii=False, indent=2) + "\n", newline="\n")
        say(f"  {'✓' if not dry else '·'} 配置文件 {cfgp}（只写本机路径与提名模型，其余默认）")
    else:
        say(f"  ✓ 配置文件已存在，不覆盖：{cfgp}")
    gate_bin = os.path.join(bin_dir(), "handoff_gate.py")
    say(f"  {'·' if dry else '✓'} Claude Code 写后检查钩子：{update_claude_hook(gate_bin, dry=dry)}")
    say(f"  {'·' if dry else '✓'} ZCode 写后检查钩子：{update_zcode_hook(gate_bin, dry=dry)}")
    if IS_WIN:
        if dry:
            say("  · 将更新计划任务 HandoffDaily／HandoffNotify：动作改跑运行版 handoffctl，允许电池启动与运行、上限 90／30 分钟，保留原触发时刻")
            say("  · 将重新注册处理页按钮协议 handoff-rule: 指向运行版")
        else:
            rc, out, err = (0, "跳过（HANDOFF_NO_SYSTEM=1）", "") if NO_SYSTEM else ps(tasks_script())
            say(f"  {'✓' if rc == 0 else '✗'} 计划任务：{(out.strip() or err.strip())[:200]}")
            if rc != 0:
                say("== 没装完：计划任务没改成，旧任务仍跑旧脚本、旧状态原件没动（运行目录里只是副本）。修好后重跑 install")
                return 1
            r = subprocess.run([sys.executable, "-X", "utf8", "-B", os.path.join(bin_dir(), "handoff_notify.py"), "register",
                                "--table", C.table_path()], capture_output=True, text=True, encoding="utf-8", errors="replace",
                               creationflags=C.NO_WINDOW)
            say(f"  {'✓' if r.returncode == 0 else '✗'} 处理页按钮协议：{'已指向运行版' if r.returncode == 0 else (r.stdout + r.stderr)[-200:]}")
    if not dry and plan:
        # ③ 迁移第二段：计划任务已改指运行版，原件改名留底（留底副本剥掉口令种子）
        say(f"  ✓ 旧状态原件留底：{_migrate_finish(plan)}")
    else:
        say("  · Linux：不装每日学习与弹窗（单一发布者在 Windows）。兜底扫描 cron 建议改成：")
        say(f"      17 */4 * * *  flock -n /tmp/handoff_scan.lock timeout 600 python3 -X utf8 -B {os.path.join(bin_dir(), 'handoffctl.py')} run scan")
    src_skill = os.path.join(canon(), "skill", "SKILL.md")
    dst_skill = os.path.join(project_root(), ".claude", "skills", SKILL_NAME, "SKILL.md")
    if os.path.isfile(src_skill):
        if not dry:
            os.makedirs(os.path.dirname(dst_skill), exist_ok=True)
            shutil.copyfile(src_skill, dst_skill)
        say(f"  {'✓' if not dry else '·'} skill：{dst_skill}")
    if dry:
        say("== 演练结束：什么都没改。去掉 --dry-run 正式执行")
        return 0
    say("== 体检：")
    r = subprocess.run([sys.executable, "-X", "utf8", "-B", os.path.join(bin_dir(), "handoffctl.py"), "doctor"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=C.NO_WINDOW)
    print(r.stdout)
    return r.returncode


def cmd_uninstall(args):
    yes, purge = "--yes" in args, "--purge" in args
    say("== 卸载自我改进循环" + ("" if yes else "（没加 --yes：只列出要做什么，什么都不改）"))
    plan = ["删计划任务 HandoffDaily、HandoffNotify", "删处理页按钮协议 handoff-rule:",
            "从 .claude/settings.local.json 与 .zcode/config.json 摘掉写后检查钩子（先备份）",
            f"删 skill {os.path.join(project_root(), '.claude', 'skills', SKILL_NAME)}"]
    if purge:
        plan.append(f"删运行目录 {C.P.new_home}（状态、日志、处理页一并删除）")
    else:
        plan.append(f"保留运行目录 {C.P.new_home} 里的状态与日志（--purge 才删）")
    for p in plan:
        say("  · " + p)
    if not yes:
        return 0
    if IS_WIN:
        if not NO_SYSTEM:
            ps(tasks_script(remove=True))
        if not NO_SYSTEM:
            ps("Remove-Item -Path 'HKCU:\\Software\\Classes\\handoff-rule' -Recurse -ErrorAction SilentlyContinue")
    say("  " + update_claude_hook("", remove=True))
    say("  " + update_zcode_hook("", remove=True))
    shutil.rmtree(os.path.join(project_root(), ".claude", "skills", SKILL_NAME), ignore_errors=True)
    if purge:
        home = C.P.new_home
        looks_right = os.path.basename(os.path.normpath(home)) == "handoff" and (
            os.path.isdir(os.path.join(home, "state")) or os.path.isfile(os.path.join(home, "bin", "MANIFEST.sha256")))
        if looks_right:
            shutil.rmtree(home, ignore_errors=True)
        else:
            say(f"  ✗ {home} 看着不像运行目录（名字不叫 handoff，或里面没有 state/、bin/MANIFEST.sha256），没删")
    say("== 卸载完成。正本代码与 docs 里的教训表、否决记录一个字没动。")
    return 0


# ---------- run / 拍板 ----------
def _lessons():
    import handoff_lessons as L
    return L


def _notify():
    import handoff_notify as N
    return N


def _check_argv(table, docs):
    return ["check", table, "--with-scan", os.path.join(docs, "工作传递"), "--scan-hours", str(C.cfg("notify", "scan_hours", 8)),
            "--with-flow", docs, "--flow-days", str(C.cfg("notify", "flow_days", 2))]


def cmd_run(args):
    if not args:
        say(__doc__)
        return 2
    sub, table, docs = args[0], C.table_path(), C.docs_root()
    rest = args[1:]
    if sub == "daily":
        argv = ["daily", table, "--docs", docs, "--provider", C.cfg("lessons", "provider", "glm")]
        if C.cfg("lessons", "model"):
            argv += ["--model", C.cfg("lessons", "model")]
        rc = _lessons().run_cli(argv + rest)
        try:  # 学完当场巡检一轮：新规矩马上简述给负责人（以前要等下一轮巡检，实测最长 20 小时）；它不冒充巡检心跳
            _notify().run_main(_check_argv(table, docs) + ["--source", "daily"])
        except Exception as e:
            say(f"! 学完顺带的巡检没跑成（不影响每日学习本身）：{type(e).__name__}: {e}")
        return rc
    if sub in ("publish", "adopt-pool"):
        return _lessons().run_cli([sub, table])
    if sub == "promote-rules":
        return _lessons().run_cli(["promote", table])
    if sub == "check":
        # 计划任务用 pythonw 起；手动跑一轮记成 manual，不冒充计划任务那一轮的心跳（复核 C-06）
        src = [] if "--source" in rest else ["--source", "task" if os.path.basename(sys.executable).lower().startswith("pythonw")
                                             else "manual"]
        return _notify().run_main(_check_argv(table, docs) + src + rest)
    if sub == "scan":
        import handoff_gate as G
        wt = os.path.join(docs, "工作传递")
        todo = os.path.join(wt, C.TODO_NAME if IS_WIN else C.TODO_NAME.replace(".md", "-US3.md"))
        return G.main(["--scan", wt, "--since", "8", "--todo", todo, "--writer", f"handoffctl run scan（{platform.node()}）"] + rest)
    if sub == "flow":
        import handoff_flow as F
        todo = os.path.join(docs, "工作传递", C.FLOW_TODO_NAME if IS_WIN else C.FLOW_TODO_NAME.replace(".md", "-US3.md"))
        return F.main(["handoff_flow.py", "scan", docs, "--todo", todo, "--writer", f"handoffctl run flow（{platform.node()}）"] + rest)
    say(f"不认识的 run 子命令：{sub}")
    return 2


def cmd_decide(act, args):
    """终端拍板。终端没有口令可核，谁都能敲——所以 skill 规定只在负责人当面明确要求时才执行；署名写"未核实是谁敲的"；
    采纳一条按规定要负责人点头的候选（hold）还要多加 --confirm-held。"""
    flags = [a for a in args if a.startswith("--")]
    rest = [a for a in args if not a.startswith("--")]
    if not rest:
        say(f"用法：handoffctl.py {act} <编号>" + (" [理由]" if act == "veto" else "")
            + (" [--confirm-held]" if act == "adopt" else "")
            + (" --confirm-held" if act in ("unveto", "undrop", "confirm") else "")
            + ("（trust 可一次给多个编号）--confirm-held" if act == "trust" else ""))
        return 2
    if act not in ("trust", "veto") and len(rest) > 1:  # 复核 C-12：以前多给的编号被当成理由静默吞掉
        say(f"一次只给一个编号（{act} 不带理由）：收到 {' '.join(rest)}")
        return 2
    mapping = {"veto": "no", "confirm": "ok", "adopt": "adopt", "drop": "drop", "trust": "trust", "unveto": "unveto",
               "undrop": "undrop"}
    N = _notify()
    N.toast = lambda *a, **k: True  # 终端里操作：结果直接打印，不再弹窗
    if act == "trust":  # 被扣下的行必然带硬拒因：先把全文与原因摆出来，没有 --confirm-held 不动（复核 R2-03）
        held = (C.load_json(C.P.lessons_state, {}) or {}).get("untrusted") or {}
        rc = 0
        for oid in [x.strip().upper() for x in rest]:
            info = held.get(oid)
            say(f"  {oid}：" + (f"「{info.get('rule', '')}」——{info.get('reasons', '')}（{info.get('since', '?')} 起扣下）" if info
                               else "不在「等负责人确认」清单里"))
            if not info:
                rc = 2
                continue
            if "--confirm-held" not in flags:
                say("  ✗ 没有改动：确认要加 --confirm-held——只有负责人当面点名这一条时才加")
                rc = 2
                continue
            r = N.decide(f"trust/{oid}", C.table_path(), who="本机终端（handoffctl，未核实是谁敲的）",
                         require_token=False, allow_held=True)
            say(("  ✓ 已确认生效" if r == 0 else "  ✗ 没有改动") + f"（详情见看门狗日志 {C.P.notify_log}）")
            rc = rc or r
        return rc
    oid = rest[0].strip().upper()
    why = " ".join(rest[1:]).strip() or None
    rc = N.decide(f"{mapping[act]}/{oid}", C.table_path(), who="本机终端（handoffctl，未核实是谁敲的）",
                  require_token=False, reason=why, allow_held="--confirm-held" in flags)
    if rc != 0 and act in ("adopt", "unveto", "undrop", "confirm") and "--confirm-held" not in flags:
        say("  （放行「等负责人看一眼」的候选、恢复负责人不采纳／不用过的条目、或把新规矩标成看过了（负责人就收不到简述了）："
            "只有负责人当面明确同意时，才加 --confirm-held 重跑）")
    say(("✓ 完成" if rc == 0 else "✗ 没有改动") + f"（{act} {oid}；详情见看门狗日志 {C.P.notify_log}）")
    return rc


def cmd_evidence_stats(args):
    """「≥2 个原始事件」主通道在真实树上的放行率：评审方判决件里，有多少份能认出它评的那件原件（复核 N-07）。"""
    L = _lessons()
    docs = C.docs_root()
    ids, by_name, by_path = L.known_report_index(docs)
    n = has = ok_ = 0
    import glob
    for p in glob.glob(os.path.join(docs, "工作传递", "**", "*_交接报告.md"), recursive=True):
        if L.is_archived(p) or L.source_dir_of(p) not in C.SOURCES:
            continue
        n += 1
        try:
            fm = C.fm_dict(C.read_text(p))
        except (OSError, ValueError):
            continue
        cands = L.event_candidates(fm)
        if cands:
            has += 1
            if L.resolve_events(cands, ids, by_name, by_path, p, docs):
                ok_ += 1
    say(f"评审方判决件 {n} 份：frontmatter 写了事件字段的 {has} 份，能认出原件的 {ok_} 份（{ok_ * 100 // max(1, n)}%）。"
        "认不出的多半是只引了别的判决件。证据门槛只决定候选走直通还是走被拒候选池，不单独决定生不生效。")
    return 0



# ---------- status / doctor / table-check ----------
def _tasks_info():
    if not IS_WIN:
        return {}
    script = ("foreach ($n in @(" + ",".join(psq(n) for n, _, _ in TASKS) + ")) { "
              "$t = Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue; "
              "if (-not $t) { $n + '|missing'; continue }; $i = $t | Get-ScheduledTaskInfo; $a = $t.Actions | Select-Object -First 1; "
              "$lr = if ($i.LastRunTime -and $i.LastRunTime.Year -gt 2000) { $i.LastRunTime.ToUniversalTime().ToString('o') } else { '' }; "
              "$nr = if ($i.NextRunTime -and $i.NextRunTime.Year -gt 2000) { $i.NextRunTime.ToUniversalTime().ToString('o') } else { '' }; "
              "$n + '|' + $t.State + '|' + $a.Execute + '|' + $a.Arguments + '|' + $t.Settings.DisallowStartIfOnBatteries + '|' + "
              "$t.Settings.StopIfGoingOnBatteries + '|' + $t.Settings.ExecutionTimeLimit + '|' + $i.LastTaskResult + '|' + $lr + '|' + $nr }")
    rc, out, _ = ps(script)
    info = {}
    for ln in out.splitlines():
        parts = ln.strip().split("|")
        if len(parts) >= 2 and parts[1] == "missing":
            info[parts[0]] = None
        elif len(parts) >= 10:
            info[parts[0]] = {"state": parts[1], "exe": parts[2], "args": parts[3], "no_battery_start": parts[4] == "True",
                              "stop_on_battery": parts[5] == "True", "limit": parts[6],
                              "last_result": int(parts[7]) if parts[7].lstrip("-").isdigit() else None,
                              "last_run": parts[8], "next_run": parts[9]}
    return info


def _table_view():
    table = C.table_path()
    text = C.read_text(table)
    vetoed = C.veto_ids(table)
    rows = [C.cells_of(ln) for _, ln in C.table_rows(text)]
    live = [c for c in rows if len(c) >= 5 and c[1].startswith("生效") and c[0] not in vetoed]
    pend = [c for c in rows if len(c) >= 5 and C.status_kind(c[1]) == "pending"]
    now = C.now_bj()
    recent = []
    for c in live:
        m = C.ADDED_ANY.search(c[4])
        if m:
            try:
                ad = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=C.BJ)
            except ValueError:
                continue
            if now - ad <= timedelta(days=int(C.cfg("notify", "recent_days", 7))):
                recent.append((c[0], c[2], m.group(1), m.group(2)))
    pub = os.path.join(os.path.dirname(table), C.PUBLISH_NAME)
    pub_text = C.read_text(pub) if os.path.isfile(pub) else ""
    mm = re.search(r"表哈希 ([0-9a-f]{8})(?: · 否决哈希 ([0-9a-f]{8}))?", pub_text)
    cred_ok = bool(mm and mm.group(1) == C.sha(text)[:8] and mm.group(2) == C.veto_hash(table))
    return {"text": text, "rows": rows, "live": live, "pending": pend, "vetoed": vetoed, "recent": recent,
            "lint": C.lint_table(text, pub_text), "cred_ok": cred_ok, "stray": C.parse_veto(C.veto_text(table))[1]}


_BAD_BYTES = "教训表或否决记录里有不是 UTF-8 的坏字节（多半是用 PowerShell 的 Set-Content／Add-Content 写过）"


def _hb_check(ns, now):
    """doctor 的「看门狗最近一轮」：只认计划任务那一轮（common.task_heartbeat）；4 小时一轮，跳过一轮也不误报。返回 (级别, 说明)。"""
    lc_at = C.to_bj(C.task_heartbeat(ns).get("utc"))
    return ("✓" if lc_at and now - lc_at < timedelta(hours=9) else "!"), (f"北京 {lc_at:%m-%d %H:%M}" if lc_at
                                                                          else "没有记录（升级后第一轮还没跑）")


def cmd_status(args):
    ls, ns = load(C.P.lessons_state), load(C.P.notify_state)
    try:
        tv = _table_view()
    except UnicodeDecodeError as e:
        say(f"✗ {_BAD_BYTES}：{e}")
        return 1
    lr, lst, lc = ls.get("last_run") or {}, ls.get("last_start") or {}, C.task_heartbeat(ns)
    pool = (load(C.P.pool).get("items") or [])
    pend_pool = [x for x in pool if str(x.get("status", "pending")) == "pending"]
    held = [x for x in pend_pool if x.get("hold")]
    say(f"自我改进循环 · 状态（北京 {C.now_bj():%Y-%m-%d %H:%M}；套件 {C.SUITE_VERSION}；"
        f"{'已安装运行版' if C.P.layout == 'installed' else '未安装（直接跑正本）'}）")
    say(f"  每日学习：上次开跑 {C.bj_str(lst.get('utc'))}，上次结束 {C.bj_str(lr.get('utc'))}，"
        f"结果 {'正常' if lr.get('rc') == 0 else ('退出码 ' + str(lr.get('rc')) + '：' + str(lr.get('error') or '')[:80]) if lr else '无记录'}；"
        f"待读积压 {len(ls.get('pending') or [])} 件")
    ld = ns.get("last_check") or {}
    say(f"  看门狗：上次计划任务巡检 {C.bj_str(lc.get('utc'))}"
        + (f"（每日学习跑完顺带的一轮在 {C.bj_str(ld.get('utc'))}）" if ld.get("source") == "daily" else ""))
    for n, inf in _tasks_info().items():
        if inf is None:
            say(f"  计划任务 {n}：✗ 不存在")
        else:
            kind, meaning = C.task_result_meaning(inf["last_result"])
            say(f"  计划任务 {n}：{inf['state']}，上次 {C.bj_str(inf['last_run'])}（{meaning}），下次 {C.bj_str(inf['next_run'])}")
    say(f"  教训表：生效 {len(tv['live'])} 条 / 上限 {C.cfg('lessons', 'total_cap', 40)}；遗留拟生效 {len(tv['pending'])}；"
        f"已否决 {len(tv['vetoed'])}；生效版凭证{'一致' if tv['cred_ok'] else '✗ 不一致（下一轮看门狗会自动重发布）'}")
    if tv["recent"]:
        say(f"  最近 {C.cfg('notify', 'recent_days', 7)} 天新生效 {len(tv['recent'])} 条：")
        for lid, rule, at, how in tv["recent"]:
            say(f"    {lid}（{at} {how}）{rule}")
    untr = ls.get("untrusted") or {}
    if untr:
        say(f"  ✗ 表里冒出 {len(untr)} 条不是本机流程加的规矩，先没放进生效版：" +
            "；".join(f"{k} {str(v.get('rule'))[:24]}（{v.get('reasons')}）" for k, v in sorted(untr.items())[:3])
            + "——处理页上「确认生效」或「不采纳」")
    say(f"  被拒候选池：待处理 {len(pend_pool)} 条，其中等你点「采纳」的 {len(held)} 条"
        + ("：" + "；".join(f"{x.get('id')} {str(x.get('rule'))[:30]}（{x.get('hold')}）" for x in held[:3]) if held else ""))
    if tv["lint"] or tv["stray"]:
        say("  ✗ 表体检：" + "；".join(f"{a} {b[:50]}" for a, b in tv["lint"][:3])
            + ("；否决记录有不在表格里的行：" + "；".join(tv["stray"][:2]) if tv["stray"] else ""))
    d = drift()
    if d is None:
        say("  运行版：未安装（跑 handoffctl.py install）")
    elif d:
        say(f"  ! 运行版落后于正本：{', '.join(d)} 不一致——改完测过了就跑 handoffctl.py promote")
    else:
        say("  运行版：与正本一致")
    return 0


def cmd_doctor(args):
    res = []

    def chk(level, item, detail=""):
        res.append((level, item, detail))

    chk("✓" if sys.version_info >= (3, 10) else "✗", "Python 版本", sys.version.split()[0])
    try:
        import yaml  # noqa: F401
        chk("✓", "PyYAML", "可用")
    except Exception:
        chk("✗", "PyYAML", "缺失：写后检查会 fail-closed（pip install pyyaml）")
    chk("✓" if C.P.layout == "installed" else "!", "运行目录",
        C.P.home + ("" if C.P.layout == "installed" else "（旧布局：还没 install）"))
    try:
        C.load_json(C.P.config, {})
        chk("✓", "配置文件", C.P.config if os.path.isfile(C.P.config) else "没有（全用默认值）")
    except Exception as e:
        chk("✗", "配置文件", f"读不出：{e}")
    table, docs = C.table_path(), C.docs_root()
    chk("✓" if os.path.isfile(table) else "✗", "教训表", table)
    d = drift()
    if d is None:
        chk("!", "运行版", "未部署（install 或 promote）")
    else:
        b = bin_dir()
        mf = os.path.join(b, "MANIFEST.sha256")
        bad = []
        if os.path.isfile(mf):
            for ln in C.read_text(mf).splitlines():
                parts = ln.split("  ", 1)
                if len(parts) == 2 and (not os.path.isfile(os.path.join(b, parts[1])) or file_sha(os.path.join(b, parts[1])) != parts[0]):
                    bad.append(parts[1])
        chk("✗" if bad else "✓", "运行版完整性（MANIFEST）", "被改动或缺失：" + ", ".join(bad) if bad else "与部署时一致")
        chk("!" if d else "✓", "运行版与正本", ("正本较新未部署：" + ", ".join(d)) if d else "一致")
    if IS_WIN:
        infos = _tasks_info()
        for n, sub, lim in TASKS:
            inf = infos.get(n)
            if inf is None:
                chk("✗", f"计划任务 {n}", "不存在")
                continue
            probs = []
            if inf["state"] == "Disabled":
                probs.append("被禁用")
            if "handoffctl.py" not in inf["args"] or os.path.normcase(bin_dir()) not in os.path.normcase(inf["args"]):
                probs.append("动作没指向运行版 handoffctl")
            if inf["no_battery_start"] or inf["stop_on_battery"]:
                probs.append("用电池时不启动／会被停")
            kind, meaning = C.task_result_meaning(inf["last_result"])
            if kind == "fail":
                probs.append(f"上次结果：{meaning}")
            chk("!" if probs else "✓", f"计划任务 {n}", "；".join(probs) if probs else f"正常；下次 {C.bj_str(inf['next_run'])}")
        N = _notify()
        cur = N.current_protocol_command() or ""
        m = re.search(r'"([^"]+handoff_notify\.py)"', cur)
        if not cur:
            chk("!", "处理页按钮协议", "没注册（页面按钮点不了）")
        elif not (m and os.path.isfile(m.group(1))):
            chk("✗", "处理页按钮协议", f"指向的脚本不存在：{cur[:120]}")
        else:
            tbl_ok = os.path.normcase(os.path.abspath(table)) in os.path.normcase(cur)
            to_bin = os.path.normcase(bin_dir()) in os.path.normcase(m.group(1))
            chk("✓" if tbl_ok and to_bin else "!", "处理页按钮协议",
                ("指向运行版" if to_bin else "指向正本（install 后应指运行版）") + ("" if tbl_ok else "；--table 不是配置里的教训表"))
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                has_key = bool(winreg.QueryValueEx(k, "GLM_API_KEY")[0])
        except OSError:
            has_key = bool(os.environ.get("GLM_API_KEY"))
        chk("✓" if has_key else "✗", "GLM_API_KEY（用户环境变量）", "有（不显示值）" if has_key else "没有：每日学习调不了模型")
        if C.cfg("lessons", "glm_via", "claude-code") == "claude-code":
            exe = C.cfg("lessons", "claude_exe", "") or shutil.which("claude")
            real = _lessons()._resolve_exe(exe) if exe else None
            shim = bool(real) and real.lower().endswith((".cmd", ".bat"))  # 认不出垫片旁的 claude.exe：超时杀不到它（R2-2-6）
            chk("✗" if not exe else ("!" if shim else "✓"), "Claude Code（每日学习经它调 GLM，智谱 Coding Plan 只能在官方支持的工具里用）",
                (real + ("——是 npm 之类的垫片、旁边没找到 claude.exe：调用超时时可能杀不到真正的进程，"
                         "在 config.json 的 lessons.claude_exe 写 claude.exe 的完整路径" if shim else "")) if exe
                else "找不到 claude：装好 Claude Code，或在 config.json 的 lessons.claude_exe 写明路径")
        else:
            chk("!", "GLM 调用方式", "直连按量计费的标准端点（花账户余额）；默认应是经 Claude Code（lessons.glm_via=claude-code）")
    for name, p, key in (("Claude Code 写后检查钩子", os.path.join(project_root(), ".claude", "settings.local.json"), "handoff_gate.py"),
                         ("ZCode 写后检查钩子", os.path.join(project_root(), ".zcode", "config.json"), "handoff_gate.py")):
        if not os.path.isfile(p):
            chk("!", name, f"没有配置文件 {p}")
            continue
        txt = C.read_text(p)
        paths = re.findall(r'([A-Za-z]:[/\\][^"\']*?handoff_gate\.py|/[^"\']*?handoff_gate\.py)', txt)
        if not paths:
            chk("!", name, "没配写后检查")
        elif not all(os.path.isfile(x) for x in paths):
            chk("✗", name, "指向的脚本不存在：" + paths[0])
        else:
            to_bin = all(os.path.normcase(bin_dir()) in os.path.normcase(os.path.abspath(x)) for x in paths)
            chk("✓" if to_bin else "!", name, "指向运行版" if to_bin else "指向正本（install 后应指运行版）")
    sk_src = os.path.join(canon(), "skill", "SKILL.md")
    sk_dst = os.path.join(project_root(), ".claude", "skills", SKILL_NAME, "SKILL.md")
    if os.path.isfile(sk_src):
        if not os.path.isfile(sk_dst):
            chk("!", "skill", "没装（install 会装）")
        else:
            chk("✓" if file_sha(sk_src) == file_sha(sk_dst) else "!", "skill", "与正本一致" if file_sha(sk_src) == file_sha(sk_dst) else "落后于正本（promote 或 install 会更新）")
    cm = os.path.join(project_root(), ".claude", "CLAUDE.md")
    chk("✓" if os.path.isfile(cm) and C.PUBLISH_NAME in C.read_text(cm) else "!", "CLAUDE.md 引入生效版",
        "已引入" if os.path.isfile(cm) and C.PUBLISH_NAME in C.read_text(cm) else "没找到对生效版的引用")
    try:
        tv = _table_view()
        chk("✗" if tv["lint"] else "✓", "教训表体检", "；".join(f"{a} {b[:40]}" for a, b in tv["lint"][:3]) if tv["lint"] else f"生效 {len(tv['live'])} 条，格式都认得")
        chk("✓" if tv["cred_ok"] else "!", "生效版凭证（表哈希＋否决哈希）", "一致" if tv["cred_ok"] else "不一致：下一轮看门狗会重发布，或手动 run publish")
        if tv["stray"]:
            chk("!", "否决记录", "有不在表格里的 LG 行（不计入否决）：" + "；".join(tv["stray"][:2]))
    except UnicodeDecodeError as e:
        chk("✗", "教训表体检", f"{_BAD_BYTES}：{e}")
    except OSError as e:
        chk("✗", "教训表体检", f"读不了：{e}")
    ls, ns = load(C.P.lessons_state), load(C.P.notify_state)
    now = datetime.now(timezone.utc)
    lr, lc = ls.get("last_run") or {}, C.task_heartbeat(ns)  # 只认计划任务那一轮巡检
    lr_at, lc_at = C.to_bj(lr.get("utc")), C.to_bj(lc.get("utc"))
    if IS_WIN:
        chk("✓" if lr_at and now - lr_at < timedelta(hours=26) and lr.get("rc") == 0 else "!", "每日学习最近一轮",
            f"北京 {C.bj_str(lr.get('utc'))}，退出码 {lr.get('rc')}" if lr_at else "没有记录")
        _lv, _dt = _hb_check(ns, now)
        chk(_lv, "看门狗最近一轮", _dt)
    lk = C.Lock(C.P.lessons_lock)
    raw, pid, age = lk._info()
    if raw is not None:
        chk("!" if (pid and not C.pid_alive(pid)) or (age or 0) > 6000 else "✓", "每日学习锁",
            f"被进程 {pid} 占用 {int((age or 0) // 60)} 分钟" + ("（进程已不在：下一轮会自动清）" if pid and not C.pid_alive(pid) else ""))
    for name, p in (("每日学习日志", C.P.lessons_log), ("看门狗日志", C.P.notify_log)):
        if os.path.isfile(p):
            kb = os.path.getsize(p) // 1024
            chk("✓" if kb < 4096 else "!", name, f"{kb} KB（超过 {C.cfg('log', 'rotate_kb', 1024)} KB 自动轮转）")
    tz = time.strftime("%z")
    chk("✓", "本机时区", f"{time.tzname[0]}（UTC{tz[:3]}:{tz[3:]}）——所有显示都已换算成北京时间")
    for level, item, detail in res:
        say(f"  {level} {item}：{detail}")
    nbad = sum(1 for r in res if r[0] == "✗")
    nwarn = sum(1 for r in res if r[0] == "!")
    say(f"体检：{len(res)} 项，✗ {nbad} 项，! {nwarn} 项")
    return 1 if nbad else 0


def cmd_table_check(args):
    try:
        tv = _table_view()
    except UnicodeDecodeError as e:
        say(f"✗ {_BAD_BYTES}：{e}")
        return 1
    if not tv["lint"] and not tv["stray"]:
        say(f"✓ 教训表 {len(tv['rows'])} 行格式都认得；生效 {len(tv['live'])} 条；凭证{'一致' if tv['cred_ok'] else '不一致'}")
        return 0
    for a, b in tv["lint"]:
        say(f"✗ {a}：{b}")
    for s in tv["stray"]:
        say(f"! 否决记录里不在表格内（不计入）：{s}")
    return 1


def cmd_logs(args):
    which = args[0] if args and not args[0].startswith("-") else "notify"
    n = int(args[args.index("-n") + 1]) if "-n" in args and len(args) > args.index("-n") + 1 else 40
    p = C.P.lessons_log if which.startswith("l") else C.P.notify_log
    if not os.path.isfile(p):
        say(f"没有日志：{p}")
        return 1
    lines = C.read_text(p).splitlines()
    say(f"== {p}（最后 {n} 行，共 {len(lines)} 行）")
    for ln in lines[-n:]:
        say(ln)
    return 0


def cmd_config(args):
    say(json.dumps({"运行布局": C.P.layout, "运行目录": C.P.home, "配置文件": C.P.config, "正本目录": canon(),
                    "docs 根": C.docs_root(), "教训表": C.table_path(), "生效配置": C.CONFIG}, ensure_ascii=False, indent=2))
    return 0


COMMANDS = {
    "status": cmd_status, "doctor": cmd_doctor, "test": cmd_test, "promote": cmd_promote, "install": cmd_install,
    "uninstall": cmd_uninstall, "run": cmd_run, "table-check": cmd_table_check,
    "logs": cmd_logs, "config": cmd_config,
}


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        say(__doc__)
        return 0 if argv else 2
    cmd, args = argv[0], argv[1:]
    if cmd in ("veto", "confirm", "adopt", "drop", "trust", "unveto", "undrop"):
        return cmd_decide(cmd, args)
    if cmd == "evidence-stats":
        return cmd_evidence_stats(args)
    fn = COMMANDS.get(cmd)
    if not fn:
        say(f"不认识的子命令：{cmd}\n")
        say(__doc__)
        return 2
    return fn(args)


if __name__ == "__main__":
    C.stdio_safe()
    try:
        rc = main(sys.argv[1:])
    except Exception as e:
        import traceback
        msg = f"handoffctl {' '.join(sys.argv[1:2])} 异常：{type(e).__name__}: {e}"
        print("! " + msg)
        traceback.print_exc()
        try:  # pythonw 下没人看得见 stderr：落进看门狗日志
            os.makedirs(os.path.dirname(C.P.notify_log), exist_ok=True)
            with io.open(C.P.notify_log, "a", encoding="utf-8") as f:
                f.write(f"{C.now_bj():%Y-%m-%d %H:%M} ! {C.one_line(msg)} ⏎ {C.one_line(traceback.format_exc()[-1200:])}\n")
        except Exception:
            pass
        rc = 1
    sys.exit(rc)
