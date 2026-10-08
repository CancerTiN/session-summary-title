# session-summary-title

一个给 AI agent 用的技能：为当前会话生成摘要，并把标题改成**恰好十二个汉字**。它严格区分「候选标题」「请求被接受」「持久化回读成功」「界面已更新」四件事，绝不把前者说成后者。

[English](README.md)

支持的改名入口：

- **DeepSeek Harness** —— 通过 `set_session_title` 工具
- **Codex** —— 通过 app-server 的 `thread/name/set` RPC，或 `/rename` 斜杠命令

## 安装

```bash
npx skills add CancerTiN/session-summary-title
```

或者直接把 `skills/session-summary-title/` 复制进你的技能目录（`~/.agents/skills/`、`~/.claude/skills/` 等）。

## 用法

调用该技能，或者直接用自然语言说：

> 总结这个会话，并起一个十二个汉字的标题。

只要求摘要、或只要求候选标题时，就只交付那一部分——不会多做。

## 为什么是「恰好十二个汉字」

十二个字大致是一个紧凑名词短语的长度：够长到能同时点出**对象**和**交付物**，又够短到在侧边栏或标签页里仍然可读。这条约束是**机械校验**的，不靠自觉：

```bash
python3 skills/session-summary-title/scripts/validate_title.py '打通集群接入与飞书工具链'
# OK
```

校验器只有在「恰好十二个字符」**且**每个字符都是 CJK 统一表意文字时才放行。空格、标点、数字、拉丁字母、emoji、部首和迭字符号一律拒绝。汉字判定走 `unicodedata.name()`，因此落在旧 CJK 区间里的**未分配码位**会被正确拒绝，而新增的扩展平面表意文字则能通过。

## 设计要点：证据边界

多数「改会话标题」的流程在 API 调用返回的那一刻就宣布成功，这就把四种完全不同的状态混为一谈：

| 状态 | 实际已知的信息 |
| --- | --- |
| **候选** | 提出了一个标题，什么都没写 |
| **请求被接受** | 写入调用返回成功，服务端仍可能丢弃 |
| **已持久化** | 对同一目标的独立回读显示新标题 |
| **界面已更新** | 用户自己的界面反映了它。只有用户能观测 |

本技能拒绝把它们合并。**只有在独立回读成功后才报告「已持久化」**；工具确认写入但无法回读时报告「已修改」；写入结果不确定时报告「未确认」并把候选标题交回去。它绝不声称一个自己看不到的界面更新。

同样的纪律约束目标选择：改名工具只作用于**调用者自己的会话**，运行时会话 ID **仅**用于回读核验——不用来猜测目标，也不在当前会话不可读或缺失时回退到父会话。

## 目录结构

```
skills/session-summary-title/
├── SKILL.md                     agent 加载的指令正文
├── agents/openai.yaml           Codex 侧清单
├── references/cli-protocol.md   Codex app-server 协议笔记与证据规则
└── scripts/
    ├── validate_title.py        十二汉字校验器
    ├── rename_thread.py         Codex app-server 改名路径
    └── test_*.py                unittest 测试套件
```

## 环境要求

- **Python 3** —— 脚本只用标准库，无第三方依赖
- **Codex CLI** —— 仅在使用 Codex 改名路径时需要；DeepSeek Harness 路径只需内置工具

## 测试

```bash
cd skills/session-summary-title
python3 -B -m unittest discover -s scripts -p 'test_*.py'
```

共 27 个测试，覆盖：校验器边界（长度错误、非汉字、旧区间内的未分配码位、扩展平面表意文字、部首与迭字符号）、目标隔离（子代理绝不改父会话）、协议异常、写入状态报告、以及独立进程回读核验。

## 许可证

MIT —— 见 [LICENSE](LICENSE)。
