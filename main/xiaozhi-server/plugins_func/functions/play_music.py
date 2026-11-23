import json
import os
import re
import time
import random
import difflib
import traceback
from pathlib import Path
from core.providers.tts.dto.dto import TTSMessageDTO, SentenceType, ContentType
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__

MUSIC_CACHE = {}

play_music_function_desc = {
    "type": "function",
    "function": {
        "name": "play_music",
        "description": "当用户要求播放音乐、歌曲，或者要求切歌、下一首、上一首时调用。用户说'切歌''下一首''换一首''换首歌''不要这首'时 action 填 next；说'上一首''前一首''回到刚才那首'时 action 填 previous；只说播放音乐或指定歌名时 action 填 play。",
        "parameters": {
            "type": "object",
            "properties": {
                "song_name": {
                    "type": "string",
                    "description": "歌曲名称，如果用户没有指定具体歌名则为'random', 明确指定的时返回音乐的名字 示例: ```用户:播放两只老虎\n参数：两只老虎``` ```用户:播放音乐 \n参数：random ```",
                },
                "action": {
                    "type": "string",
                    "enum": ["play", "next", "previous"],
                    "description": "play=播放（默认），next=切歌/下一首，previous=上一首",
                }
            },
            "required": ["song_name"],
        },
    },
}


@register_function("play_music", play_music_function_desc, ToolType.SYSTEM_CTL)
async def play_music(
    conn: "ConnectionHandler", song_name: str = "random", action: str = "play"
):
    try:
        action = (action or "play").strip().lower()
        # 切歌 / 上一首：在当前播放队列里前后移动
        if action in ("next", "previous"):
            step = 1 if action == "next" else -1
            played = await play_relative_music(conn, step)
            if not played:
                return ActionResponse(
                    action=Action.RESPONSE,
                    result="没有可播放的音乐",
                    response="没有找到可以播放的音乐，请先把音乐文件放到 music 目录里",
                )
            tip = "下一首" if step > 0 else "上一首"
            return ActionResponse(
                action=Action.RECORD, result="指令已接收", response=f"好的，为您{tip}"
            )

        music_intent = (
            f"播放音乐 {song_name}" if song_name != "random" else "随机播放音乐"
        )
        await handle_music_command(conn, music_intent)
        return ActionResponse(
            action=Action.RECORD, result="指令已接收", response="正在为您播放音乐"
        )
    except Exception as e:
        conn.logger.bind(tag=TAG).error(f"处理音乐意图错误: {e}")
        return ActionResponse(
            action=Action.RESPONSE, result=str(e), response="播放音乐时出错了"
        )


def _extract_song_name(text):
    """从用户输入中提取歌名"""
    for keyword in ["播放音乐"]:
        if keyword in text:
            parts = text.split(keyword)
            if len(parts) > 1:
                return parts[1].strip()
    return None


def _find_best_match(potential_song, music_files):
    """查找最匹配的歌曲"""
    best_match = None
    highest_ratio = 0

    for music_file in music_files:
        song_name = os.path.splitext(music_file)[0]
        ratio = difflib.SequenceMatcher(None, potential_song, song_name).ratio()
        if ratio > highest_ratio and ratio > 0.4:
            highest_ratio = ratio
            best_match = music_file
    return best_match


def get_music_files(music_dir, music_ext):
    music_dir = Path(music_dir)
    music_files = []
    music_file_names = []
    for file in music_dir.rglob("*"):
        # 判断是否是文件
        if file.is_file():
            # 获取文件扩展名
            ext = file.suffix.lower()
            # 判断扩展名是否在列表中
            if ext in music_ext:
                # 添加相对路径
                music_files.append(str(file.relative_to(music_dir)))
                music_file_names.append(
                    os.path.splitext(str(file.relative_to(music_dir)))[0]
                )
    return music_files, music_file_names



# 同音/口语纠错：把 ASR 容易听错的词归一成音乐控制词（仅在意图识别前生效）
MUSIC_COMMAND_ALIASES = {
    "切割": "切歌",
    "切个歌": "切歌",
    "切个": "切歌",
    "切哥": "切歌",
    "切歌儿": "切歌",
    "下一曲": "下一首",
    "下一首歌": "下一首",
    "下首": "下一首",
    "换首歌": "切歌",
    "前一首": "上一首",
    "上一个": "上一首",
}


def normalize_music_text(text):
    """把常见的音乐指令同音误识别归一，未命中则原样返回。"""
    if not text:
        return text
    # 长词优先，避免"切个歌"先被"切个"替换成"切歌歌"
    for wrong, right in sorted(
        MUSIC_COMMAND_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True
    ):
        if wrong in text:
            text = text.replace(wrong, right)
    return text


def _get_music_state(conn: "ConnectionHandler"):
    """每个连接独立的播放状态，记录当前歌与歌单。"""
    state = getattr(conn, "music_state", None)
    if not isinstance(state, dict):
        state = {"playlist": [], "index": -1, "current": None}
        conn.music_state = state
    return state


async def _stop_current_music(conn: "ConnectionHandler"):
    """停止设备端当前播放的音频，并清空待推送队列。"""
    try:
        conn.client_abort = True
        conn.clear_queues()
        await conn.websocket.send(
            json.dumps(
                {
                    "type": "tts",
                    "state": "stop",
                    "session_id": getattr(conn, "session_id", conn.sentence_id),
                }
            )
        )
        conn.clearSpeakStatus()
    except Exception as e:
        conn.logger.bind(tag=TAG).warning(f"停止当前音乐失败: {e}")
    finally:
        # 允许继续推送下一首
        conn.client_abort = False


def _enqueue_music_file(conn: "ConnectionHandler", selected_music, music_path):
    """把一首歌的引导语 + 音频文件推入 TTS 队列，并更新播放状态。"""
    state = _get_music_state(conn)
    state["current"] = selected_music
    try:
        state["index"] = state["playlist"].index(selected_music)
    except ValueError:
        pass

    text = _get_random_play_prompt(selected_music)
    conn.tts.store_tts_text(conn.sentence_id, text)

    if conn.intent_type == "intent_llm":
        conn.tts.tts_text_queue.put(
            TTSMessageDTO(
                sentence_id=conn.sentence_id,
                sentence_type=SentenceType.FIRST,
                content_type=ContentType.ACTION,
            )
        )
    conn.tts.tts_text_queue.put(
        TTSMessageDTO(
            sentence_id=conn.sentence_id,
            sentence_type=SentenceType.MIDDLE,
            content_type=ContentType.TEXT,
            content_detail=text,
        )
    )
    conn.tts.tts_text_queue.put(
        TTSMessageDTO(
            sentence_id=conn.sentence_id,
            sentence_type=SentenceType.MIDDLE,
            content_type=ContentType.FILE,
            content_file=music_path,
        )
    )
    if conn.intent_type == "intent_llm":
        conn.tts.tts_text_queue.put(
            TTSMessageDTO(
                sentence_id=conn.sentence_id,
                sentence_type=SentenceType.LAST,
                content_type=ContentType.ACTION,
            )
        )


async def play_relative_music(conn: "ConnectionHandler", step: int):
    """在当前歌单里前进/后退 step 首（首尾循环），成功返回 True。"""
    initialize_music_handler(conn)
    global MUSIC_CACHE

    files = MUSIC_CACHE.get("music_files") or []
    if not files:
        conn.logger.bind(tag=TAG).error("未找到MP3音乐文件")
        return False

    state = _get_music_state(conn)
    if list(state.get("playlist") or []) != files:
        state["playlist"] = list(files)

    playlist = state["playlist"]
    current = state.get("current")
    index = playlist.index(current) if current in playlist else -1
    if index < 0 and step < 0:
        index = 0  # 没有在播时，"上一首"从歌单开头算起
    new_index = (index + step) % len(playlist)
    selected_music = playlist[new_index]
    music_path = os.path.join(MUSIC_CACHE["music_dir"], selected_music)
    if not os.path.exists(music_path):
        conn.logger.bind(tag=TAG).error(f"选定的音乐文件不存在: {music_path}")
        return False

    await _stop_current_music(conn)
    _enqueue_music_file(conn, selected_music, music_path)
    conn.logger.bind(tag=TAG).info(f"切歌到: {selected_music}")
    return True


def initialize_music_handler(conn: "ConnectionHandler"):
    global MUSIC_CACHE
    if MUSIC_CACHE == {}:
        plugins_config = conn.config.get("plugins", {})
        if "play_music" in plugins_config:
            MUSIC_CACHE["music_config"] = plugins_config["play_music"]
            MUSIC_CACHE["music_dir"] = os.path.abspath(
                MUSIC_CACHE["music_config"].get("music_dir", "./music")  # 默认路径修改
            )
            MUSIC_CACHE["music_ext"] = MUSIC_CACHE["music_config"].get(
                "music_ext", (".mp3", ".wav", ".p3")
            )
            MUSIC_CACHE["refresh_time"] = MUSIC_CACHE["music_config"].get(
                "refresh_time", 60
            )
        else:
            MUSIC_CACHE["music_dir"] = os.path.abspath("./music")
            MUSIC_CACHE["music_ext"] = (".mp3", ".wav", ".p3")
            MUSIC_CACHE["refresh_time"] = 60
        # 获取音乐文件列表
        MUSIC_CACHE["music_files"], MUSIC_CACHE["music_file_names"] = get_music_files(
            MUSIC_CACHE["music_dir"], MUSIC_CACHE["music_ext"]
        )
        MUSIC_CACHE["scan_time"] = time.time()
    return MUSIC_CACHE


async def handle_music_command(conn: "ConnectionHandler", text):
    initialize_music_handler(conn)
    global MUSIC_CACHE

    """处理音乐播放指令"""
    clean_text = re.sub(r"[^\w\s]", "", text).strip()
    conn.logger.bind(tag=TAG).debug(f"检查是否是音乐命令: {clean_text}")

    # 尝试匹配具体歌名
    if os.path.exists(MUSIC_CACHE["music_dir"]):
        if time.time() - MUSIC_CACHE["scan_time"] > MUSIC_CACHE["refresh_time"]:
            # 刷新音乐文件列表
            MUSIC_CACHE["music_files"], MUSIC_CACHE["music_file_names"] = (
                get_music_files(MUSIC_CACHE["music_dir"], MUSIC_CACHE["music_ext"])
            )
            MUSIC_CACHE["scan_time"] = time.time()

        potential_song = _extract_song_name(clean_text)
        if potential_song:
            best_match = _find_best_match(potential_song, MUSIC_CACHE["music_files"])
            if best_match:
                conn.logger.bind(tag=TAG).info(f"找到最匹配的歌曲: {best_match}")
                await play_local_music(conn, specific_file=best_match)
                return True
    # 检查是否是通用播放音乐命令
    await play_local_music(conn)
    return True


def _get_random_play_prompt(song_name):
    """生成随机播放引导语"""
    # 移除文件扩展名
    clean_name = os.path.splitext(song_name)[0]
    prompts = [
        f"正在为您播放，《{clean_name}》",
        f"请欣赏歌曲，《{clean_name}》",
        f"即将为您播放，《{clean_name}》",
        f"现在为您带来，《{clean_name}》",
        f"让我们一起聆听，《{clean_name}》",
        f"接下来请欣赏，《{clean_name}》",
        f"此刻为您献上，《{clean_name}》",
    ]
    # 直接使用random.choice，不设置seed
    return random.choice(prompts)


async def play_local_music(conn: "ConnectionHandler", specific_file=None):
    global MUSIC_CACHE
    """播放本地音乐文件"""
    try:
        if not os.path.exists(MUSIC_CACHE["music_dir"]):
            conn.logger.bind(tag=TAG).error(
                f"音乐目录不存在: " + MUSIC_CACHE["music_dir"]
            )
            return

        # 确保路径正确性
        if specific_file:
            selected_music = specific_file
            music_path = os.path.join(MUSIC_CACHE["music_dir"], specific_file)
        else:
            if not MUSIC_CACHE["music_files"]:
                conn.logger.bind(tag=TAG).error("未找到MP3音乐文件")
                return
            selected_music = random.choice(MUSIC_CACHE["music_files"])
            music_path = os.path.join(MUSIC_CACHE["music_dir"], selected_music)

        if not os.path.exists(music_path):
            conn.logger.bind(tag=TAG).error(f"选定的音乐文件不存在: {music_path}")
            return
        # 记录歌单（随机播放时也保证"下一首"能在同一份歌单里移动）
        state = _get_music_state(conn)
        if list(state.get("playlist") or []) != list(MUSIC_CACHE["music_files"]):
            state["playlist"] = list(MUSIC_CACHE["music_files"])
        _enqueue_music_file(conn, selected_music, music_path)

    except Exception as e:
        conn.logger.bind(tag=TAG).error(f"播放音乐失败: {str(e)}")
        conn.logger.bind(tag=TAG).error(f"详细错误: {traceback.format_exc()}")
