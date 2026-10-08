# CLI 改名协议与验证

在使用 CLI 路径或维护辅助脚本时阅读。脚本仅依赖 Python 标准库；应使用当前安装的 `codex`，不创建模型回合来完成改名。

## 正常流程

```bash
python3 -B <skill-dir>/scripts/rename_thread.py '<十二字标题>'
```

1. 校验标题、超时参数和精确目标 ID，再检查 `codex` 是否可用。
2. 启动 `codex app-server --stdio`，发送 `initialize`，收到结果后发送 `initialized` 通知。
3. 调用 `thread/read`，参数为 `{threadId: "<ID>", includeTurns: false}`；要求返回相同 ID 及可验证的 `name` 字段。`name: null` 表示尚未命名。
4. 标题不同时，调用 `thread/name/set`，参数为 `{threadId: "<ID>", name: "<标题>"}`。相同时跳过写入。
5. 结束首个客户端，再启动新进程读取同一 ID 的 `thread.name`；匹配才返回 `status: "verified"` 和退出码 `0`。

协议为逐行 JSON。客户端忽略通知，拒绝服务端发起的交互请求，不批准命令或其他动作。它不调用 `thread/start`、`thread/resume` 或 `turn/start`，也不直接读取或改写内部存储文件。

## 失败与只读核验

失败返回退出码 `1`，错误结果在 stderr 中输出 JSON：

- `stage`：输入校验、目标定位、CLI 查找、连接、初次读取、改名或回读中的具体阶段。
- `thread_id`：成功解析的精确目标；解析前失败则为 `null`。
- `write_attempted: false`：本次未调用改名请求。
- `write_attempted: true`：已尝试调用，不能据此保证请求到达服务端。
- `request_accepted: true`：收到改名接口的成功响应，仍需回读确认持久化。

请求可能已发送后，不自动再次写入。可沿用同一目标只读检查：

```bash
python3 -B <skill-dir>/scripts/rename_thread.py --verify-only '<十二字标题>'
```

该选项只启动一个新的客户端并读取目标，绝不调用 `thread/name/set`。标题匹配时返回 `status: "verified"`、`operation: "verify"`；不匹配或读取失败仍返回未确认状态。它不能验证已打开的终端界面是否刷新。

两种模式均优先使用 `CODEX_THREAD_ID`，仅缺失或为空时回退到 `CODEX_SESSION_ID`。不得用另一个会话解决无效 ID 或读取失败。仅当用户明确指定其他会话及其精确 ID 时才使用 `--thread-id`，并在核验时保留同一目标。

`--timeout` 限定每次 RPC 的等待时间，默认 15 秒，合法范围为大于 0 且不超过 60 秒；它不是整个流程的总超时。方法不支持、启动失败、权限拒绝或超时后停止原样重试。权限拒绝不授权改用其他入口绕过限制。

## 版本依据与维护

2026-09-25 核对了官方文档及本机 Codex CLI **0.157.0** 的帮助和生成 schema。该版本接受 `--stdio`；官方文档也描述默认 stdio 和 `--listen stdio://`。这属于协议核对，不代表对真实会话做过改名验证。

- [App Server](https://developers.openai.com/codex/app-server)：初始化握手、`thread/read`、`thread/name/set` 及名称回读。
- [CLI slash commands](https://developers.openai.com/codex/cli/slash-commands)：`/rename` 修改当前界面的会话。

遇到版本差异时，先读 `codex app-server --help`；需要核对参数时，将 `codex app-server generate-json-schema --out <临时目录>` 的结果与脚本使用的少量字段对照。不要为改标题安装、升级或重配 Codex。

维护代码后运行：

```bash
python3 -B -m unittest discover -s <skill-dir>/scripts -p 'test_*.py'
```

测试使用临时数据及模拟服务，验证目标隔离、标题校验、协议异常、写入状态与独立进程回读。保留已验证、模拟验证和真实界面观察之间的证据边界；不为维护技能试改真实会话标题。
