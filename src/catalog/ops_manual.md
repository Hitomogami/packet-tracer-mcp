# Packet Tracer MCP 运维手册

> 本手册是《MCP故障现象报告》§6.2 / §7.6 / §8.6 / §9.4 的蒸馏，供排障与编写探针时查阅。
> 日常工具调用只需会话级 instructions；只有绕过 MCP 工具直接操作桥/脚本引擎前，必须通读本手册。

## 1. 引擎挂死矩阵（安全边界，§8.6 终版）

| 调用 | 3560/2960 (IOS) | PC-PT |
|------|-----------------|-------|
| `device.enterCommand(cmd, mode)` 双参 | ✅（`.second`=同步输出） | ❌ 方法不存在（TypeError） |
| `device.getCommandPrompt()` → 单参 `enterCommand(cmd)` + `getOutput()` | ❌ 方法不存在 | ✅ **PC 唯一 CLI 路径** |
| `device.skipBoot()` | ✅ | ❌ 方法不存在（shim 已兼容） |
| `getCommandLine()` / `getIpcTerminalLine()` 读取 | ✅ 安全（但**不含** ping 异步输出） | 🚫 永不调用（挂死记录） |
| `getIpcTerminalLine().getPrompt()` | ❓ 疑似阻塞 >25s，禁止使用 | — |
| `getIpcTerminalLine().getOutput()` | 无该方法（TypeError），"79/81 字符缓冲"实为错误串长度 | — |
| payload 含 `'` 的 reportResult | ✅ 已由 shim `%27` 转义（修复前=Parse error 弹窗+webview 冻结） | 同 |
| setTimeout 裸回调（仅 reportResult） | ✅ | ✅ |
| setTimeout 回调内任何 IPC | 🚫 挂死 | 🚫 同 |
| shell `-c` 内联 JS 探测 | 🚫 **禁止**（PowerShell 转义损坏 → Parse error；用文件型探针） | 🚫 同 |

## 2. PT 脚本 API 事实（§八穷尽定论）

- **IOS**：`enterCommand(cmd, mode)` 返回 `{first: 状态码, second: 同步输出}`；ping/traceroute 确实执行（`.first=0`）但**异步输出不暴露给任何脚本 API**（GUI 控制台、TerminalLine、telnet 会话均无）→ 用 `show ip arp` 兜底做间接证据。
- **PC-PT**：唯一 CLI 入口 `getCommandPrompt()`，`enterCommand` 为**单参数**形态；输出累积进 `getOutput()`，ping 输出滞后 15-30s 进缓冲（两阶段采集的依据）。
- IOS 输出提取助手为 `__ctext()`（shim 内定义）；自写 JS 必须自带或 prepend `_CTEXT_JS`，否则 ReferenceError（`25b89dd` 的教训）。

## 3. 引擎"挂死"的识别与恢复

- **真挂死症状**：`GET /status` 显示 connected 且 webview 在轮询，但任何命令不执行。
- **历史教训**：多数"挂死"假象另有真因——① payload 撇号击穿 → Parse error 模态弹窗冻结 webview（用户关弹窗即恢复）；② PT 重启后旧 GUI 实例成僵尸进程抢 `/next` 命令。
- **恢复**：重启 Packet Tracer。taskkill 时区分：旧 GUI 实例（按 StartTime/MainWindowTitle，杀）；`--progress-bar-server` 子进程（合法、会重生，**别杀**）。

## 4. 探针纪律（probe_pt.py）

- 新调用先在交换机上试；PC-PT 上只允许 `getCommandPrompt` 路径；每次上未知调用前先跑 `env` 探针确认引擎存活。
- `POST /queue`：body = `COMPAT_SHIM + "\n" + wrap_with_result(js, seq)`；`GET /result?hold=0` 非阻塞取结果（`hold` 缺省 9s 长轮询会把下一条命令的结果偷进断开的 socket——孤儿 handler 教训）；结果队列全局共享，按 seq 过滤。
- 探针 JS 一律走文件（`js_run.py`/`js_multi.py`/`probes/*.js`），禁止 shell 内联。

## 5. 操作纪律（§9.4）

1. **同源 ping 必须串行**：`async_collect` 以 `lastIndexOf(命令)` 锚定截取缓冲增量，同源并发两条 ping 会在转录里混入另一条的输出；异源可并行。
2. **首包 ARP 超时属正常**：ping/traceroute 失败先等 15-30s 复测再下结论。
3. **`write memory` ≠ `.pkt` 落盘**：NVRAM 只保证设备配置进入 PT 内存态；实验完成必须 PT GUI 内 File→Save，否则下次打开是旧快照。
4. **跨会话先抽查完成态标志**（hostname、SVI IP、PC 端口 IP），用 `pt_get_device_info` / `pt_get_running_config` 判断 `.pkt` 新旧，不要假设上次会话的内存配置还在。
5. **"成功 + 空输出" ≠ "代码陈旧"**：IOS 兜底若代码旧会以 `✗ Ping failed: ReferenceError` 呈现；`success + 空` 说明新代码在跑、空是环境数据（如 ARP 表真空）。
