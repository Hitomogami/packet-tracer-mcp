# Packet Tracer MCP 故障现象报告

> 实验环境：实验5《利用三层交换机实现VLAN间的通信》（switchC=3560 三层交换机，switchA/switchB=2960，pc1~pc4）
> 报告日期：2026-09-24
> 现象总结：**写命令（添加/连线/发CLI/配PC）能到达 PT 并生效；读取类接口（设备列表/拓扑/CLI输出回传）始终返回空或假数据。**

---

## 一、按时间线的完整调用记录与原始返回

### 阶段 1：会话开始（写操作正常）

| 工具 | 返回原文（节选） | 旁证 |
|------|------------------|------|
| `pt_list_templates` | 正常返回 4 个模板 | 服务端静态数据，不依赖 PT |
| `pt_add_device` ×7 | `✓ Added switchC (3560-24PS) at position (380, 60)` | **用户目视确认设备真实出现在 PT 画布** |
| `pt_connect` ×6 | `✓ Connected pc2:FastEthernet0 ↔ switchA:FastEthernet0/1 [auto→straight]` | **用户目视确认线缆真实出现** |
| `pt_send_commands` ×3 | `✓ Commands sent to switchA:\n enable\n configure terminal...` | ⚠️ 该返回是对输入命令的**纯回显**，并非设备 CLI 输出，无法证明命令真正执行 |

### 阶段 2：第一次读取（交换机配置下发后立即）—— 空输出但不报错

| 工具 | 返回原文 |
|------|---------|
| `pt_show_interfaces`（switchC、switchA） | `Interfaces on switchC:\n(no output — ensure device is configured)` |
| `pt_get_running_config`（switchC） | `Running config for switchC:\n\n(no output returned — PT may need more time)` |

- 工具正常执行完毕、无异常，但**输出捕获为空**。
- 等待 8 秒后重试，结果完全相同。

### 阶段 3：读取进一步退化 —— 注册表为空

| 工具 | 返回原文 |
|------|---------|
| `pt_list_devices` | `No devices found in topology (or Packet Tracer is disconnected).` |
| `pt_list_connections` | 同上 |
| `pt_get_device_info` | `Device 'switchC' not found. Known devices: none` ← **关键线索** |
| `pt_export_topology` | `{"devices": [], "connections": [], "summary": {"device_count": 0, "connection_count": 0}}` |
| `pt_validate` | `⚠ Topology is empty — no devices found.` |

**关键线索**：`Known devices: none` 表明服务端维护了一个**内存中的"已知设备注册表"**，而它为空 —— 尽管 `add_device` 刚成功且设备真实存在。

### 阶段 4：同一代码块内"写成功 + 读为空"的自相矛盾

在**同一个脚本块**内先 add 再 list：

```text
pt_add_device(testprobe) → "✓ Added testprobe (PC-PT) at position (900, 100)"   ← 用户目视确认出现
pt_list_devices()        → "No devices found in topology"                        ← 同一秒读取为空
```

证明**写与读走的是两条不同通道**。随后：

| 工具 | 返回 | PT 端实际表现 |
|------|------|--------------|
| `pt_remove_device`（testprobe） | 服务端返回 `✓ Removed device 'testprobe'` | **PT 端弹出 `ReferenceError: removeDevice is not defined`**（服务端假成功） |
| `pt_get_running_config`（switchC） | `✗ Failed to get config for switchC: PT stopped polling — is Packet Tracer still open?` | 错误文案与阶段 2 不同 |
| `pt_configure_pc` ×4 | `✗ Failed to configure pc1: PTBuilder is not polling. Make sure Packet Tracer is open with the MCP bridge PTBuilder module installed.` | 4 台 PC 全部失败 |

### 阶段 5：用户重启 Packet Tracer 并重新打开文件后

| 工具 | 结果 |
|------|------|
| `pt_list_devices` / `pt_export_topology` / `pt_validate` | ❌ **仍然全空**（重启未修复注册表类读取） |
| `pt_add_device`（probe1） | ✅ 成功，用户目视确认 |
| `pt_configure_pc` ×4 | ✅ **重启后成功**：`✓ pc1: 192.168.1.2/255.255.255.0 gw= dns=`（重启前报 not polling） |
| `pt_ping` ×2 | `Ping from pc2 to 192.168.0.3:\n(sent to PT console — Packet Tracer cannot return ping output; check the result inside Packet Tracer)` |
| `pt_send_commands` ×3（重发全部交换机配置） | ✅ 回显成功（执行与否仍无法通过读取接口确认） |

---

## 二、症状分类归纳

| 类别 | 工具 | 现象 | 推测的故障点 |
|------|------|------|-------------|
| **A 类：始终正常**（fire-and-forget 通道） | `add_device`、`connect`、`send_commands`（仅回显）、重启后的 `configure_pc` | 调用即成功，PT 侧真实生效 | 无故障 |
| **B 类：始终返回空**（注册表/快照类读取） | `list_devices`、`list_connections`、`get_device_info`、`export_topology`、`validate` | 一律"拓扑为空 / 设备未找到"，`Known devices: none` | 服务端 known-devices 注册表填充/同步逻辑：`add_device` 未登记？PT 重连后未重新同步？ |
| **C 类：命令发出但输出捕获失败**（CLI 输出回传通道） | `show_interfaces`、`get_running_config`、`ping` | `(no output — ensure device is configured)` / `PT stopped polling` / 明确声明 `cannot return ping output` | PT 侧执行 CLI 后如何把输出写回响应；服务端等待/超时分支 |
| **D 类：服务端与 PT 侧脚本命令表不匹配** | `remove_device` | 服务端返回 ✓，PT 侧抛 `ReferenceError: removeDevice is not defined` | PT 侧（PTBuilder 模块 JS）命令分发表与服务端函数名映射不一致；服务端缺少对 PT 侧执行结果的确认，导致假成功 |

---

## 三、给源码排查的入口建议

1. **B 类优先查注册表**：`pt_get_device_info` 的报错文案 `Known devices: none` 是最直接的字符串锚点，反查该注册表（known devices）在何处写入、何处清空。重点确认 `add_device` 成功后是否登记，以及 PT 断开重连（重启）后是否有重新枚举拓扑的逻辑。
2. **C 类查输出回传**：`get_running_config` 在不同阶段返回过三种文案（`no output returned — PT may need more time` / `PT stopped polling — is Packet Tracer still open?` / 空输出），可作为内部状态分支的断点排查入口。对照 PT 侧执行 `show` 命令后输出回传的实现。
3. **D 类查命令分发表**：在 PT 侧 PTBuilder 模块 JS 中搜索 `removeDevice`，确认其是否存在/命名是否与服务端下发的命令名一致；同时排查其他工具是否存在同类不匹配（尤其哪些命令"发得出去、没实现"）。
4. **双通道架构确认**：阶段 4 证明存在 fire-and-forget 与轮询（polling）两条通道。`configure_pc` 在 PT 重启前报 `PTBuilder is not polling`、重启后成功，说明轮询通道由 PT 侧模块驱动；而注册表类读取（B 类）与轮询通道恢复与否无关，重启后依旧为空。

---

## 四、当前实验进度与待办（修复后继续）

**已完成：**
- 拓扑搭建：switchC(3560) + switchA/switchB(2960) + pc1~pc4，6 条线缆（PC↔交换机 Fa0/1-Fa0/2；switchA/B 的 Fa0/23 ↔ switchC 的 Fa0/1-Fa0/2）
- 三台交换机配置已下发（幂等重发过一次）：
  - switchA/B：vlan10、vlan20；Fa0/1→access vlan10，Fa0/2→access vlan20，Fa0/23→trunk
  - switchC：`ip routing`；vlan10/20；Fa0/1-2 → `switchport trunk encapsulation dot1q` + trunk；`int vlan 10 → 192.168.0.1/24`、`int vlan 20 → 192.168.1.1/24` 均 no shutdown
- PC IP 已配置成功（**无网关**）：pc1=192.168.1.2、pc2=192.168.0.2、pc3=192.168.0.3、pc4=192.168.1.3（掩码均为 255.255.255.0）

**待办：**
1. 人工清理 PT 画布上的 `probe1`（及可能残留的 `testprobe`）
2. 修复 MCP 读取通道后，核对三台交换机 `show run` / `show ip int brief` / `show vlan brief`
3. 阶段一验证（无网关）：pc2→pc3 ✅、pc1→pc4 ✅、跨 VLAN ❌
4. 下发网关：pc2/pc3 → 192.168.0.1，pc1/pc4 → 192.168.1.1
5. 阶段二验证（有网关）：跨 VLAN 全部 ✅
6. `pt_save_config` 保存所有设备配置，`pt_export_topology` 导出拓扑留档

**IP 规划参考：**

| 设备 | 端口/接口 | VLAN | IP | 网关 |
|------|-----------|------|----|------|
| switchC SVI | — | 10 | 192.168.0.1/24 | — |
| switchC SVI | — | 20 | 192.168.1.1/24 | — |
| pc2 | switchA Fa0/1 | 10 | 192.168.0.2 | （阶段二）192.168.0.1 |
| pc3 | switchB Fa0/1 | 10 | 192.168.0.3 | （阶段二）192.168.0.1 |
| pc1 | switchA Fa0/2 | 20 | 192.168.1.2 | （阶段二）192.168.1.1 |
| pc4 | switchB Fa0/2 | 20 | 192.168.1.3 | （阶段二）192.168.1.1 |

---

## 五、修复实施记录（2026-09-24，已完成并在线验证）

### 5.1 根因（已证实）

| 类别 | 根因 |
|------|------|
| B 类 | `pt_connection.py` 的 `get_topology_state()` 硬编码返回空列表，从未查询 PT |
| C 类 | `send_script` 发完即睡 0.6s 返回空；PT 侧 mcpbridge.html 只轮询 /next 执行 runCode，**无任何结果回传**；脚本引擎无 XMLHttpRequest，唯一网络通道是隐藏 webview |
| D 类 | PTBuilder API 无 `removeDevice`/`removeLink`/`moveDevice`/`getTopology`，服务端却生成这些调用 → PT 弹 ReferenceError |
| 连锁 | runCode 出错弹**模态框冻结轮询** → 后续全部 "not polling"（解释了阶段 4 现象） |

### 5.2 修复方案（Python 侧 4 文件 + 新增测试，无需改 .pts）

- `script_builder.py`：SHIM 新增 `reportResult()`（经 `mcpBridge.webview.evaluateJavaScriptAsync` 注入 XHR 回传 POST /result）；`wrap_with_result()` 包 try/catch+seq（消灭假成功与模态弹窗）；改用真实 IPC 原语 `LogicalWorkspace.removeDevice()`/`deleteLink()`/`device.moveToLocation()`；新增 `get_topology()`（getDeviceAt/getLinkAt + port-UUID 映射）与 `exec_cli()`
- `pt_connection.py`：`send_script` 改**同步请求-响应**（drain→入队→按 seq 等结果，超时给诊断）；新增 `PTScriptError`
- `command_queue.py`：真实 `get_topology`（含 typeId→category 映射）、新增 `exec_cli`
- `tools/*`：show_interfaces/get_running_config/ping/traceroute 走真实输出；send_commands/remove_device 消灭假成功
- `tests/test_bridge_roundtrip.py`：离线回归测试（模拟 webview 轮询），全部通过

### 5.3 在线验证结果（重启 MCP 服务后实测）

| 测试 | 结果 |
|------|------|
| `pt_list_devices` | ✅ 8 台设备（switchC/A/B、pc1~4 + 多余的 Power Distribution Device0 待清理） |
| `pt_list_connections` | ✅ 6 条线缆与拓扑完全吻合 |
| `pt_get_device_info` | ✅ 端口状态正确（switchC Fa0/1-2 connected） |
| `pt_validate` | ✅ 8 devices, 6 connections, no errors |
| `pt_show_interfaces(switchC)` | ✅ 完整 IOS 接口表（Fa0/1-2 trunk up/up） |
| `pt_get_running_config(switchC)` | ✅ 1162 字节完整回传 |
| `pt_ping` | 🔶 执行成功但输出为空 —— **ping 异步，enterCommand 立即返回空缓冲**，待二次读取 console 解决 |

**关键发现**：`enterCommand` 返回 `{first: <状态码>, second: "<CLI输出>"}`，文本在 `.second`。exec_cli 的 `__ctext()` 已按此提取。

### 5.4 修复暴露的实验配置问题（重要！）

之前"回显成功"的下发**实际未全部生效**（假成功掩盖）：
- **switchC**：❌ 无 vlan 10/20 定义、❌ 无 SVI IP（192.168.0.1/192.168.1.1）、❌ Fa0/1-2 无 trunk、❌ hostname 仍为 Switch；仅 `ip routing` ✅
- **switchA**：✅ Fa0/1→access vlan10、Fa0/2→access vlan20、Fa0/23→trunk；❌ hostname 未生效、show run 中无 vlan 定义段（PT 可能自动建，需 show vlan brief 核实）
- switchB 未检查

**待办（按序）**：
1. 修复 ping 异步输出问题：exec_cli 对 ping 类命令二次 enterCommand（如发空命令或 "ping" 结束后延时读取 console 缓冲）再取 .second
2. 人工清理画布：probe1、testprobe、Power Distribution Device0
3. **重新下发交换机配置**（现在有逐条确认通道）：重点补 switchC 的 vlan 10/20 + SVI IP + Fa0/1-2 trunk、三台 hostname；下发后用 show run 核实
4. 继续报告 §四 阶段一/二验证（pc2↔pc3、pc1↔pc4、跨 VLAN 网关）
5. pt_save_config + pt_export_topology 留档
6. 可选：升级 configureIosDevice 为逐条返回结果的版本（hostname 等首条命令被吞的根因排查）

---

## 六、在线 API 探测记录（2026-09-24 第二次会话，probe_pt.py）

> 方法：不经 MCP 工具，直接与运行中的桥 HTTP 服务对话（`POST /queue` 投递原始 JS，`GET /result` 收结果，`GET /status` 查轮询）。
> 工具：`probe_pt.py`（已入库，用法 `python probe_pt.py <probe名>`，带 `!` 后缀为裸 JS 探测）。
> 目的：定位 ping 异步输出的落点 + 摸清 PT IPC API 安全边界。

### 6.1 关键发现（已实测证实）

| # | 发现 | 证据 |
|---|------|------|
| 1 | **脚本引擎支持 `setTimeout`，裸回调正常触发**（12s 实测通过） | timer12 探测返回 "TIMER12 FIRED" |
| 2 | **setTimeout 回调内做 IPC 调用 = 引擎死锁**（裸回调没事） | ping_hunt2（回调内 getOutput）超时，engine 卡死 |
| 3 | **设备对象有 `getCommandLine()` → ConsoleLine 对象**，其 `getOutput()` 返回**完整 GUI 控制台缓冲**（switchC 上 4933 字符：boot 日志 + syslog），**非破坏性**（连读两次 identical） | get_output / output_tail / output_twice 探测 |
| 4 | ConsoleLine 缓冲里**只有 boot+syslog**：既无 enterCommand 的命令输出，也无 ping 输出 → enterCommand 走的是另一条通道 | output_tail（ping 之后读，尾部只有 LINK-5-CHANGED） |
| 5 | `getIpcTerminalLine()` → TerminalLine 对象 = **enterCommand 实际会话**（`getMode()`=**"enable"**），但其 `getOutput()` 恒为 **0** | ipc_term_min / ipc_term_getout |
| 6 | ConsoleLine/TerminalLine 对象方法表（可能有用）：`getOutput, getMode, getPrompt, getCommandInput, enterChar, enterCommand, println, flush, getCurrentHistory, getConfigHistory, getUserHistory, registerEvent, registerDelegate` | cmdline_obj / term_obj 探测 |
| 7 | `enterCommand` 返回 `{first: 状态码, second: 命令自身同步输出}`；**`.second` 不含异步输出，且后续 enterCommand 也不回传之前挂起的输出**（"冲刷"假设被否定） | pt_ping 后立刻 pt_show_interfaces：输出干净无 ping 痕迹 |
| 8 | **ping 输出落点仍未找到**，且 ping 是否真的执行过都存疑（各缓冲均无痕迹）；**`.first` 状态码至今未记录过**——下一步必须先抓它 | 全部 ping 相关探测 |
| 9 | switchC 配置缺失再次确认：`show ip int brief` 无 Vlan10/Vlan20 接口，Fa0/1-2 up 但 trunk/SVI 全无 → §5.4 结论成立 | pt_show_interfaces(switchC) |

### 6.2 ⚠️ IPC 调用安全矩阵（防止再次挂死引擎，务必遵守）

**引擎挂死症状**：`GET /status` 仍显示 connected（webview 在轮询），但任何命令不执行（`python probe_pt.py env` 超时）。唯一恢复手段：**重启 Packet Tracer**。

| 调用 | 3560/2960 交换机 | PC-PT |
|------|------------------|-------|
| `device.enterCommand(cmd, mode)`（含 "enable"/"global"/"" mode） | ✅ 安全（show run 全文回传） | ✅ 安全（enable+ping 均返回，ping 的 .second 为空） |
| `device.skipBoot()` | ✅ 安全 | ✅ 安全（pt_ping pc2 全程正常） |
| `getCommandLine()` + `.getOutput()/.getMode()/.getPrompt()` | ✅ 安全 | ❌ **挂死引擎**（test_pc_ping1 实测） |
| `getIpcTerminalLine()` + `.getOutput()/.getMode()` | ✅ 安全 | ❓ 未测（假定同样危险） |
| `cl.enterCommand(...)`（ConsoleLine 上的） | ❌ **挂死引擎**（cl_login 探测 `("","")` 实测） | ❓ 未测 |
| setTimeout 裸回调（仅 reportResult） | ✅ 安全（12s 实测） | ✅（同理） |
| setTimeout 回调内任何 IPC | ❌ **挂死引擎** | ❌ 同 |

**探测纪律**：新调用先在 switchC 上试；PC-PT 上只允许 device.enterCommand/skipBoot；每次上未知调用前先跑 `env` 探测确认引擎活着。

### 6.3 当前状态（会话结束时）

> ⚠️ **本节及 §6.4 已过时，最新状态见 §七（第三次会话）。**

- **Packet Tracer：引擎第二次挂死中（test_pc_ping1 触发），需再次重启 PT 并打开实验文件**
- MCP 服务器：正常运行（用户已重启过一次），代码为 §5.2 修复版（未提交 git）
- 拓扑：9 台设备在线（switchC/A/B、pc1~4 + 待清理 testprobe、Power Distribution Device0）
- probe_pt.py 已就位（重启 PT 后立即可用，无需重启 MCP）

### 6.4 下一步计划（按序执行）

> ⚠️ **本节已过时，最新计划见 §七.5。**

1. **用户重启 PT**（引擎已挂死），打开 1.pkt；重启后跑 `python probe_pt.py env` 确认恢复
2. **TEST B（switchC ping，全部用已证安全调用）**：抓 `.first` 状态码 + `{first,second}` 全文 + ping 后 12s 读 cl/tl 缓冲 → 确定 ping 是否执行、输出落哪。探针 `test_sw_ping1!`/`test_sw_ping2!` 已写好在 probe_pt.py（去掉其中 cl 相关调用即可，注意 switchC 上这些调用是安全的，可直接用）
3. **TEST A（PC ping）重设计**：PC 上只允许 `device.enterCommand`——先抓 PC ping 的 `{first,second}`（.first 是关键新信息）；PC 控制台读取另想办法（候选：`getConsole()`（ConsolePort，switchC 上安全，PC 未测）、registerEvent 事件注册、或放弃读输出改用 `show arp`/`show mac address-table` 间接验证）
4. **按实验结果实现代码修复**：
   - `command_queue.exec_cli`：ping/traceroute 双阶段（发命令 → Python asyncio.sleep(12) → 读缓冲），阶段 2 JS 按 TEST 结论写
   - `script_builder.configure_device`：弃用 PTBuilder configureIosDevice，改 exec 式逐条循环（`("!","global")` 后加 ~400ms Date 自旋等模式切换稳定，解决"首条命令被吞"；逐条捕获返回值，工具层报告每条成败）→ 顺带完成 §5.4 待办 6
   - 更新 tests/test_bridge_roundtrip.py
5. **告知用户重启 MCP**（代码改动生效），然后继续实验：
   - `pt_remove_device` 清理 testprobe、Power Distribution Device0（现在 remove_device 是真实现）
   - 重新下发三台交换机配置（重点 switchC：vlan10/20 + SVI IP + Fa0/1-2 trunk + 三台 hostname），逐条确认后 show run 核实
   - §四 阶段一验证（无网关：pc2↔pc3 ✅、pc1↔pc4 ✅、跨 VLAN ❌）→ 下发网关（pc2/pc3→192.168.0.1，pc1/pc4→192.168.1.1）→ 阶段二跨 VLAN 全 ✅
   - pt_save_config 全设备 + pt_export_topology 留档
6. 全部完成后更新本报告 + git 提交（含 probe_pt.py；或按需删除）

### 6.5 桥 HTTP 端点备忘（probe_pt.py 依赖）

- `POST /queue`：body = `COMPAT_SHIM + "\n" + wrap_with_result(js, seq)`（或裸 JS 自带 reportResult）
- `GET /result`：服务端 hold 最长 9s，空则 204；**结果队列是全局的**，MCP 工具调用与 probe 共享，交叉消费时注意 seq 过滤
- `GET /status`：`{"connected": bool, "last_poll_ago": float}`，判断引擎挂死（connected=true 但命令无响应）的关键

---

## 七、第三次会话（2026-09-24 续）：孤儿 handler 排障 + configure_device 改造 + TEST B

### 7.1 本会话结论速览（续接必读）

| # | 结论 | 状态 |
|---|------|------|
| 1 | **configure_device 逐条确认改造完成**（§6.4 步骤 4-b）：exec 式循环 + 400ms Date 自旋 + 逐条 `{cmd,first,out}` 捕获 + Python 侧 IOS 错误标注 | ✅ 代码+测试就位 |
| 2 | **"引擎第二次挂死"是误判**：真相是 PT 重启后旧实例（35796）成为僵尸进程残存，与新版并抢 `/next` 命令；已 taskkill | ✅ 已解决 |
| 3 | **probe 结果丢失的真正根因 = `_drain()` 孤儿 handler**：客户端 1s 超时的 `GET /result` 在服务端仍阻塞 9s，把下一条命令刚报告的结果偷进断开的 socket | ✅ 已修复（`/result?hold=0`） |
| 4 | **回传链路自始至终没坏**：`reportResult` 返回 true，`DIAG` 实测躺在结果队列里 | ✅ env 探针复通 |
| 5 | **TEST B 部分完成**：ping 的 `.first=0`、`.second="\n"`；输出不进 GUI 控制台；**tl 缓冲从恒 0 变为 79 字符**（内容未读到，见 7.5 待办 1） | 🔶 进行中 |
| 6 | `tl_dump` 探针超时一次（引擎未挂死，env 随后正常）——疑似 `getPrompt()`（未验证调用）或非空 `tl.getOutput()` 首次读取触发阻塞 | ❓ 待隔离 |

### 7.2 本会话完整时间线与证据

1. **configure_device 改造**（PT 未恢复期间完成，代码见 7.3）：
   - 测试 3/4 通过（pytest 未安装，用 conda python 内联跑）；`test_drain_endpoint_is_non_blocking` 因测试间端口占用（10048，roundtrip 测试的 server 未释放）未跑通——**逻辑未验证，待修**（换端口即可）。
   - 跑测试命令（conda 环境无 pytest）：
     `& 'D:\ProgramData\anaconda3\envs\envs\packettracer\python.exe' -c "import sys; sys.path.insert(0,r'D:\packet-tracer-mcp'); import tests.test_bridge_roundtrip as t, traceback; [ (f(), print('PASS',n)) if not (lambda:( f(), None))() else None for n,f in ...]"` ← 实际用的是遍历 `vars(t)` 逐个 try 的内联脚本，建议直接给该环境装 pytest。
2. **PT 重启后发现"依然超时"** → 排障链：
   - `/status` 显示 connected=true 且 last_poll 活跃 → 网页轮询活着
   - `Get-Process PacketTracer` → **两个实例**：35796（15:21，旧挂死实例=僵尸）+ 30580（16:23，新开 1.pkt）→ `taskkill 35796`
   - kill 后又冒出无窗口 `PacketTracer.exe --progress-bar-server` 子进程（**合法子进程，杀了会重生，别杀**）→ 一度怀疑它抢命令
   - 裸 `reportResult(...)` 探针（无 shim）超时 → 后续证明该探针从未执行（被僵尸偷走）
   - 投递裸文本 MARKER → **用户目击 PT 弹 `ReferenceError: COMPAT_MARKER_TEST_xxx is not defined`（全程唯一一次弹窗）** → 证明 runCode 执行通道正常
   - 火忘 `addDevice('probe_visible','PC-PT',900,100)` → **设备真实出现**（与 testprobe 重叠，曾误判未出现）→ 证明 shim+写通道正常
   - 诊断探针把引擎状态编码进设备名（`diag_report.py`）→ 用户读到 **`m_object_w_object_v_undefined_e_function_r_true`**：mcpBridge 存在、`evaluateJavaScriptAsync` 是函数、**`reportResult("DIAG")` 返回 true**
   - `GET /result` → **队列里躺着 `DIAG`** → 实锤：回传正常，是 **probe 的 `_drain()` 孤儿 handler 把每条快速探针的结果吃掉了**
   - 修复 `/result?hold=0` + probe drain 改造 → **用户重启 MCP → `env` 探针正常返回** → 链路端到端复通 ✅
3. **为何历史现象都对上了**：`timer12!`（12s 后才报告）成功 = 结果到达时 9s 孤儿已过期；§5.3 MCP 工具全正常 = `send_script` 的 `drain_results()` 用 `get_nowait` 无孤儿；所有"超时"命令实际都执行了（但 env/marker 之前那些已被僵尸偷走）。

### 7.3 本会话代码变更（全部未提交 git）

| 文件 | 变更 |
|------|------|
| `src/bridge/script_builder.py` | 新增共享 `_CTEXT_JS`、`_spin(ms)`；`CONFIG_SKIP_COMMANDS` 导出；`configure_device` 重写为 exec 式逐条循环（`("!","global")` 后 400ms 自旋，逐条捕获 `{cmd,first,out}`，**不再自动 write memory**）；`save_device_config` 重写（`("!","enable")`+自旋+`write memory`+捕获结果）；`exec_cli` 复用 `_CTEXT_JS` |
| `src/bridge/command_queue.py` | 新增 `looks_like_ios_error()`（区分 `% Invalid input` 与 syslog `%FACILITY-N-`）、`_annotate_config_results()`（逐行加 `failed`/`error`）；`configure_device`/`save_config` 接入标注 |
| `src/tools/configuration.py` | `pt_send_commands` 逐条 ✓/✗ + IOS 错误行 + skipped 提示；`pt_save_config` 显示 `[OK]`/失败检测；`pt_configure_ip` 逐条失败上抛；`_format_config_rows` 助手；工具 docstring 同步更新 |
| `src/bridge/pt_connection.py` | **do_GET 改 urlparse 路由**；新增 `GET /result?hold=0` 非阻塞取结果（get_nowait，立即 204）；hold 默认行为不变；代码内注释警告孤儿陷阱 |
| `probe_pt.py` | `_drain()` 改用 `hold=0`；`send_wrapped` 按 seq 过滤结果；新增 `tl_dump` 探针（读 tl 内容/mode/prompt） |
| `tests/test_bridge_roundtrip.py` | FakePTWebview 增加 configure 结果分支（`__out={results:__res};`）与 save 分支（`{cmd:"write memory"`）；新增 `test_ios_error_heuristics`、`test_drain_endpoint_is_non_blocking`；roundtrip 增加第 5/6 段（configure_device 失败行标注、save_config 返回） |
| `diag_report.py` | 新增一次性诊断脚本（引擎状态编码进设备名），可删 |

### 7.4 TEST B 实测数据（switchC，安全调用）

- `test_sw_ping1!`（ping 192.168.0.3 后立即）：
  - `base_cl_len=4933`（GUI 控制台缓冲基线，boot+syslog）
  - **`ping_ret={"first":0,"second":"\n"}`** ← `.first=0` 状态码首获；`.second` 仅一个换行，无 ping 输出
  - `tl_mode=enable`、`cl_mode=logout`（GUI 控制台在 boot 后未登录态）
- `test_sw_ping2!`（约 12s 后）：
  - `cl_len=4933` **未变** → ping 输出不进 GUI 控制台（§6.1 发现 4 再证实）
  - **`tl_len=79`** ← IPC TerminalLine 从历史恒 0 变为 79 字符：**异步输出的头号候选落点**
- **未读出 79 字符内容**：`tl_dump` 超时一次（含未验证的 `getPrompt()` 与首次非空 `getOutput()` 读取）。随后 `env` 正常 → 引擎未挂死；超时可能是该调用阻塞 >25s 后恢复，结果又被下一次 env 的 drain 丢弃（无孤儿，属正常清队）。
- **注意**：switchC 此刻无 IP（§5.4），该 ping 大概率失败——但失败 ping 同样能验证异步输出落点；待 79 字符内容确认。

### 7.5 下一步计划（按序）

> ✅ **本节已全部完成（除 MCP 重启验收），过程与结果见 §八。**

1. **读出 tl 的 79 字符**（决定 ping 修复方案的关键）：
   - 探针只保留 `getMode()` + `getOutput()`（**删掉 getPrompt**），timeout 放大到 60s；
   - 若仍超时 → 分别隔离：只读 `getMode()` → 只读 `getOutput()`，定位阻塞点并更新 §6.2 安全矩阵（非空 tl 缓冲读取可能不安全）；
   - 若确认 tl 持有 ping 输出 → **`exec_cli` 双阶段方案落地**：ping/traceroute 命令发出后 Python 侧 `asyncio.sleep(12)`，再发第二条 JS 读 `tl.getOutput()` 拼接返回（§6.4 步骤 4-a）。
2. **修 drain 测试端口冲突**：`test_drain_endpoint_is_non_blocking` 换用 `TEST_PORT+1`（或测试间显式 shutdown+等待），重跑全部 4 个测试确认 PASS。
3. **清理画布**（`pt_remove_device`，现在是真实现）：`testprobe`、`Power Distribution Device0`、`probe_visible`（**注意它已被 setName 成诊断串 `m_object_w_object_v_undefined_e_function_r_true`，按画布上实际标签删**）。
4. **核实 PC IP 是否幸存**：PT 重启 = 1.pkt 从磁盘重开，上一会话 configurePcIp 的内存配置可能丢失 → 用 `pt_get_device_info` pc1~4 或 `get_topology()` 端口 IP 字段核实；丢了就重推（pc1=192.168.1.2、pc2=192.168.0.2、pc3=192.168.0.3、pc4=192.168.1.3，掩码 /24，无网关）。
5. **重新下发交换机配置**（新逐条确认通道，下发后核对每条 ✓/✗）：
   - switchC（重点，§5.4 全缺）：`hostname switchC`、`ip routing`、`vlan 10`、`vlan 20`、`int vlan10→192.168.0.1/24 no shut`、`int vlan20→192.168.1.1/24 no shut`、`Fa0/1-2 → switchport trunk encapsulation dot1q + switchport mode trunk`
   - switchA/B：`hostname`、`vlan 10/20` 定义（show vlan brief 核实 PT 是否自动建）、Fa0/1→access vlan10、Fa0/2→access vlan20、Fa0/23→trunk
   - 下发后 `show run` / `show ip int brief` / `show vlan brief` 核实
6. **§四 阶段一/二验证**：pc2↔pc3 ✅、pc1↔pc4 ✅、跨 VLAN ❌ → 下发网关（pc2/pc3→192.168.0.1，pc1/pc4→192.168.1.1）→ 跨 VLAN 全 ✅（ping 输出问题若未解决，可用 `show arp`/`show mac address-table` 间接验证，§6.4 TEST A 候选）
7. `pt_save_config` 全设备（现在是逐条确认版）+ `pt_export_topology` 留档
8. 更新本报告 §七 结果 + **git 提交**（src 全部改动 + tests + probe_pt.py；`diag_report.py` 建议删除）

### 7.6 安全矩阵增补（在 §6.2 基础上）

| 调用 | 状态 |
|------|------|
| `getIpcTerminalLine().getPrompt()` | ❓ **未验证，疑似阻塞 >25s（tl_dump 超时主嫌疑）——隔离前禁止使用** |
| `getIpcTerminalLine().getOutput()`（**非空**缓冲，79 字符） | ❓ 首次非空读取未成功——与 getPrompt 同 payload 无法归因，需隔离 |
| `getIpcTerminalLine().getOutput()`（空缓冲，恒 0 时代） | ✅ 已验证安全（§6.1） |
| `taskkill` PT `--progress-bar-server` 子进程 | ⚠️ 合法子进程会重生，别杀；要杀的是**旧的 GUI 挂死实例**（按 StartTime/MainWindowTitle 区分） |

### 7.7 运行环境备忘

- MCP 服务器 conda 环境：`D:\ProgramData\anaconda3\envs\envs\packettracer\python.exe`（系统 python 无 mcp/pytest）
- 当前在线：PT PID 30580（1.pkt 已开）、MCP 已运行 §7.3 新代码、桥端口 54321
- 本会话结束时引擎状态：**活着**（env 正常），tl 缓冲留有 79 字符未读内容
- 结果队列：空（env 最后一次 drain 已清）

---

## 八、第四次会话（2026-09-25）：传输层撇号 bug + PC CLI 路径发现 + 实验全部完成

### 8.1 结论速览（续接必读）

| # | 结论 | 状态 |
|---|------|------|
| 1 | **"SyntaxError: Parse error" 弹窗根因 = shim 传输层真 bug**：`reportResult` 把 payload `encodeURIComponent` 后嵌入**单引号 JS 字面量**，而 `encodeURIComponent` **不转义 `'`** → payload 含撇号即击穿字面量 → PT 弹 Parse error、**webview 冻结**（表现为后续所有命令超时）。修复：`.replace(/'/g,"%27")` | ✅ 已修复+测试 |
| 2 | **tl 79/81 字符之谜破案**：`getIpcTerminalLine()` 返回对象**根本没有 `getOutput` 方法**（TypeError 恰 75 字符；`'EXC:'+75=79`、`'TLEXC:'+75=81`）。之前所有"tl 缓冲 79 字符"都是**错误消息的长度**，错误文本含 `'getOutput'` 撇号 → 正是击穿传输层的内容源。§7.4 的两个悬念全部闭合 | ✅ 实测证实 |
| 3 | **IOS 设备 ping 输出：PT 脚本 API 不暴露**。穷尽检查：`getCommandLine().getOutput()`（GUI 控制台，只有 boot+syslog，4933 字节不变）、`getIpcTerminalLine()`（无 getOutput）、`getConsole().getTerminalLine()`（=GUI 控制台同一缓冲）、`getTelnetClientAt/Count`（3 个终端对象全部 0 个会话）。ping 确实执行（`.first=0`），但文本拿不到 → IOS 侧 pt_ping 用 **`show ip arp` 兜底**作为间接证据 | ✅ 定论 |
| 4 | **重大发现：PC 的 CLI 路径** = `device.getCommandPrompt()` → 命令提示符 TerminalLine，**同时有 `getOutput`/`enterCommand`/`getMode`/`getPrompt`**。`enterCommand` 为**单参数**形态（双参报 `IPC Call ERROR: Invalid arguments`），输出进 `getOutput()` 累积缓冲 → **PC 发起的 ping/ipconfig 全文可捕获** | ✅ 实测证实 |
| 5 | **§6.2 旧矩阵纠错**：PC 设备对象**没有 `enterCommand` 也没有 `skipBoot`**（"PC enterCommand 安全"是僵尸进程污染时代的错误结论）；`getCommandLine` 在 PC 上存在但别调用。PC 唯一 CLI 入口是 `getCommandPrompt()` | ✅ 已固化进代码 |
| 6 | **代码固化**：`exec_cli` 双路径（PC/IOS 自动探测）+ `async_start`/`async_collect` 两阶段 + `queue.ping()`；`pt_ping` PC 全文回传、IOS ARP 兜底；`pt_traceroute` 两阶段化；shim 撇号修复。离线测试 **4/4 通过** | ✅ |
| 7 | **实验（§四）全部完成**：阶段一同 VLAN ✅ / 跨 VLAN ❌（无网关）→ 网关下发 → 阶段二跨 VLAN 全 ✅（**TTL=127 实证三层路由**） | ✅ |
| 8 | drain 测试端口冲突修复（独立端口），配置保存 ×3，拓扑导出存档 `topology_export.json` | ✅ |

### 8.2 排障过程与证据链

1. **弹窗→冻结链还原**（用户两次看到弹窗）：带内容的探测 payload（tl"内容"=`EXC:TypeError: Property 'getOutput' of object [object Object] is not a function`）→ encodeURIComponent 原样保留 2 个 `'` → 内层 `x.send(decodeURIComponent('...'))` 字面量被击穿 → evaluateJavaScriptAsync 抛 Parse error（**模态弹窗**）→ webview 事件循环冻结 → `/status` 显示 connected 但 `last_poll_ago` 疯涨，一切命令超时。用户关弹窗后恢复。**所有"引擎挂死"假象（含 §7.4 tl_dump 超时、tl_dump2/阶梯/charCodes 探针失败）全部由此解释**——引擎从未真正挂死。
2. **隔离实验定案 tl**：`getMode()` 秒回（mode=enable）；`getOutput()` 无报告；cl-first 顺序下长度可读（81）但内容传输即弹窗；charCodes 纯数字传输成功（tl_len=0）；最终 `js_multi` 多点上报直接打印出 **TypeError 原文** → 79/81 = 错误串长度，全案闭合。
3. **PC CLI 发现链**：pc2 的 `pt_ping` 45s 无回报 → 多点上报探针定位 `enterCommand` 不存在（TypeError）→ 对比 switchC/pc2 方法表 → pc2 独有 `getCommandPrompt` → keys dump 显示**全套终端方法** → `ipconfig` 单参数调用成功且全文可读 → `ping` 输出滞后 15-30s 进缓冲（+8s 时仅命令回显，~30s 全文）→ 两阶段采集设计定型。
4. **工具层教训（严禁再犯）**：两次弹窗的**源头都是 shell `-c` 内联 JS 的转义损坏**（PowerShell 双引号层把 `\n` 变成裸换行进字符串字面量 → parse error）。修复后全部改文件型探针。工具脚本沉淀：`js_run.py`（单探针）、`js_multi.py`（多点上报收集，定位死点必备）、`cli_run.py`（完整 CLI 输出，绕过 pt_send_commands 每行 150 字符截断）、`probes/*.js`（全部探测记录留档）。

### 8.3 代码变更（本轮，与 §7.3 一起待提交）

| 文件 | 变更 |
|------|------|
| `src/bridge/script_builder.py` | ① shim `reportResult` 撇号修复（`replace(/'/g,"%27")`）；② `exec_cli` 重写为双路径：JS 内探测 `getCommandPrompt`（PC：单参 enterCommand + spin 500ms + 缓冲 delta 采集）否则 IOS 路径（两参 enterCommand + `.second`）；③ 新增 `async_start`/`async_collect`（PC：`lastIndexOf(命令)` 锚定缓冲增量；IOS：`fallback_cmd` 同步兜底） |
| `src/bridge/command_queue.py` | 新增 `async_cli(name, command, fallback_cmd, settle)` 两阶段流程与 `PING_SETTLE_SECONDS=15`（实测 ping 输出 +8s 未现、~30s 齐全）；新增 `ping()`（IOS 兜底 `show ip arp`） |
| `src/tools/topology.py` | `pt_ping` 改走 `queue.ping`（PC 返回 ping 全文，IOS 返回 ARP 表 + 说明）；`pt_traceroute` 改走 `async_cli` 两阶段 |
| `tests/test_bridge_roundtrip.py` | FakePTWebview 新增 `started:true`/pc-buffer/ios-fallback 分支（ios-fallback 用 `"show ip arp" in body` 判别——两个分支的字符串同在一份 payload 里）；roundtrip 增加段 7（PC ping 两阶段）/段 8（IOS ARP 兜底）；shim 撇号修复 + PC 路径断言；drain 测试改用独立端口（修复 10048 端口占用） |
| 新增 | `js_run.py`、`js_multi.py`、`cli_run.py`（排查工具链）、`probes/*.js`（探测记录）、`topology_export.json`（实验存档） |
| 删除 | `diag_report.py`、`tl_probe_isolate.py`（一次性诊断脚本） |

### 8.4 实验最终结果（§四 待办全部完成）

**配置面（全部逐条 ✓ 确认后二次核实）：**
- switchC：hostname/ip routing/vlan 10,20/SVI10=192.168.0.1、SVI20=192.168.1.1（`show ip int brief` 双 up/up）/Fa0/1-2 dot1q trunk（show run 核实）
- switchA/B：hostname/vlan 10,20/Fa0/1→access 10、Fa0/2→access 20、Fa0/23→trunk（`show vlan brief` 核实端口分配）
- PC（无网关→阶段二加网关）：pc1=192.168.1.2、pc2=192.168.0.2、pc3=192.168.0.3、pc4=192.168.1.3（ipconfig 实测网关生效）
- `pt_save_config` ×3 ✓（write memory 确认捕获）；`pt_validate` 7 devices/6 connections 无错误；拓扑导出 `topology_export.json`

**连通性（PC 命令提示符实测，全文捕获）：**

| 阶段 | 测试 | 结果 |
|------|------|------|
| 一（无网关） | pc2→pc3（同 VLAN10） | ✅ 3/4（首包 ARP 超时属正常） |
| 一 | pc1→pc4（同 VLAN20） | ✅ 3/4 |
| 一 | pc2→pc1（跨 VLAN） | ❌ 4/4 超时（预期） |
| 二（网关） | pc2→pc1（跨 VLAN） | ✅ 4/4 **TTL=127** |
| 二 | pc1→pc3（跨 VLAN） | ✅ 3/4 TTL=127 |
| 二 | pc2→pc4（跨 VLAN） | ✅ 3/4 TTL=127 |

TTL 128→127 = 恰经一次三层转发，`show ip route` 两条 C 直连路由、`show ip arp` 学到 pc1/pc2/pc3 MAC —— **利用三层交换机实现 VLAN 间通信实验目标全部达成**。
（注：跨 VLAN 首测曾 4/4 超时，为网关下发后 ARP/路由收敛竞态，稳定后复测即通。）

### 8.5 残留事项

1. ~~用户重启 MCP 服务器 → 激活本轮代码~~ ✅ 已重启并端到端验收：`pt_ping(pc2, 192.168.1.2)` **直接返回 ping 全文**（4/4、TTL=127、0% 丢包）
2. ~~git 提交~~ ✅ `af75017`（41 文件 +2454/−103）
3. ~~IOS 兜底 `__ctext` 未定义~~ ✅ 会话内发现并修复（`async_collect` 补拼 `_CTEXT_JS`），经桥直测返回完整 ARP 表（4 台 PC 双 VLAN 全部在列）；测试 4/4 通过。该一行修复需**下次重启 MCP** 后 MCP 侧 `pt_ping(IOS 设备)` 生效（桥层已验证）

### 8.6 安全矩阵终版（取代 §6.2/§7.6）

| 调用 | 3560/2960 | PC-PT |
|------|-----------|-------|
| `device.enterCommand(cmd, mode)` 双参 | ✅（`.second`=同步输出） | ❌ **方法不存在**（TypeError） |
| `device.getCommandPrompt()` → 单参 `enterCommand(cmd)` + `getOutput()` | ❌ 方法不存在 | ✅ **PC 唯一 CLI 路径** |
| `device.skipBoot()` | ✅ | ❌ 方法不存在（shim 已兼容） |
| `getCommandLine()`/`getIpcTerminalLine()` 读取 | ✅ 安全（但**不含** ping 输出） | 🚫 永不调用（旧矩阵的挂死记录） |
| `getConsole().getTerminalLine()` | ✅（=GUI 控制台缓冲） | 未测 |
| `getIpcTerminalLine().getPrompt()` | ❓ 疑似阻塞（tl_dump 超时主嫌，未隔离） | — |
| payload 含 `'` 的 reportResult | ❌ **已修复**（%27 转义），修复前=弹窗+冻结 | 同 |
| setTimeout 裸回调（仅 reportResult） | ✅ | ✅ |
| setTimeout 回调内任何 IPC | 🚫 挂死 | 🚫 同 |
| shell `-c` 内联 JS 探测 | 🚫 **禁止**（转义损坏→Parse error） | 🚫 同 |

---
