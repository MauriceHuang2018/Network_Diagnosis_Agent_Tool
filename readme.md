# 网络诊断 Agent

基于 OSI 分层模型的智能网络故障诊断 Agent，使用 LangChain + 通义千问 + Chainlit 构建。

## 项目结构

```
CASE-工具链组合/
├── network_diagnostic_agent.py   # 后端：LangChain Agent + 诊断工具
├── network_diagnostic_app.py     # 前端：Chainlit Web 界面
└── readme.md
```

## 功能概览

Agent 按 OSI 分层从底向上逐层排查网络故障，覆盖以下层级：

| OSI 层级 | 诊断工具 | 功能说明 |
|----------|---------|---------|
| Layer 1/2 物理层/数据链路层 | `check_physical_connection` | 检查网卡状态、MAC 地址、连接介质 |
| Layer 3 网络层 | `check_ip_config` | 查看 IP 地址、子网掩码、网关、DNS |
| Layer 3 网络层 | `ping_host` | ICMP 连通性测试，检查可达性和延迟 |
| Layer 3 网络层 | `traceroute_host` | 路由追踪，定位网络中断节点 |
| Layer 4 传输层 | `test_tcp_port` | TCP 端口连通性测试（类 telnet） |
| Layer 4 传输层 | `check_listening_ports` | 查看本机监听端口和对应进程 |
| Layer 7 应用层 | `dns_lookup` | DNS 域名解析查询 |
| Layer 7 应用层 | `http_request` | HTTP 请求测试（curl），检查 Web 服务可达性 |
| Layer 7 应用层 | `check_firewall` | 防火墙状态检查 |
| Layer 7 应用层 | `check_service_status` | 系统服务运行状态查询 |
| Layer 7 应用层 | `read_debug_log` | 读取日志文件末尾内容 |

## 排查流程

```
用户输入故障描述
        │
        ▼
 ┌───────────────┐
 │  目标提取      │  从用户描述中提取 URL / 主机名 / IP / 端口
 └───────┬───────┘
         │
    ┌────┴────┬──────────────┐
    ▼         ▼              ▼
 有明确目标  有端口信息     无目标
    │         │              │
    │         │        ┌─────┴─────┐
    │         │        │ 询问用户   │
    │         │        │ 提供目标   │
    │         │        └─────┬─────┘
    │         │              │
    │         │       用户仍不提供 → 告知后检查本机配置
    │         │              │
    ▼         ▼              ▼
 ┌───────────────────────────────────┐
 │        按 OSI 分层逐层排查         │
 │  Layer 1/2 → Layer 3 → Layer 4   │
 │          → Layer 7                │
 └───────────────┬───────────────────┘
                 │
                 ▼
         诊断结论 + 建议
```

## 环境要求

- Python 3.9+
- Windows 或 Linux 系统
- 通义千问 API Key（环境变量 `DASHSCOPE_API_KEY`）

## 安装依赖

```bash
pip install langchain langchain-core langchain-community dashscope chainlit
```

## 配置

设置通义千问 API Key 环境变量：

```bash
# Windows
set DASHSCOPE_API_KEY=your_api_key_here

# Linux / macOS
export DASHSCOPE_API_KEY=your_api_key_here
```

## 使用方式

### 方式一：Web 界面（推荐）

```bash
chainlit run network_diagnostic_app.py
or
python -m chainlit run network_diagnostic_app.py
```

启动后浏览器自动打开 `http://localhost:8000`，在聊天框中输入网络问题即可。

### 方式二：命令行

```bash
python network_diagnostic_agent.py
```

直接运行后端脚本，使用内置的测试用例进行诊断。

## 交互示例

**场景 1：用户提供了明确目标**

```
用户: 我无法访问 www.baidu.com
Agent: → dns_lookup("www.baidu.com")
       → ping_host("www.baidu.com")
       → test_tcp_port("www.baidu.com", 443)
       → http_request("https://www.baidu.com")
       → 诊断结论
```

**场景 2：用户提供了端口信息**

```
用户: 数据库 192.168.1.100:3306 连不上
Agent: → ping_host("192.168.1.100")
       → test_tcp_port("192.168.1.100", 3306)
       → check_service_status("mysql")
       → 诊断结论
```

**场景 3：用户未提供目标**

```
用户: 上不了网
Agent: 请提供您要访问的具体网站地址或服务器IP，以便我进行针对性排查。

用户: www.ifeng.com
Agent: → dns_lookup → ping_host → test_tcp_port → http_request → 诊断结论
```

**场景 4：用户仍未提供目标**

```
用户: 上不了网
Agent: 请提供您要访问的具体网站地址或服务器IP，以便我进行针对性排查。

用户: 我也不知道，就是上不了网
Agent: 未提供具体目标，我将检查本机网络配置。
       → check_ip_config → ping_host(网关) → check_firewall → 诊断结论
```

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| LLM | 通义千问 (qwen-turbo) | 通过 DashScope API 调用 |
| Agent 框架 | LangChain 1.x `create_agent` | ReAct 风格 tool-calling Agent |
| 工具定义 | `@tool` 装饰器 | LangChain 原生工具声明 |
| Web 界面 | Chainlit | 支持多轮对话、工具调用可视化 |
| 跨平台 | `platform.system()` | 自动适配 Windows/Linux 命令差异 |

## 跨平台支持

所有诊断工具自动适配操作系统：

| 功能 | Windows | Linux |
|------|---------|-------|
| IP 配置 | `ipconfig /all` | `ip addr` |
| 网卡状态 | `getmac /v` | `ip link` |
| Ping | `ping -n` | `ping -c` |
| 路由追踪 | `tracert` | `traceroute` |
| 监听端口 | `netstat -ano` | `ss -tulpn` / `netstat -tulpn` |
| 防火墙 | `netsh advfirewall` | `ufw status` / `iptables -L -n` |
| 服务状态 | `sc query` | `systemctl status` |
