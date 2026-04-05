"""
File processing tools.
"""

import os
from typing import Optional


def _ensure_directory_exists(path: str) -> bool:
    """Ensure the directory for the given file path exists; create if needed."""
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
            return True
        except OSError as e:
            return False
    return True


def file_write(path: str, content: str, mode: Optional[str] = None) -> str:
    """
    Write content to a file.

    Args:
        path: Absolute or relative path to the file.
        content: String content to write.
        mode: Write mode ('overwrite', 'append', or None).
    Returns:
        String with success or error message, including absolute path.
    """
    # Convert to absolute path
    abs_path = os.path.abspath(path)

    # Ensure directory exists
    if not _ensure_directory_exists(abs_path):
        return f"Error: Could not create directory for {abs_path}"

    # Determine mode if not specified
    if mode is None:
        mode = "overwrite"

    try:
        if mode == "overwrite":
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"Successfully wrote to {abs_path}"
        elif mode == "append":
            with open(abs_path, 'a', encoding='utf-8') as f:
                f.write(content)
            return f"Successfully appended to {abs_path}"
        else:
            return f"Error: Invalid mode '{mode}'. Must be 'overwrite', 'append', or None."
    except Exception as e:
        return f"Error writing to file '{abs_path}' (resolved from '{path}'): {str(e)}"


def file_replace(path: str, old: str, new: str, replace_all: bool = False) -> str:
    """
    Replace occurrences of a substring in a file.

    Args:
        path: Absolute or relative path to the file.
        old: Substring to replace.
        new: Replacement substring.
        replace_all: If True, replace all occurrences; otherwise replace only the first.

    Returns:
        String with success or error message, including absolute path.
    """
    # Convert to absolute path
    abs_path = os.path.abspath(path)

    # Check file existence
    if not os.path.exists(abs_path):
        return f"Error: File not found: {abs_path} (resolved from '{path}')"

    if not os.path.isfile(abs_path):
        return f"Error: Path is not a file: {abs_path} (resolved from '{path}')"

    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Perform replacement
        if replace_all:
            new_content = content.replace(old, new)
        else:
            new_content = content.replace(old, new, 1)

        # Write back only if changes were made
        if new_content != content:
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return f"Successfully replaced in {abs_path}"
        else:
            return f"No occurrences found to replace in {abs_path}"

    except Exception as e:
        return f"Error processing file '{abs_path}' (resolved from '{path}'): {str(e)}"

def file_read(path: str, offset: int = 0, lines: int = 100) -> str:
    """
    Read a portion of a file, adding line numbers and enforcing a maximum length.

    Args:
        path: Absolute or relative path to the file.
        offset: Number of lines to skip from the beginning (0-indexed).
        lines: Number of lines to read. If negative, read all remaining lines.

    Returns:
        String containing the requested lines, each prefixed with its line number
        (starting from offset+1) and a colon. The total string length is limited
        to 8000 characters; longer output is truncated. On failure, returns an
        error message starting with "Error:".
    """
    abs_path = os.path.abspath(path)

    if not os.path.exists(abs_path):
        return f"Error: File not found: {abs_path} (resolved from '{path}')"

    if not os.path.isfile(abs_path):
        return f"Error: Path is not a file: {abs_path} (resolved from '{path}')"

    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            # Skip offset lines
            for _ in range(offset):
                try:
                    next(f)
                except StopIteration:
                    return ""

            output = ""
            line_num = offset + 1
            max_chars = 8000

            # Determine how many lines to read
            if lines < 0:
                # Read until EOF or length limit
                for current_line in f:
                    line_with_num = f"{line_num}:{current_line}"
                    if len(output) + len(line_with_num) > max_chars:
                        remaining = max_chars - len(output)
                        if remaining > 0:
                            output += line_with_num[:remaining]
                        break
                    output += line_with_num
                    line_num += 1
            else:
                # Read up to 'lines' lines
                for _ in range(lines):
                    try:
                        current_line = next(f)
                    except StopIteration:
                        break
                    line_with_num = f"{line_num}:{current_line}"
                    if len(output) + len(line_with_num) > max_chars:
                        remaining = max_chars - len(output)
                        if remaining > 0:
                            output += line_with_num[:remaining]
                        break
                    output += line_with_num
                    line_num += 1

            return output

    except Exception as e:
        return f"Error reading file '{abs_path}' (resolved from '{path}'): {str(e)}"


FILE_TOOLS = {
    "file_write": file_write,
    "file_replace": file_replace,
    "file_read": file_read,
}