#!/usr/bin/env python3
"""
Telegram Bot Producer - 接收 Telegram 消息并发送到 main queue。

Behavior:
- 通过环境变量 TELEGRAM_BOT_TOKEN 配置 bot token
- 通过环境变量 TARGET_USERNAME 配置目标用户（可选）
- 收到消息后先发送中断信号打断当前 model step
- 支持图片、文件下载到 tg_media 目录
- 设置 typing 状态，turn 结束后自动取消
- 然后将消息放入 main_queue 作为 role:user
- 如果配置了 TARGET_USERNAME，只处理该用户的消息
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from queue_utils import telegram_message, print_message, MessageType

load_dotenv()

# Environment variables
ENV_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ENV_TARGET_USERNAME = os.getenv("TARGET_USERNAME")

# Where to persist username->chat_id mappings
DEFAULT_STORE_PATH = Path.home() / ".tgpipe_targets.json"

# Media download directory
MEDIA_DIR = Path("tg_media")

# Globals
app: Optional[Application] = None
_resolved_chat_id: Optional[int] = None
_typing_task: Optional[asyncio.Task] = None
_typing_turn_id: int = 0  # 用于同步 turn 的 ID
_telegram_batch_active: bool = False  # 标记是否正在收集一批消息中


def get_current_turn_id() -> int:
    """获取当前 turn ID，用于 bot_consumer 检查是否是新的 turn"""
    global _typing_turn_id
    return _typing_turn_id


def is_telegram_batch_active() -> bool:
    """检查是否正在收集一批 telegram 消息"""
    global _telegram_batch_active
    return _telegram_batch_active


def set_telegram_batch_active(active: bool):
    """设置 batch 活跃状态（由 consumer 在处理完成后调用）"""
    global _telegram_batch_active
    _telegram_batch_active = active


def get_bot():
    """Get the current bot instance."""
    global app
    return app.bot if app else None


def get_target_chat_id():
    """Get the resolved target chat_id."""
    global _resolved_chat_id
    return _resolved_chat_id


def _norm_username(u: Optional[str]) -> Optional[str]:
    """Normalize a username to lowercase without leading @; return None if empty."""
    if not u:
        return None
    u = u.lstrip("@").strip()
    return u.lower() or None


def load_saved_targets(path: Path = DEFAULT_STORE_PATH) -> dict:
    """Load saved username->chat_id mapping from JSON file."""
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    _norm_username(k): int(v)
                    for k, v in (data or {}).items()
                    if _norm_username(k) and v is not None
                }
    except Exception:
        pass
    return {}


def save_target(username: str, chat_id: int, path: Path = DEFAULT_STORE_PATH) -> None:
    """Save or update the mapping username->chat_id atomically."""
    username_norm = _norm_username(username)
    if not username_norm:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = load_saved_targets(path)
        data[username_norm] = int(chat_id)
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
    except Exception as e:
        print(f"[WARN] failed to save target: {e}")


async def _typing_loop(bot, chat_id: int, turn_id: int):
    """持续发送 typing 状态，直到被取消或 turn 改变"""
    global _typing_turn_id
    try:
        while _typing_turn_id == turn_id:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(4)  # Telegram typing 状态持续约 5 秒
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


def start_new_typing_turn(bot, chat_id: int):
    """开始一个新的 turn 的 typing"""
    global _typing_task, _typing_turn_id
    # 停止之前的 typing
    if _typing_task and not _typing_task.done():
        _typing_task.cancel()
    # 增加 turn ID
    _typing_turn_id += 1
    # 启动新的 typing 任务
    _typing_task = asyncio.create_task(_typing_loop(bot, chat_id, _typing_turn_id))
    return _typing_turn_id


def stop_typing():
    """停止 typing 状态"""
    global _typing_task
    if _typing_task and not _typing_task.done():
        _typing_task.cancel()
        _typing_task = None


async def download_file(bot, file_id: str, filename: str) -> Optional[str]:
    """下载文件到 tg_media 目录，返回保存路径"""
    try:
        file = await bot.get_file(file_id)
        # 创建目录
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名：timestamp_originalname
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{filename}"
        filepath = MEDIA_DIR / safe_filename
        
        # 下载文件
        await file.download_to_drive(filepath)
        return str(filepath)
    except Exception as e:
        print(f"[Telegram] Failed to download file: {e}")
        return None


async def handle_incoming(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    main_queue: asyncio.Queue,
    user_interrupt_queue: asyncio.Queue,
    print_queue: asyncio.Queue,
    target_username: Optional[str],
    set_chat_id_func,
):
    """
    Handler for incoming messages.
    If message matches target (if configured), interrupt current model step
    and send message to main_queue.
    """
    global _typing_task
    
    if not update.message:
        return

    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None:
        return

    username_raw = user.username or user.first_name or ""
    username_norm = _norm_username(user.username) or _norm_username(username_raw)
    chat_id = chat.id

    # Check if target username is configured and matches
    if target_username:
        if username_norm != target_username:
            # Ignore messages from other users
            return

    # Save target if new
    if username_norm:
        saved = load_saved_targets()
        if username_norm not in saved:
            save_target(username_norm, chat_id)
            await print_queue.put(
                print_message(f"[Telegram] Saved new target: @{username_raw} (chat_id={chat_id})")
            )
        # 更新全局 chat_id
        set_chat_id_func(chat_id)

    ts = datetime.now().strftime("%H:%M:%S")
    
    # 获取 bot 实例用于 typing 和下载
    bot = context.bot
    
    # 开始新的 turn（停止之前的 typing，启动新的）
    current_turn_id = start_new_typing_turn(bot, chat_id)
    
    # 处理不同类型的消息
    message_parts = []
    file_paths = []
    
    # 1. 处理文本/caption
    text = update.message.text or update.message.caption or ""
    
    # 2. 处理图片
    if update.message.photo:
        # 获取最大尺寸的图片
        photo = update.message.photo[-1]
        file_id = photo.file_id
        # 生成文件名
        ext = "jpg"  # Telegram 图片通常是 jpeg
        filename = f"photo_{photo.file_unique_id}.{ext}"
        
        await print_queue.put(
            print_message(f"[Telegram {ts}] Received photo from @{username_raw}, downloading...")
        )
        
        filepath = await download_file(bot, file_id, filename)
        if filepath:
            file_paths.append(filepath)
            await print_queue.put(
                print_message(f"[Telegram] Saved photo to: {filepath}")
            )
    
    # 3. 处理文档/文件
    elif update.message.document:
        doc = update.message.document
        file_id = doc.file_id
        filename = doc.file_name or f"file_{doc.file_unique_id}"
        
        await print_queue.put(
            print_message(f"[Telegram {ts}] Received file '{filename}' from @{username_raw}, downloading...")
        )
        
        filepath = await download_file(bot, file_id, filename)
        if filepath:
            file_paths.append(filepath)
            await print_queue.put(
                print_message(f"[Telegram] Saved file to: {filepath}")
            )
    
    # 4. 处理纯文本消息
    elif update.message.text:
        await print_queue.put(
            print_message(f"[Telegram {ts}] Received from @{username_raw}: {text}")
        )
    
    # 5. 处理不支持的消息类型
    else:
        unsupported_types = []
        if update.message.audio:
            unsupported_types.append("audio")
        if update.message.video:
            unsupported_types.append("video")
        if update.message.voice:
            unsupported_types.append("voice")
        if update.message.video_note:
            unsupported_types.append("video_note")
        if update.message.sticker:
            unsupported_types.append("sticker")
        if update.message.location:
            unsupported_types.append("location")
        if update.message.contact:
            unsupported_types.append("contact")
        if update.message.poll:
            unsupported_types.append("poll")
        
        if unsupported_types:
            type_str = ", ".join(unsupported_types)
            await print_queue.put(
                print_message(f"[Telegram {ts}] Received unsupported message type ({type_str}) from @{username_raw}")
            )
            # 发送提示给用户
            await update.message.reply_text(
                f"⚠️ 不支持的消息类型: {type_str}\n"
                f"目前支持: 文本、图片、文件"
            )
            # 通知 agent 收到了未知类型消息
            tagged_text = f"[From Telegram {ts}] [System: User sent unsupported message type: {type_str}]"
            
            # 发送中断信号
            if user_interrupt_queue.empty():
                await user_interrupt_queue.put("telegram_interrupt")
            
            # 放入 main_queue
            await main_queue.put(telegram_message(tagged_text))
            
            # 停止 typing
            stop_typing()
            return
    
    # 构建消息内容
    if text:
        message_parts.append(text)
    
    for fp in file_paths:
        message_parts.append(f"[File: {fp}]")
    
    if not message_parts:
        stop_typing()
        return
    
    final_text = "\n".join(message_parts)

        # 1. 检查是否正在收集一批消息中
    # 使用全局标志来跟踪状态（因为消息可能已被 consumer 取出但仍在处理中）
    global _telegram_batch_active
    
    if not _telegram_batch_active:
        # 第一条消息，设置标志并发送中断信号
        _telegram_batch_active = True
        if user_interrupt_queue.empty():
            await user_interrupt_queue.put("telegram_interrupt")
        await print_queue.put(
            print_message(f"[Telegram] Sent interrupt signal to stop current model step")
        )
    else:
        # 正在收集后续消息，不发送中断信号
        await print_queue.put(
            print_message(f"[Telegram] Batch active, skipping interrupt signal")
        )

    # 2. 将消息放入 main_queue（带上时间戳标记）
    tagged_text = f"[From Telegram {ts}] {final_text}"
    await main_queue.put(telegram_message(tagged_text))


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply to /start to confirm bot reachability."""
    chat = update.effective_chat
    user = update.effective_user
    if chat and update.message:
        uname = user.username if user else "unknown"
        await update.message.reply_text(
            f"Bot connected. Your username: @{uname}, chat_id: {chat.id}\n"
            f"支持的消息类型: 文本、图片、文件"
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log handler errors."""
    print(f"[Telegram ERROR] {context.error}")


async def telegram_bot_producer(
    main_queue: asyncio.Queue,
    print_queue: asyncio.Queue,
    user_interrupt_queue: asyncio.Queue,
):
    """
    Telegram Bot Producer - 监听 Telegram 消息，收到后打断当前 model step
    并将消息发送到 main_queue。
    """
    token = ENV_TOKEN
    if not token:
        await print_queue.put(
            print_message("[Telegram] TELEGRAM_BOT_TOKEN not set, bot producer will not start")
        )
        return

    target_username = _norm_username(ENV_TARGET_USERNAME)

    if target_username:
        await print_queue.put(
            print_message(f"[Telegram] Target username configured: @{target_username}")
        )
        saved = load_saved_targets()
        if target_username in saved:
            await print_queue.put(
                print_message(f"[Telegram] Using saved chat_id for @{target_username}: {saved[target_username]}")
            )
    else:
        await print_queue.put(
            print_message("[Telegram] No TARGET_USERNAME configured, will accept messages from any user")
        )

    global app
    app = Application.builder().token(token).build()

    def set_chat_id(chat_id: int):
        global _resolved_chat_id
        _resolved_chat_id = chat_id
    
    # Create handler with access to queues
    async def handle_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await handle_incoming(
            update, context, main_queue, user_interrupt_queue, print_queue, target_username, set_chat_id
        )

    app.add_handler(CommandHandler("start", start_command))
    # 处理所有消息类型（文本、图片、文件等）
    app.add_handler(MessageHandler(filters.ALL, handle_wrapper))
    app.add_error_handler(error_handler)

    await print_queue.put(print_message("[Telegram] Bot starting..."))

    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

        # Keep running until cancelled
        while True:
            await asyncio.sleep(1)

    except asyncio.CancelledError:
        await print_queue.put(print_message("[Telegram] Bot producer cancelled"))
        raise
    finally:
        stop_typing()
        if app:
            try:
                await app.updater.stop()
            except Exception:
                pass
            try:
                await app.stop()
            except Exception:
                pass
            try:
                await app.shutdown()
            except Exception:
                pass
        await print_queue.put(print_message("[Telegram] Bot stopped"))


def stop_typing_for_turn():
    """在 turn 结束后调用，停止 typing 状态（供外部调用）"""
    stop_typing()
