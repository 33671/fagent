import asyncio
import sys
from pathlib import Path
import os

# 加载系统提示 - 从 ~/.fagent/ 目录、包目录或当前工作目录
def load_system_prompt():
    # 方式1: 优先从 ~/.fagent/system_prompt.md 加载（用户自定义）
    user_prompt_file = Path.home() / ".fagent" / "system_prompt.md"
    if user_prompt_file.exists():
        return user_prompt_file.read_text(encoding="utf-8")
    
    # 方式2: 从包目录（安装后）
    pkg_dir = Path(__file__).parent
    prompt_file = pkg_dir / "system_prompt.md"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")
    
    # 方式3: 从工作目录（开发模式兼容）
    prompt_file = Path("system_prompt.md")
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")
    
    # 方式4: 从环境变量
    if "SYSTEM_PROMPT_PATH" in os.environ:
        return Path(os.environ["SYSTEM_PROMPT_PATH"]).read_text(encoding="utf-8")
    
    raise FileNotFoundError("system_prompt.md not found")

SYSTEM_PROMPT = load_system_prompt()

from .queue_utils import Message, command_message, telegram_response_message
from .producers import user_input_producer, terminal_output_producer
from .bot_producer import telegram_bot_producer, get_bot, get_target_chat_id
from .bot_consumer import telegram_bot_consumer
from .consumer import model_consumer, print_consumer


async def main(is_preserved_thinking=False):
    print("=" * 60)
    print(f"Config: isPreservedthinking={is_preserved_thinking}")
    print("Commands:")
    print("  Ctrl+D/exit    - Exit")
    print("  clear          - Clear history")
    print("=" * 60)

    main_queue = asyncio.Queue()
    print_queue = asyncio.Queue()
    user_interrupt_queue = asyncio.Queue()
    telegram_response_queue = asyncio.Queue()

    producers = [
        asyncio.create_task(user_input_producer(main_queue, print_queue, user_interrupt_queue)),
        asyncio.create_task(terminal_output_producer(main_queue, print_queue)),
        asyncio.create_task(telegram_bot_producer(main_queue, print_queue, user_interrupt_queue)),
    ]

    consumers = [
        asyncio.create_task(model_consumer(main_queue, print_queue, user_interrupt_queue,
                                           telegram_response_queue, is_preserved_thinking, SYSTEM_PROMPT)),
        asyncio.create_task(print_consumer(print_queue)),
        asyncio.create_task(telegram_bot_consumer(telegram_response_queue, print_queue,
                                                   get_bot, get_target_chat_id)),
    ]

    done, pending = await asyncio.wait(consumers, return_when=asyncio.FIRST_COMPLETED)

    await telegram_response_queue.put(command_message("exit"))

    for task in pending:
        task.cancel()
    for task in producers:
        task.cancel()
    await asyncio.gather(*pending, *producers, return_exceptions=True)


if __name__ == "__main__":
    preserve_thinking = True
    asyncio.run(main(preserve_thinking))


def run_main():
    """Entry point for fagent command"""
    import argparse
    parser = argparse.ArgumentParser(description="FAgent - Async Agent")
    parser.add_argument(
        "--preserve-thinking",
        action="store_true",
        default=True,
        help="Preserve thinking in output"
    )
    args = parser.parse_args()
    asyncio.run(main(args.preserve_thinking))
