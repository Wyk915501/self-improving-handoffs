现役

# 部署样例

**Windows 不用手装**：`python -X utf8 <DOCS>/规范/交接写时门/handoffctl.py install --dry-run` 看清楚，再去掉 `--dry-run`。它建运行目录、部署测过的运行版、装项目级钩子、建两个计划任务（pythonw 起）、注册处理页按钮协议、装 skill，最后体检。下面这些片段给 Linux、或想自己手装的人：把 `<PYTHON>` 换成解释器绝对路径、`<DOCS>` 换成你 docs 树的绝对路径、`<BIN>` 换成运行版目录（装过就是 `~/.claude/handoff/bin`；没装就用 `<DOCS>/规范/交接写时门`）。

| 文件 | 用在哪 | 验证状态 |
|---|---|---|
| claude-code-project-settings.json | 项目根 `.claude/settings.local.json`（项目级：只对从项目根启动的会话生效，子目录启动的会话不继承） | 原项目两台机器实测触发 |
| zcode-config.json | 项目根 `.zcode/config.json`（ZCode 的钩子多一层 events，command 是单字符串） | **只验了配置能装，未实测触发** |
| CLAUDE.md-片段.md | 加进 Claude Code 读的 CLAUDE.md（`@` 导入生效版） | 原项目在用 |
| AGENTS.md-片段.md | 加进其他工具读的规则文件（一句话指针） | 原项目在用 |
| linux-cron.txt | crontab 片段：兜底扫描（每日学习与弹窗只在唯一的发布者上装） | 原项目远程机在用 |
