现役

# 部署样例

把 `<PYTHON>` 换成你的解释器绝对路径、`<DOCS>` 换成你 docs 树的绝对路径。Windows 用正斜杠也行。

| 文件 | 用在哪 | 验证状态 |
|---|---|---|
| windows-claude-code-settings.hooks.json | 合并进 `~/.claude/settings.json`（用户级＝全机所有项目） | 原项目实测触发 |
| windows-zcode-config.json | 放到项目根 `.zcode/config.json`（ZCode 的钩子多一层 events，command 是单字符串） | **只验了配置能装，未实测触发** |
| linux-project-settings.json | 放到项目根 `.claude/settings.json`（共用 root 的服务器只装项目级，别碰 `/root/.claude/`） | 原项目实测触发 |
| CLAUDE.md-片段.md | 加进 Claude Code 读的 CLAUDE.md（`@` 导入生效版） | 原项目在用 |
| AGENTS.md-片段.md | 加进其他工具读的规则文件（一句话指针） | 原项目在用 |
| windows-计划任务.ps1 | PowerShell 里跑一次（⚠ Git Bash 里 `schtasks /TN` 会被 MSYS 转成路径） | 原项目在用；触发时刻是本机本地时间，先查系统时区 |
| linux-cron.txt | crontab 片段：兜底扫描必装；每日学习只在你选它当发布者时装 | 原项目远程机在用（只装了扫描） |
