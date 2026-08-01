# network_diagnostic_app.py
# Chainlit frontend for the network diagnostic agent
# Run: chainlit run network_diagnostic_app.py

import importlib.util
from pathlib import Path

import chainlit as cl

# Import agent creation function from the existing diagnostic module
# (filename starts with a digit, so use importlib instead of normal import)
_MODULE_PATH = Path(__file__).parent / "network_diagnostic_agent.py"
_spec = importlib.util.spec_from_file_location("network_diagnostic_agent", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
create_diagnostic_agent = _mod.create_diagnostic_agent


@cl.on_chat_start
async def on_chat_start():
    """Initialize the diagnostic agent and message history when a new chat session starts."""
    agent = create_diagnostic_agent()
    cl.user_session.set("agent", agent)
    # Store conversation history for multi-turn support
    cl.user_session.set("message_history", [])
    await cl.Message(
        content=(
            "👋 你好！我是网络诊断助手，请描述你遇到的网络问题，"
            "我会按 OSI 分层逐步帮你排查。\n\n"
            "例如：**我无法访问 www.baidu.com**"
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    """Handle user message with multi-turn conversation support."""
    agent = cl.user_session.get("agent")
    message_history = cl.user_session.get("message_history")

    # Append user message to history
    message_history.append(("user", message.content))

    # Chainlit callback handler automatically displays
    # intermediate tool calls and outputs in the UI
    cb = cl.LangchainCallbackHandler()

    # Run agent asynchronously with full conversation history
    # so the agent can see previous Q&A context (e.g. follow-up after asking for a URL)
    result = await cl.make_async(agent.invoke)(
        {"messages": message_history},
        config={"callbacks": [cb], "recursion_limit": 50},
    )

    # Extract the final AI response and append to history
    response = result["messages"][-1].content
    message_history.append(("assistant", response))

    await cl.Message(content=response).send()
