---
name: session-summary-title
description: Summarize a conversation and rename its session to an exactly twelve-Han-character title — a Codex thread through the app tool or CLI, or a DeepSeek Harness session through the set_session_title tool. Use when the user requests a recap plus renaming, or invokes this workflow. Respect summary-only or title-only requests; editing the skill itself does not authorize a rename.
---

# Session Summary Title

交付有证据边界的摘要与严格十二个汉字的标题。区分候选、请求被接受、持久化回读成功和界面更新。

## 匹配请求

单独调用本技能默认执行摘要和当前会话改名，无需重复确认。用户只要求摘要、候选标题或改名时，仅交付所要求的部分。审查、优化或修复本技能属于技能维护，不授权修改当前会话标题。

## 摘要与标题

基于可用对话提取目标、已完成事项、关键决策及下一步。保留原目标和已接受的调整，除非用户明确替换或取消。区分已验证、未验证和受阻；省略放弃的分支及无关私人细节。上下文缺失时说明范围，不能把“未见记录”写成“无待办”。复用已有证据，无需为摘要重跑项目检查。

标题应表达实际主题及主要交付物，避免“会话总结”等泛化标签，并满足：

- 恰好十二个汉字，不含空格、标点、数字、拉丁字母或表情。
- 以有意义的双字动词开头，后接具体对象、问题、目的或交付物。
- 不用“的”“之”“相关”“情况”“工作”等弱填充词凑字数，不虚构成果。

应用工具写入前，运行 `python3 <skill-dir>/scripts/validate_title.py '<标题>'`，要求退出码为 `0` 且输出 `OK`。CLI 脚本内置同一校验，无需重复运行。候选标题也应检查字数。脚本校验已分配汉字及长度；语义和双字动词由代理判断。

## 目标会话

默认目标是当前线程，包括子代理自身。优先使用运行时 `CODEX_THREAD_ID`，仅缺失或为空时回退到 `CODEX_SESSION_ID`。子代理可能继承父会话的后者，二者不同不代表冲突；不得清除环境变量或改用父 ID 来消除差异。

选中的 ID 必须是有效的完整 UUID。无效、目标读取失败，或子代理无法确认回退 ID 属于自身时，停止改名，交付可完成的摘要与候选标题。不得用最近会话、目录或标题猜测目标。只有用户明确指定其他会话及其精确 ID 才覆盖默认目标。

DeepSeek Harness 会话使用运行时 `DSH_SESSION_ID`，形如 `session-<uuid>`，与 `$DSH_HOME/sessions/<cwd 键>/<该 id>/` 对应。该环境的改名工具只作用于调用者自己的会话，不接受目标 ID 参数；此 ID 仅用于回读核验。

## 按可用能力修改标题

先检查实际工具清单，必要时使用可用的发现入口。按工具声明操作，不假定固定名称或能力必然存在。

### 应用工具可用

使用已发现的改名工具。例如 `mcp__codex_app__set_thread_title` 接受 `{title, threadId}`，仍以当前声明为准。显式传入选定 ID；仅在没有运行时标识且工具明确绑定目标会话时才省略，子代理不能依赖指向父会话的默认值。

检查返回结果，有读取能力时回读同一 ID。候选文本或模糊结果不证明改名成功；明确权限拒绝后不更换入口绕过限制。

### DSH 会话：`set_session_title` 工具可用

DeepSeek Harness 的 `set_session_title`（由 profile 里的 `dsh-set-session-title` bundle 提供）接受 `{title}`，把**调用者自己的会话**改名为该标题，返回 `{title, eventSeq}`。标题以 `source: {kind: "user"}` 追加为 `session/title` 事件，因此钉住会话：之后不再自动改标题。

不要传目标会话 ID——该工具只作用于当前会话；`DSH_SESSION_ID` 只用于回读核验。工具返回非空 `title` 与正整数 `eventSeq` 即写入成功。

回读同一会话（任选其一，两者都应显示新标题）：

```bash
# GUI 读取的投影缓存；其 seq 应与工具返回的 eventSeq 对应
python3 -c "import json;print(json.load(open('$DSH_HOME/storages/session_projcache/sessions/$DSH_SESSION_ID.json'))['record']['rows']['title'])"

# 持久日志：最后一条 session/title 事件，source.kind 应为 user
zstd -dc "$DSH_HOME"/sessions/*/"$DSH_SESSION_ID"/session.v4.jsonl.zstd | grep session/title | tail -1
```

工具返回成功且回读一致时报告“标题已持久化”；工具确认而无法回读时报告“标题已修改”。同一会话目录可能同时留有 `session.v4.jsonl.zstd` 与旧格式 `session.jsonl.zstd`：**以 v4 为准**，不要在旧文件里没看到新事件就判失败。

### 应用工具不可用，本地 Codex CLI 可用

阅读 [references/cli-protocol.md](references/cli-protocol.md)，使用辅助脚本：

```bash
python3 -B <skill-dir>/scripts/rename_thread.py '<标题>'
```

脚本按目标规则定位；两个环境 ID 均缺失时停止。仅对用户明确指定的其他会话使用 `--thread-id '<精确 ID>'`。

脚本先读目标，必要时改名，再通过新进程回读。仅在退出码为 `0` 且 `status: "verified"` 时报告“标题已持久化”。

请求结果不确定时，可加 `--verify-only` 对同一目标只读核验，不重发写入。该调用的未写入状态不抹去此前已尝试写入的事实。不要原样循环重试；协议问题按参考文档核对。

### 没有可用改名入口，或回读失败

保留摘要与候选标题，说明失败阶段及是否尝试写入。一个工具缺失只排除该入口，不代表整个环境不能改名。

手动步骤应指向目标线程自己的界面：CLI 用 `/rename <标题>`，应用用对应任务菜单。无独立界面的子代理只保留精确 ID 和候选标题，不引导在父会话改名，也不注入终端按键。

## 输出

遵循用户指定格式；默认简短摘要加标题状态。复杂任务可按目标、已完成、关键决策、下一步组织，省略无必要的空项。

按整个任务的证据选择末行：回读成功写“标题已持久化”；应用工具明确确认写“标题已修改”；未尝试写入则给出候选及原因；写入结果不确定写“标题修改未确认”及候选与下一步。仅界面证据或用户反馈支持“界面已更新”。

## 边界

只处理请求范围内的对话。保持 `CODEX_HOME`、模型及配置；不创建或归档任务、发送消息、直接改写内部存储，也不为改标题安装或升级 Codex。DSH 侧同理：工具缺失时按“没有可用改名入口”处理，不得在改名任务中自行安装插件（安装属独立授权），也不得绕过 `/api` 鉴权栅栏去自签凭据。改名失败不扩展为技能修复；明确要求维护技能时使用隔离测试。
