# Internal module state
_memo = ""


def todos_write(content: str) -> str:
    """Overwrite content to memo, returns operation result."""
    global _memo
    _memo = content[:1000]
    msg = "Write successful!"
    if len(content) > 1000:
        msg += "(truncated to 1000 chars)"
    return msg    


def todos_clear() -> str:
    """Clears memo, returns operation result."""
    global _memo
    _memo = ""
    return "All memo content cleared"


def get_memo() -> str:
    """Returns current memo content (for debugging/inspection)."""
    return _memo


MEMO_TOOLS = {
    "todos_write": todos_write,
    "todos_clear": todos_clear,
}