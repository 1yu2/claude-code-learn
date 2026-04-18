"""
s01_agent_loop.py - The Agent Loop
This file teaches the smallest useful coding-agent pattern:
    user message
      -> model reply
      -> if tool_use: execute tools
      -> write tool_result back to messages
      -> continue
It intentionally keeps the loop small, but still makes the loop state explicit
so later chapters can grow from the same structure.
"""
import os
import subprocess
from dataclasses import dataclass
try:
    import readline
    # #143 UTF-8 backspace fix for macOS libedit
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
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"),base_url=os.getenv("OPENAI_BASE_URL"),model=os.getenv("OPENAI_MODEL"))

SYSTEM = (
    f"You are a coding agent at {os.getcwd()}."
    "use bash to inspect and change the workspace.Act first, then report clearly."
)

TOOLS =  [{
        "name":"bash",
        "description":"use bash to inspect and change the workspace",
        "parameters":{
            "type":"object",
            "properties":{
                "command":{
                    "type":"string",
                    "description":"the command to execute"
                }
            },
            "required":["command"]
        }
    }
]