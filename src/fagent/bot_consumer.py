#!/usr/bin/env python3
"""
Telegram Bot Consumer - 将模型响应发送回 Telegram 用户。

Behavior:
- 监听 telegram_response_queue
- 将 tool call 执行信息和最终回复发送给 Telegram 用户
- 使用 bot_producer 中初始化的 bot 实例发送消息
"""

import asyncio
from typing import Optional

from .queue_utils import MessageType, print_message
from .bot_producer import stop_typing_for_turn, get_current_turn_id


def escape_markdown(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    # 需要转义的字符: _ * [ ] ( ) ~ ` > # + - = | { } . !
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text


async def send_telegram_message(bot, chat_id: int, text: str, use_markdown: bool = True) -> bool:
    """Send a text message to Telegram chat, splitting if too long."""
    if not bot or not chat_id:
        return False
    
    # Telegram 消息长度限制为 4096 字符
    MAX_LENGTH = 4000
    
    try:
        # 如果消息太长，分段发送
        if len(text) > MAX_LENGTH:
            chunks = []
            for i in range(0, len(text), MAX_LENGTH):
                chunk = text[i:i + MAX_LENGTH]
                chunks.append(chunk)
            
            for i, chunk in enumerate(chunks):
                prefix = f"[Part {i+1}/{len(chunks)}]\n" if len(chunks) > 1 else ""
                await bot.send_message(
                    chat_id=chat_id,
                    text=prefix + chunk,
                    parse_mode="MarkdownV2" if use_markdown else None
                )
                await asyncio.sleep(0.1)  # 避免发送太快
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="MarkdownV2" if use_markdown else None
            )
        return True
    except Exception as e:
        # Markdown 解析失败时，尝试用纯文本发送
        if use_markdown:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=None
                )
                return True
            except Exception as e2:
                print(f"[Telegram Consumer ERROR] Failed to send message: {e2}")
                return False
        else:
            print(f"[Telegram Consumer ERROR] Failed to send message: {e}")
            return False


async def telegram_bot_consumer(
    telegram_response_queue: asyncio.Queue,
    print_queue: asyncio.Queue,
    get_bot_func,  # 函数，返回 bot 实例
    get_chat_id_func,  # 函数，返回当前目标 chat_id
):
    """
    Telegram Bot Consumer - 监听 telegram_response_queue，
    将模型响应发送给 Telegram 用户。
    """
    await print_queue.put(print_message("[Telegram Consumer] Started"))
    
    running = True
    last_turn_id = 0  # 上一次处理的 turn ID
    
    while running:
        try:
            msg = await telegram_response_queue.get()
            
            # 检查是否是新的 turn
            current_turn_id = get_current_turn_id()
            is_new_turn = current_turn_id != last_turn_id
            if is_new_turn:
                last_turn_id = current_turn_id
            
            if msg.type == MessageType.TELEGRAM_RESPONSE:
                data = msg.data
                response_type = data.get("type", "text")
                content = data.get("content", "")
                
                if not content:
                    continue
                
                # 新 turn 的第一个响应发送前，停止 typing 状态
                if is_new_turn:
                    stop_typing_for_turn()
                
                # 获取 bot 和 chat_id
                bot = get_bot_func()
                chat_id = get_chat_id_func()
                
                if not bot or not chat_id:
                    await print_queue.put(
                        print_message(f"[Telegram Consumer] Skip sending: bot={bool(bot)}, chat_id={chat_id}")
                    )
                    continue
                
                # 根据类型格式化消息（使用 MarkdownV2）
                if response_type == "tool_start":
                    formatted = f"🛠️ *Executing Tool*\n```\n{escape_markdown(content)}\n```"
                    await send_telegram_message(bot, chat_id, formatted)
                    
                elif response_type == "tool_result":
                    truncated = content[:3000] + ('...' if len(content) > 3000 else '')
                    formatted = f"📊 *Tool Result*\n```\n{escape_markdown(truncated)}\n```"
                    await send_telegram_message(bot, chat_id, formatted)
                    
                elif response_type == "final":
                    formatted = f"{escape_markdown(content)}"
                    await send_telegram_message(bot, chat_id, formatted)
                    
                else:
                    # 普通文本
                    await send_telegram_message(bot, chat_id, escape_markdown(content))
                    
            elif msg.type == MessageType.COMMAND and msg.data == "exit":
                running = False
                
        except asyncio.CancelledError:
            await print_queue.put(print_message("[Telegram Consumer] Cancelled"))
            raise
        except Exception as e:
            await print_queue.put(
                print_message(f"[Telegram Consumer ERROR] {e}")
            )
    
    await print_queue.put(print_message("[Telegram Consumer] Stopped"))
