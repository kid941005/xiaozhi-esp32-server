"""飞牛音乐网关（fnmusic-gateway）接入插件

把网关的 REST 播放能力桥接到设备端 self.music.play_url / self.music.stop 工具上，
让语音助手可以播放飞牛音乐库、歌单、歌手/专辑，并支持随机播放与单曲/列表循环。

网关接口：GET /api/play?query=&playlist=&artist=&album=&favorites=
                &shuffle=1&index=&quality=&scope=library&repeat=off|one|all
返回 JSON：{url, title, artist, lyric_url, duration, device_args, ...}
"""

from typing import TYPE_CHECKING, Any, Dict, Optional

import httpx

from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

MODULE_NAME = "fnmusic_gateway"
DEFAULT_TIMEOUT = 10.0
DEFAULT_CONNECT_TIMEOUT = 3.0
DEFAULT_DEVICE_TOOL = "self.music.play_url"
DEFAULT_STOP_TOOL = "self.music.stop"
MAX_URL_LENGTH = 2048

MSG_NOT_CONFIGURED = (
    "飞牛音乐网关还没有配置，请管理员在 config.yaml 的 "
    "plugins.fnmusic_gateway 里填写 base_url 后再试。"
)
MSG_DEVICE_UNAVAILABLE = "设备的音乐播放能力暂时不可用，请稍后再试。"
MSG_GATEWAY_FAILED = "连接飞牛音乐网关失败，请稍后再试。"
MSG_NOTHING_PLAYING = "当前没有正在播放的飞牛歌单，无法切换歌曲。"

_REPEAT_ALIASES = {
    "单曲循环": "one",
    "单曲重复": "one",
    "这首歌循环": "one",
    "循环播放这首": "one",
    "列表循环": "all",
    "列表重复": "all",
    "全部循环": "all",
    "歌单循环": "all",
    "顺序播放": "off",
    "不循环": "off",
    "取消循环": "off",
    "关闭循环": "off",
}

_LIBRARY_WORDS = ("library", "音乐库", "曲库", "全部音乐", "所有音乐", "整个音乐库")


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
def _plugin_config(conn: "ConnectionHandler") -> Dict[str, Any]:
    plugins = (getattr(conn, "config", None) or {}).get("plugins") or {}
    return plugins.get(MODULE_NAME) or {}


def _base_url(conn: "ConnectionHandler") -> str:
    return str(_plugin_config(conn).get("base_url") or "").strip().rstrip("/")


def _is_enabled(conn: "ConnectionHandler") -> bool:
    cfg = _plugin_config(conn)
    return bool(_base_url(conn)) and bool(cfg.get("enabled", True))


def _device_tool(conn: "ConnectionHandler") -> str:
    return str(_plugin_config(conn).get("device_tool") or DEFAULT_DEVICE_TOOL)


def _stop_tool(conn: "ConnectionHandler") -> str:
    return str(_plugin_config(conn).get("stop_tool") or DEFAULT_STOP_TOOL)


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
# 参数归一化
# --------------------------------------------------------------------------- #
def normalize_repeat(value: Any) -> str:
    """把 'one'/'all'/'off' 或中文口令归一化成网关支持的取值。"""
    text = str(value or "").strip()
    if not text:
        return "off"
    lowered = text.lower()
    if lowered in ("one", "all", "off"):
        return lowered
    if "单曲" in text or "这首" in text:
        return "one"
    if "列表" in text or "全部" in text or "歌单" in text:
        return "all"
    return _REPEAT_ALIASES.get(text, "off")


def normalize_scope(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered in ("library", "all"):
        return "library"
    for word in _LIBRARY_WORDS:
        if word.lower() == lowered or word in text:
            return "library"
    return ""


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on", "随机", "随机播放")


# --------------------------------------------------------------------------- #
# 网关请求
# --------------------------------------------------------------------------- #
async def _fetch_play(conn: "ConnectionHandler", params: Dict[str, Any]) -> Dict[str, Any]:
    """请求网关 /api/play 并返回播放信息；网络异常向上抛 httpx.HTTPError。"""
    base_url = _base_url(conn)
    timeout = _float(_plugin_config(conn).get("timeout"), DEFAULT_TIMEOUT)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=DEFAULT_CONNECT_TIMEOUT)
    ) as client:
        resp = await client.get(f"{base_url}/api/play", params=params)
    if resp.status_code != 200:
        raise httpx.HTTPStatusError(
            f"gateway returned {resp.status_code}",
            request=resp.request,
            response=resp,
        )
    data = resp.json()
    if isinstance(data, dict) and not data.get("url") and isinstance(data.get("data"), dict):
        return data["data"]
    return data if isinstance(data, dict) else {}


def build_play_params(
    query: str = "",
    playlist: str = "",
    artist: str = "",
    album: str = "",
    favorites: Any = None,
    scope: str = "",
    repeat: str = "off",
    shuffle: Any = None,
    index: Any = None,
    quality: str = "",
) -> Dict[str, Any]:
    """按网关契约组装 /api/play 的查询参数，空值不传。"""
    params: Dict[str, Any] = {}
    if query:
        params["query"] = str(query).strip()
    if playlist:
        params["playlist"] = str(playlist).strip()
    if artist:
        params["artist"] = str(artist).strip()
    if album:
        params["album"] = str(album).strip()
    if _truthy(favorites):
        params["favorites"] = "1"
    if normalize_scope(scope):
        params["scope"] = "library"
    if shuffle is not None and _truthy(shuffle):
        params["shuffle"] = "1"
    if index is not None and str(index).strip() != "":
        params["index"] = int(index)
    if quality:
        params["quality"] = str(quality).strip()
    params["repeat"] = normalize_repeat(repeat)
    return params


def _absolute_url(conn: "ConnectionHandler", url: str) -> str:
    url = str(url or "").strip()
    if url.startswith("/"):
        return f"{_base_url(conn)}{url}"
    return url


# --------------------------------------------------------------------------- #
# 设备调用
# --------------------------------------------------------------------------- #
async def _call_device(conn: "ConnectionHandler", tool_name: str, args: Dict[str, Any]) -> Any:
    """调用设备 MCP 工具；单独抽出便于单元测试替换。"""
    from core.providers.tools.device_mcp import call_mcp_tool

    mcp_client = getattr(conn, "mcp_client", None)
    if mcp_client is None:
        raise RuntimeError("设备 MCP 客户端未就绪")
    return await call_mcp_tool(conn, mcp_client, tool_name, args)


def _device_args(conn: "ConnectionHandler", info: Dict[str, Any]) -> Dict[str, Any]:
    args: Dict[str, Any] = {"url": _absolute_url(conn, info.get("url"))}
    if info.get("title"):
        args["title"] = str(info["title"])
    if info.get("artist"):
        args["artist"] = str(info["artist"])
    if info.get("lyric_url"):
        args["lyric_url"] = _absolute_url(conn, info["lyric_url"])
    duration = info.get("duration")
    if duration not in (None, ""):
        try:
            args["duration"] = int(float(duration))
        except (TypeError, ValueError):
            pass
    extra = info.get("device_args")
    if isinstance(extra, dict):
        args.update(extra)
    return args


async def play_on_device(conn: "ConnectionHandler", info: Dict[str, Any]) -> Optional[ActionResponse]:
    """把网关返回的播放信息交给设备播放；成功返回 None，失败返回提示响应。"""
    args = _device_args(conn, info)
    url = str(args.get("url") or "")
    if not url:
        return ActionResponse(action=Action.RESPONSE, response="音乐网关没有返回可播放的地址。")
    if len(url) > MAX_URL_LENGTH:
        logger.bind(tag=TAG).warning(f"播放地址过长（{len(url)}），已拒绝下发")
        return ActionResponse(action=Action.RESPONSE, response="播放地址过长，无法推送到设备。")
    try:
        await _call_device(conn, _device_tool(conn), args)
    except (RuntimeError, ValueError) as exc:
        logger.bind(tag=TAG).warning(f"设备播放失败: {exc}")
        return ActionResponse(action=Action.RESPONSE, response=MSG_DEVICE_UNAVAILABLE)
    except Exception as exc:  # 设备侧异常不影响会话
        logger.bind(tag=TAG).error(f"设备播放异常: {exc}")
        return ActionResponse(action=Action.RESPONSE, response=MSG_DEVICE_UNAVAILABLE)
    return None


# --------------------------------------------------------------------------- #
# 播放状态（供下一首/上一首使用）
# --------------------------------------------------------------------------- #
def _get_state(conn: "ConnectionHandler") -> Dict[str, Any]:
    state = getattr(conn, "fnmusic_state", None)
    if not isinstance(state, dict):
        state = {}
        setattr(conn, "fnmusic_state", state)
    return state


def _remember_state(conn: "ConnectionHandler", params: Dict[str, Any], info: Dict[str, Any]) -> None:
    state = _get_state(conn)
    state.clear()
    state.update(
        {
            "playlist": params.get("playlist", ""),
            "scope": params.get("scope", ""),
            "quality": params.get("quality", ""),
            "repeat": params.get("repeat", "off"),
            "index": int(params.get("index") or 1),
            "count": int(info.get("count") or 0),
        }
    )


def _step_play_params(state: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
    if state.get("scope") == "library":
        params: Dict[str, Any] = {"scope": "library", "index": index}
    elif state.get("playlist"):
        params = {"playlist": state["playlist"], "index": index}
    else:
        return None
    if state.get("quality"):
        params["quality"] = state["quality"]
    params["repeat"] = state.get("repeat") or "off"
    return params


async def _advance(conn: "ConnectionHandler", step: int) -> ActionResponse:
    state = _get_state(conn)
    if not state or (not state.get("playlist") and state.get("scope") != "library"):
        return ActionResponse(action=Action.RESPONSE, response=MSG_NOTHING_PLAYING)
    current = int(state.get("index") or 1)
    count = int(state.get("count") or 0)
    target = current + step
    if target < 1:
        if state.get("repeat") == "all" and count:
            target = count
        else:
            return ActionResponse(action=Action.RESPONSE, response="已经是第一首了。")
    if count and target > count:
        if state.get("repeat") == "all":
            target = 1
        else:
            return ActionResponse(action=Action.RESPONSE, response="已经是最后一首了。")
    params = _step_play_params(state, target)
    if not params:
        return ActionResponse(action=Action.RESPONSE, response=MSG_NOTHING_PLAYING)
    try:
        info = await _fetch_play(conn, params)
    except httpx.HTTPError as exc:
        logger.bind(tag=TAG).error(f"切换歌曲失败: {exc}")
        return ActionResponse(action=Action.RESPONSE, response=MSG_GATEWAY_FAILED)
    if not info.get("url"):
        return ActionResponse(action=Action.RESPONSE, response=info.get("message") or "没有找到要播放的音乐。")
    failure = await play_on_device(conn, info)
    if failure is not None:
        return failure
    state["index"] = target
    if info.get("count"):
        state["count"] = int(info["count"])
    tip = "下一首" if step > 0 else "上一首"
    title = info.get("title") or "音乐"
    return ActionResponse(action=Action.RECORD, result="指令已接收", response=f"好的，为您切到{tip}：{title}")


# --------------------------------------------------------------------------- #
# 注册工具
# --------------------------------------------------------------------------- #
fnmusic_play_desc = {
    "type": "function",
    "function": {
        "name": "fnmusic_play",
        "description": (
            "播放飞牛音乐库（NAS 音源）里的音乐。支持按歌名/歌手/专辑搜索，"
            "按歌单播放，随机播放整个音乐库，以及单曲循环或列表循环。"
            "本地 music 目录的播放请使用 play_music 工具。"
            "用户说“切歌”“切割”“下一首”“换一首”时不要调用本工具，改调用 fnmusic_next；说“上一首”“前一首”时调用 fnmusic_previous。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "歌曲名或关键词，例如：周杰伦 稻香"},
                "playlist": {"type": "string", "description": "歌单名称，用户指定歌单时填写"},
                "artist": {"type": "string", "description": "歌手名称"},
                "album": {"type": "string", "description": "专辑名称"},
                "favorites": {"type": "boolean", "description": "是否播放收藏的歌曲"},
                "scope": {
                    "type": "string",
                    "description": "播放范围，填 library 表示在整个音乐库随机播放",
                },
                "shuffle": {"type": "boolean", "description": "是否随机播放"},
                "repeat": {
                    "type": "string",
                    "enum": ["off", "one", "all"],
                    "description": "循环方式：off 不循环，one 单曲循环，all 列表循环",
                },
                "index": {"type": "integer", "description": "从歌单第几首开始播放，默认 1"},
            },
            "required": [],
        },
    },
}

fnmusic_next_desc = {
    "type": "function",
    "function": {
        "name": "fnmusic_next",
        "description": "播放飞牛音乐库时切到下一首。用户说“切歌”“切割”“下一首”“换一首”“换首歌”“不要这首”时调用（仅在 fnmusic_play 播放歌单/音乐库后可用）",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

fnmusic_previous_desc = {
    "type": "function",
    "function": {
        "name": "fnmusic_previous",
        "description": "播放飞牛音乐库时切回上一首。用户说“上一首”“前一首”“回到刚才那首”时调用（仅在 fnmusic_play 播放歌单/音乐库后可用）",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

fnmusic_stop_desc = {
    "type": "function",
    "function": {
        "name": "fnmusic_stop",
        "description": "停止播放飞牛音乐库的音乐",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


@register_function("fnmusic_play", fnmusic_play_desc, ToolType.SYSTEM_CTL)
async def fnmusic_play(
    conn: "ConnectionHandler",
    query: str = "",
    playlist: str = "",
    artist: str = "",
    album: str = "",
    favorites: Any = None,
    scope: str = "",
    shuffle: Any = None,
    repeat: str = "off",
    index: Any = None,
):
    if not _is_enabled(conn):
        return ActionResponse(action=Action.RESPONSE, response=MSG_NOT_CONFIGURED)
    cfg = _plugin_config(conn)
    params = build_play_params(
        query=query,
        playlist=playlist,
        artist=artist,
        album=album,
        favorites=favorites,
        scope=scope,
        repeat=repeat,
        shuffle=shuffle,
        index=index,
        quality=str(cfg.get("quality") or ""),
    )
    if not any(key in params for key in ("query", "playlist", "artist", "album", "favorites", "scope")):
        # 没有任何检索条件时按整库随机播放
        params["scope"] = "library"
        params["shuffle"] = "1"
    try:
        info = await _fetch_play(conn, params)
    except httpx.HTTPError as exc:
        logger.bind(tag=TAG).error(f"请求音乐网关失败: {exc}")
        return ActionResponse(action=Action.RESPONSE, response=MSG_GATEWAY_FAILED)
    if not info.get("url"):
        return ActionResponse(
            action=Action.RESPONSE,
            response=info.get("message") or "飞牛音乐库里没有找到要播放的音乐。",
        )
    failure = await play_on_device(conn, info)
    if failure is not None:
        return failure
    _remember_state(conn, params, info)
    title = info.get("title") or "音乐"
    return ActionResponse(action=Action.RECORD, result="指令已接收", response=f"正在为您播放{title}")


@register_function("fnmusic_next", fnmusic_next_desc, ToolType.SYSTEM_CTL)
async def fnmusic_next(conn: "ConnectionHandler"):
    if not _is_enabled(conn):
        return ActionResponse(action=Action.RESPONSE, response=MSG_NOT_CONFIGURED)
    return await _advance(conn, 1)


@register_function("fnmusic_previous", fnmusic_previous_desc, ToolType.SYSTEM_CTL)
async def fnmusic_previous(conn: "ConnectionHandler"):
    if not _is_enabled(conn):
        return ActionResponse(action=Action.RESPONSE, response=MSG_NOT_CONFIGURED)
    return await _advance(conn, -1)


@register_function("fnmusic_stop", fnmusic_stop_desc, ToolType.SYSTEM_CTL)
async def fnmusic_stop(conn: "ConnectionHandler"):
    if not _is_enabled(conn):
        return ActionResponse(action=Action.RESPONSE, response=MSG_NOT_CONFIGURED)
    try:
        await _call_device(conn, _stop_tool(conn), {})
    except (RuntimeError, ValueError) as exc:
        logger.bind(tag=TAG).warning(f"停止播放失败: {exc}")
        return ActionResponse(action=Action.RESPONSE, response=MSG_DEVICE_UNAVAILABLE)
    except Exception as exc:
        logger.bind(tag=TAG).error(f"停止播放异常: {exc}")
        return ActionResponse(action=Action.RESPONSE, response=MSG_DEVICE_UNAVAILABLE)
    _get_state(conn).clear()
    return ActionResponse(action=Action.RECORD, result="指令已接收", response="好的，已停止播放")
