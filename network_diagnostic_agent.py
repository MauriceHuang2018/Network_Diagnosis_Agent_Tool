# network_diagnostic_agent.py
# Network diagnostic agent based on OSI layered troubleshooting methodology
# Uses LangChain 1.x create_agent with @tool-decorated network tools

from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain_community.chat_models import ChatTongyi
import logging
import os
import platform
import socket
import subprocess
import sys
import time
import dashscope

# Force UTF-8 stdout so Chinese output displays correctly on Windows consoles (default cp936)
sys.stdout.reconfigure(encoding="utf-8")

# Platform detection for cross-platform command support
IS_WINDOWS = platform.system() == "Windows"

# Maximum characters for command output (prevents LLM context overflow)
MAX_OUTPUT = 3000

# Get API key from environment variable
api_key = os.environ.get('DASHSCOPE_API_KEY')
dashscope.api_key = api_key


# ============================================================
# Helper: run shell command with timeout and output truncation
# ============================================================

def _run_command(command_args: list, timeout: int = 15) -> str:
    """Run a command (arg list) and return combined stdout/stderr, truncated if too long."""
    try:
        result = subprocess.run(
            command_args,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        output = result.stdout or ""
        if result.stderr:
            output += ("\n[stderr]\n" + result.stderr) if output else result.stderr
        output = output.strip()
        if not output:
            return "(无输出)"
        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + f"\n... (输出已截断，共 {len(output)} 字符)"
        return output
    except subprocess.TimeoutExpired:
        return f"命令超时（{timeout}秒）：{' '.join(command_args)}"
    except FileNotFoundError:
        return f"命令未找到：{command_args[0]}（可能未安装或不在PATH中）"
    except Exception as e:
        return f"命令执行失败: {e}"


# ============================================================
# Layer 1/2: Physical & Data Link Layer Tools
# ============================================================

@tool
def check_physical_connection() -> str:
    """检查物理层和数据链路层连接状态（Layer 1/2）：查看网卡状态、MAC地址、连接介质类型。
    无需参数。用于排查网线未插、网卡禁用等物理层问题。
    """
    if IS_WINDOWS:
        output = "=== 网卡MAC地址与连接状态 (getmac /v) ===\n"
        output += _run_command(["getmac", "/v", "/fo", "list"])
        return output
    else:
        output = "=== 网络接口状态 (ip link) ===\n"
        output += _run_command(["ip", "link"])
        output += "\n\n=== ARP表 (arp -n) ===\n"
        output += _run_command(["arp", "-n"])
        return output


# ============================================================
# Layer 3: Network Layer Tools
# ============================================================

@tool
def check_ip_config() -> str:
    """检查网络层IP配置（Layer 3）：IP地址、子网掩码、默认网关、DNS服务器等。
    无需参数。用于排查IP地址冲突、子网配置错误、网关不可达等问题。
    """
    if IS_WINDOWS:
        return _run_command(["ipconfig", "/all"])
    else:
        return _run_command(["ip", "addr"])


@tool
def ping_host(host: str, count: int = 4) -> str:
    """网络层ICMP连通性测试（Layer 3）：ping指定主机，测试基本网络可达性和延迟。
    参数:
        host: 目标主机名或IP地址（如 8.8.8.8 或 baidu.com）
        count: 发送的数据包数量，默认4
    返回:
        ping结果，包括丢包率和往返时间
    """
    if not host:
        return "请提供目标主机"
    try:
        count = max(1, min(int(count), 20))
    except (TypeError, ValueError):
        count = 4
    if IS_WINDOWS:
        cmd = ["ping", "-n", str(count), "-w", "3000", host]
    else:
        cmd = ["ping", "-c", str(count), "-W", "3", host]
    return _run_command(cmd, timeout=count * 4 + 5)


@tool
def traceroute_host(host: str, max_hops: int = 10) -> str:
    """网络层路由追踪（Layer 3）：追踪到目标主机的路由路径，定位网络中断节点。
    参数:
        host: 目标主机名或IP地址
        max_hops: 最大跳数，默认10
    返回:
        路由路径上各跳的延迟信息
    """
    if not host:
        return "请提供目标主机"
    try:
        max_hops = max(1, min(int(max_hops), 30))
    except (TypeError, ValueError):
        max_hops = 10
    if IS_WINDOWS:
        cmd = ["tracert", "-h", str(max_hops), "-w", "1000", host]
    else:
        cmd = ["traceroute", "-m", str(max_hops), "-w", "1", host]
    return _run_command(cmd, timeout=max_hops * 5 + 10)


# ============================================================
# Layer 4: Transport Layer Tools
# ============================================================

@tool
def test_tcp_port(host: str, port: int, timeout: int = 5) -> str:
    """传输层TCP端口连通性测试（Layer 4）：测试目标主机的TCP端口是否开放，功能类似 telnet host port。
    使用Python socket实现，比telnet命令更可靠（Windows默认未安装telnet客户端）。
    参数:
        host: 目标主机名或IP地址
        port: 目标TCP端口号（如 80、443、22）
        timeout: 连接超时秒数，默认5
    返回:
        端口连通性结果（开放/关闭/超时）及连接耗时
    """
    if not host:
        return "请提供目标主机"
    try:
        port = int(port)
        timeout = max(1, min(int(timeout), 20))
    except (TypeError, ValueError):
        return "端口和超时必须是整数"
    if not (1 <= port <= 65535):
        return f"端口号无效: {port}（应在1-65535范围内）"
    start = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            elapsed = time.time() - start
            return f"TCP端口连通: {host}:{port} 开放（连接耗时 {elapsed:.2f} 秒）"
    except socket.timeout:
        return f"TCP端口超时: {host}:{port} 可能被防火墙过滤（无响应）"
    except ConnectionRefusedError:
        return f"TCP端口拒绝连接: {host}:{port} 关闭或服务未运行（收到RST）"
    except socket.gaierror as e:
        return f"域名解析失败: {host} ({e})"
    except Exception as e:
        return f"TCP端口测试失败: {host}:{port} ({e})"


@tool
def check_listening_ports() -> str:
    """传输层监听端口检查（Layer 4）：查看本机当前监听的TCP/UDP端口和对应进程。
    无需参数。用于排查服务是否在预期端口监听。
    """
    if IS_WINDOWS:
        return _run_command(["netstat", "-ano"], timeout=15)
    else:
        out = _run_command(["ss", "-tulpn"], timeout=15)
        if "命令未找到" in out:
            out = _run_command(["netstat", "-tulpn"], timeout=15)
        return out


# ============================================================
# Layer 7: Application Layer Tools
# ============================================================

@tool
def dns_lookup(domain: str, dns_server: str = "") -> str:
    """应用层DNS查询（Layer 7，DNS）：查询域名对应的IP地址，排查DNS解析问题。
    参数:
        domain: 要查询的域名（如 baidu.com）
        dns_server: 可选，指定DNS服务器（如 8.8.8.8），留空使用系统默认
    返回:
        DNS解析结果，包括A记录IP地址
    """
    if not domain:
        return "请提供要查询的域名"
    if dns_server:
        cmd = ["nslookup", domain, dns_server]
    else:
        cmd = ["nslookup", domain]
    return _run_command(cmd, timeout=10)


@tool
def http_request(url: str, method: str = "GET", timeout: int = 10) -> str:
    """应用层HTTP请求测试（Layer 7，HTTP/HTTPS）：使用curl测试Web服务可达性和响应状态。
    参数:
        url: 目标URL（如 https://www.baidu.com）
        method: HTTP方法，默认GET
        timeout: 请求超时秒数，默认10
    返回:
        HTTP状态码、响应头和部分响应体
    """
    if not url:
        return "请提供目标URL"
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    try:
        timeout = max(1, min(int(timeout), 30))
    except (TypeError, ValueError):
        timeout = 10
    method = method.upper()
    cmd = ["curl", "-s", "-i", "-m", str(timeout), "-X", method, url]
    result = _run_command(cmd, timeout=timeout + 5)
    # Truncate very long HTTP responses
    if len(result) > 2000:
        result = result[:2000] + f"\n... (响应已截断，共 {len(result)} 字符)"
    return result


@tool
def check_firewall() -> str:
    """网络/传输层防火墙状态检查（Layer 3/4）：查看本机防火墙是否启用及规则概况。
    无需参数。用于排查防火墙阻断连通性的问题。
    """
    if IS_WINDOWS:
        return _run_command(
            ["netsh", "advfirewall", "show", "allprofiles", "state"],
            timeout=10,
        )
    else:
        out = _run_command(["ufw", "status"], timeout=10)
        if "命令未找到" in out:
            out = _run_command(["iptables", "-L", "-n"], timeout=10)
        return out


@tool
def check_service_status(service_name: str) -> str:
    """应用层服务状态检查（Layer 7）：查询指定服务是否运行，排查应用层服务问题。
    参数:
        service_name: 服务名称（Windows如 w3svc、dnscache；Linux如 nginx、ssh）
    返回:
        服务运行状态
    """
    if not service_name:
        return "请提供服务名称"
    if IS_WINDOWS:
        return _run_command(["sc", "query", service_name], timeout=10)
    else:
        return _run_command(["systemctl", "status", service_name], timeout=10)


@tool
def read_debug_log(log_path: str, lines: int = 50) -> str:
    """应用层调试日志查看（Layer 7）：读取指定日志文件的末尾若干行，用于排查应用层故障。
    参数:
        log_path: 日志文件路径
        lines: 读取末尾的行数，默认50
    返回:
        日志末尾内容
    """
    if not log_path:
        return "请提供日志文件路径"
    try:
        lines = max(1, min(int(lines), 500))
    except (TypeError, ValueError):
        lines = 50
    if not os.path.isfile(log_path):
        return f"日志文件不存在: {log_path}"
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        tail = all_lines[-lines:]
        return f"日志文件 {log_path} 末尾 {len(tail)} 行:\n" + "".join(tail)
    except Exception as e:
        return f"读取日志失败: {e}"


# ============================================================
# System prompt for the diagnostic agent
# ============================================================

SYSTEM_PROMPT = """你是一个专业的网络诊断Agent。请严格按照以下流程进行网络故障排查：

═══ 第一步：目标提取 ═══
从用户描述中提取诊断目标（URL、主机名、IP地址、端口号等）。
- 如果用户提到具体的网站/服务器（如"无法访问 www.baidu.com"），提取出目标主机名，后续所有工具调用都应以该目标为检测对象
- 如果用户提到端口号（如"数据库3306连不上"），提取出目标主机和端口
- 如果用户只描述了症状（如"上不了网"），没有指定目标，则先询问用户："请提供您要访问的具体网站地址或服务器IP，以便我进行针对性排查。" 不要使用任何工具，等待用户回复。如果用户仍未提供目标，则告知用户："未提供具体目标，我将检查本机网络配置。"然后再使用本机诊断工具排查

═══ 第二步：按OSI分层排查 ═══
根据提取的目标，按以下分层顺序排查：

1. 物理层（Layer 1/2）：确认物理连接 - 检查网卡状态、MAC地址、线缆连接（用 check_physical_connection）
2. 网络层（Layer 3）：检查IP配置（check_ip_config）、使用ping（ping_host）测试连通性、使用traceroute（traceroute_host）追踪路由
3. 传输层（Layer 4）：使用TCP端口测试（test_tcp_port，类似telnet）测试端口连通性、检查监听端口（check_listening_ports）
4. 应用层（Layer 7）：使用DNS查询（dns_lookup）解析域名、使用HTTP请求（http_request，curl）测试Web服务、检查防火墙（check_firewall）、检查服务状态和配置（check_service_status / read_debug_log）

═══ 排查原则 ═══
- 针对访问外部主机/网站的问题，必须以用户指定的目标执行 ping_host、dns_lookup、test_tcp_port、http_request 等工具，而非只检查本机配置
- 至少使用网络层(L3)、传输层(L4)、应用层(L7)各一个工具进行排查，以便定位故障层
- 从物理层到应用层逐层排查，先排除底层问题再往上查
- 每一步根据结果决定是否需要继续上层排查
- 最后给出明确的诊断结论，指出问题出在OSI哪一层及建议

═══ 示例 ═══
用户："我无法访问 www.baidu.com"
目标提取：www.baidu.com
→ dns_lookup("www.baidu.com") → ping_host("www.baidu.com") → test_tcp_port("www.baidu.com", 443) → http_request("https://www.baidu.com")

用户："数据库 192.168.1.100:3306 连不上"
目标提取：192.168.1.100, 端口3306
→ ping_host("192.168.1.100") → test_tcp_port("192.168.1.100", 3306) → check_service_status("mysql")"""


# ============================================================
# Create the diagnostic agent
# ============================================================

def create_diagnostic_agent():
    """创建网络诊断Agent"""
    tools = [
        # Layer 1/2
        check_physical_connection,
        # Layer 3
        check_ip_config,
        ping_host,
        traceroute_host,
        # Layer 4
        test_tcp_port,
        check_listening_ports,
        # Layer 7
        dns_lookup,
        http_request,
        check_firewall,
        check_service_status,
        read_debug_log,
    ]
    llm = ChatTongyi(model_name="qwen-turbo", dashscope_api_key=api_key)
    agent = create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)
    return agent


def process_diagnosis(task_description: str) -> str:
    """使用网络诊断Agent排查故障

    参数:
        task_description: 故障描述
    返回:
        诊断结果
    """
    try:
        agent = create_diagnostic_agent()
        result = agent.invoke(
            {"messages": [("user", task_description)]},
            config={"recursion_limit": 50},
        )
        return result["messages"][-1].content
    except Exception as e:
        return f"诊断过程出错: {str(e)}"


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    # Test: diagnose connectivity to baidu.com (exercises L3, L4, L7 tools)
    task = "我无法访问 www.ifeng.com，请按网络分层步骤帮我诊断问题出在哪个地方。"
    print("诊断任务:", task)
    print("=" * 60)
    result = process_diagnosis(task)
    print("诊断结果:")
    print(result)
