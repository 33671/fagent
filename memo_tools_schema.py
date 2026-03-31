"""
Tool schema definitions for memo tools.
"""

MEMO_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "todos_write",
            "description": "write new todos, which will remind you every time user send a new message",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "todos to overwrite",
                        "maxLength": 1000
                    },
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todos_clear",
            "description": "Clears current todos",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]