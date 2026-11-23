import json
from config.logger import setup_logging
import requests
from core.providers.llm.base import LLMProviderBase
from core.utils.util import check_model_key

TAG = __name__
logger = setup_logging()


class LLMProvider(LLMProviderBase):
    def __init__(self, config):
        self.api_key = config["api_key"]
        self.base_url = config.get("base_url")
        self.detail = config.get("detail", False)
        self.variables = config.get("variables", {})
        model_key_msg = check_model_key("FastGPTLLM", self.api_key)
        if model_key_msg:
            logger.bind(tag=TAG).error(model_key_msg)

    def response(self, session_id, dialogue, **kwargs):
        # 取最后一条用户消息
        last_msg = next(m for m in reversed(dialogue) if m["role"] == "user")

        # 标记当前是否处于 <think> 推理段内（原来按 chunk 是否含标签直接丢弃，会连正文一起丢）
        in_think = False

        # 发起流式请求
        with requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "stream": True,
                "chatId": session_id,
                "detail": self.detail,
                "variables": self.variables,
                "messages": [{"role": "user", "content": last_msg["content"]}],
            },
            stream=True,
        ) as r:
            for line in r.iter_lines():
                if line:
                    try:
                        if line.startswith(b"data: "):
                            if line[6:].decode("utf-8") == "[DONE]":
                                break

                            data = json.loads(line[6:])
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                if (
                                    delta
                                    and "content" in delta
                                    and delta["content"] is not None
                                ):
                                    content = delta["content"]
                                    # 只剥离 <think> 推理段标签，不要把整块正文一起丢掉
                                    if in_think:
                                        if "</think>" in content:
                                            content = content.split("</think>", 1)[1]
                                            in_think = False
                                        else:
                                            continue
                                    if "<think>" in content:
                                        head, _, tail = content.partition("<think>")
                                        content = head
                                        if "</think>" in tail:
                                            content = tail.split("</think>", 1)[1]
                                        else:
                                            in_think = True
                                    if content:
                                        yield content

                    except json.JSONDecodeError as e:
                        continue
                    except Exception as e:
                        continue

    def response_with_functions(self, session_id, dialogue, functions=None):
        # 原来只打日志并返回 None，调用方按生成器迭代会抛 TypeError。
        # 这里降级为普通对话生成（忽略 functions），保证链路可用。
        logger.bind(tag=TAG).warning(
            "fastgpt暂未实现完整的工具调用（function call），已降级为普通对话生成"
        )
        yield from self.response(session_id, dialogue, functions=functions)
