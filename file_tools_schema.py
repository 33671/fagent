"""
Tool schema definitions for file tools.
"""

FILE_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "Write string content to a file. Creates parent directories if needed. Mode determines write behavior: if not specified,  write uses 'overwrite'. Explicit mode can be set to 'overwrite' or 'append'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file",
                    },
                    "content": {
                        "type": "string",
                        "description": "The text content to write to the file",
                    },
                    "mode": {
                        "type": "string",
                        "description": "Write mode.",
                        "enum": ["overwrite", "append"],
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_replace",
            "description": "Replace occurrences of a substring in a file. Optionally replace all occurrences or only the first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file",
                    },
                    "old": {
                        "type": "string",
                        "description": "The substring to be replaced",
                    },
                    "new": {
                        "type": "string",
                        "description": "The replacement substring",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "If True, replace all occurrences; otherwise replace only the first occurrence",
                        "default": False,
                    },
                },
                "required": ["path", "old", "new"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read a portion of a file. Skips the first 'offset' lines, then reads up to 'lines' lines. If lines is negative, reads all remaining lines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Number of lines to skip from the beginning (0-indexed).",
                        "default": 0,
                        "minimum": 0,
                    },
                    "lines": {
                        "type": "integer",
                        "description": "Number of lines to read. If negative, read all remaining lines.",
                        "default": 100,
                    },
                },
                "required": ["path"],
            },
        },
    },
]