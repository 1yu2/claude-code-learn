"""
s01_agent_loop.py - The Agent Loop
本文展示最小的、有实用价值的 coding-agent 模式：
    用户消息
      -> 模型回复
      -> 若使用工具：执行工具
      -> 将工具结果写回消息列表
      -> 继续循环
代码刻意保持精简，但将循环状态显式化，
后续章节可在此基础上扩展更多功能。
"""
import os
import subprocess
from dataclasses import dataclass

# macOS 上 readline 的 UTF-8 退格键修复（#143）
try:
    import readline
    readline.parse_and_bind('set bind-tty-special-chars off')
    readline.parse_and_bind('set input-meta on')
    readline.parse_and_bind('set output-meta on')
    readline.parse_and_bind('set convert-meta off')
    readline.parse_and_bind('set enable-meta-keybindings on')
except ImportError:
    pass

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)

# 初始化 OpenAI 客户端，从环境变量读取配置
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL") or None,
)

# 模型名称，默认使用 gpt-4.1-mini（实际使用时通过环境变量覆盖）
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

# 系统提示词，定义 agent 的角色定位和行为原则
SYSTEM = (
    f"You are a coding agent at {os.getcwd()}."
    "use bash to inspect and change the workspace.Act first, then report clearly."
)

# 定义 agent 可用的工具列表，当前只有一个 bash 工具
TOOLS = [{
    "type": "function",
    "function": {
        "name": "bash",
        "description": "use bash to inspect and change the workspace",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "the command to execute"
                }
            },
            "required": ["command"]
        }
    }
}]

# 循环状态数据类，用于在 agent 循环中保存上下文
@dataclass
class LoopState:
    messages: list          # 对话历史消息列表
    turn_count: int = 1     # 当前轮次计数
    transition_reason: str | None = None  # 状态转换原因（用于调试/追踪）

def run_bash(command: str) -> str:
    """
    在本地执行 bash 命令并返回执行结果。
    包含基本的安全检查，防止执行危险命令。
    """
    dangerous = ['rm -rf /', 'sudo', 'shutdown', 'reboot', '> /dev/']
    if any(item in command for item in dangerous):
        return "Error: Dangerous command blocked"
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=os.getcwd(),      # 在当前工作目录执行
            capture_output=True, # 捕获 stdout 和 stderr
            text=True,            # 返回字符串而非字节
            timeout=120,          # 120 秒超时
        )
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"

    # 合并 stdout 和 stderr，并限制返回长度
    output = (result.stdout + result.stderr).strip()
    return output[:50000] if output else "(no output)"

def extract_text(content) -> str:
    """
    从模型返回的 content 中提取纯文本。
    content 可能是字符串，也可能是包含多个部分的列表。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                # 兼容不同格式的文本块：output_text 或 text 类型
                if item.get("type") in ("output_text", "text"):
                    parts.append(item.get("text", ""))
            elif hasattr(item, "text"):
                parts.append(item.text)
        return "\n".join(part for part in parts if part)
    return ""

def execute_tool_calls(tool_calls) -> list:
    """
    执行模型调用的工具，返回工具执行结果列表。
    每个结果包含 role、tool_call_id 和 content。
    """
    import json

    results = []
    for tool_call in tool_calls or []:
        if tool_call.function.name != "bash":
            result = f"Error: Unknown tool {tool_call.function.name}"
        else:
            try:
                # 解析工具参数（JSON 格式）
                arguments = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError as e:
                result = f"Error: Invalid tool arguments: {e}"
            else:
                # 执行 bash 命令
                result = run_bash(arguments.get("command", ""))

        results.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result,
        })
    return results

def run_one_turn(state: LoopState) -> bool:
    """
    执行单轮 agent 交互：
    1. 调用模型生成回复
    2. 将回复追加到消息历史
    3. 若有工具调用则执行，并将结果加入消息历史
    4. 返回是否需要继续下一轮（使用工具时返回 True）
    """
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": SYSTEM}] + state.messages,
        tools=TOOLS,
        max_tokens=8000,
    )

    # 安全检查：确保 API 返回了有效 choices
    if not response.choices:
        print(f"API error: {response}")
        return False

    message = response.choices[0].message
    # 将模型回复存入消息历史（转为字典以保留结构）
    state.messages.append(message.model_dump(exclude_none=True))

    # 执行工具调用（若模型未调用工具则此处返回空列表）
    tool_results = execute_tool_calls(message.tool_calls)
    if not tool_results:
        # 无工具调用，本轮结束
        state.transition_reason = None
        return False

    # 将工具执行结果追加到消息历史，继续下一轮
    state.messages.extend(tool_results)
    state.turn_count += 1
    state.transition_reason = "tool_use"
    return True

def agent_loop(state: LoopState) -> None:
    """
    主循环：持续执行直到模型不再调用工具。
    """
    while run_one_turn(state):
        pass

if __name__ == "__main__":
    history = []
    print("\033[36ms01 >> \033[0m", end="", flush=True)

    while True:
        try:
            query = input("\033[36ms01 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break

        # 输入 q、exit 或空行则退出
        if query.strip().lower() in ("q", "exit", ""):
            break

        # 将用户消息加入历史并启动 agent 循环
        history.append({"role": "user", "content": query})
        state = LoopState(messages=history)
        agent_loop(state)

        # 从最后一条模型消息中提取文本并打印
        final_text = extract_text(history[-1]["content"])
        if final_text:
            print(final_text)
        print()