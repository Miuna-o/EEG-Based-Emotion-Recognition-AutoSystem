"""可选助手 IO 边界。复用旧提示词和采样温度，只接收显式文字。"""
import os
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.models import AppError


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=4000)
    messages: list[ChatMessage] = Field(default_factory=list, max_length=60)


def status(settings):
    result = {'enabled': settings.assistant_enabled, 'available': False, 'model': settings.assistant_model,
              'timeout_seconds': settings.assistant_timeout_seconds, 'max_history': settings.assistant_max_history,
              'reason': '助手未启用；可在 config/xinlan.json 启用并启动本机 Ollama。核心工作台不依赖助手。'}
    if not settings.assistant_enabled:
        return result
    try:
        response = httpx.get(settings.assistant_base_url + '/models', timeout=min(2, settings.assistant_timeout_seconds), trust_env=False)
        response.raise_for_status()
        names = [item.get('id') for item in response.json().get('data', [])]
        result['available'] = settings.assistant_model in names
        result['reason'] = '本机模型服务可用' if result['available'] else '本机服务已启动，但没有配置的模型；请核对模型名称。'
    except (httpx.HTTPError, ValueError, KeyError):
        result['reason'] = '未连接到本机助手；请启动 Ollama，核对配置地址后刷新。'
    return result


def chat(settings, request: ChatRequest):
    if not settings.assistant_enabled:
        raise AppError('assistant_unavailable', '助手未启用；导入、任务与报告仍可使用', 503)
    try:
        from openai import OpenAI
        from core.ai_core.llm_client import SimpleAIChat
        legacy = SimpleAIChat()
        system_prompt = legacy.system_prompt
        legacy.client.close()
        # 每次请求均为独立快照，不持久化会话；清空页面后的迟到响应无法改写后台历史。
        history = request.messages[-settings.assistant_max_history * 2:] if settings.assistant_max_history else []
        messages = [system_prompt] + [item.model_dump() for item in history] + [{'role': 'user', 'content': request.text}]
        with OpenAI(base_url=settings.assistant_base_url, api_key=os.environ.get('XINLAN_ASSISTANT_API_KEY', 'ollama'),
                    timeout=settings.assistant_timeout_seconds, max_retries=settings.assistant_retry_limit,
                    http_client=httpx.Client(trust_env=False)) as client:
            response = client.chat.completions.create(model=settings.assistant_model, messages=messages, temperature=0.7)
            reply = response.choices[0].message.content
            if not reply:
                raise ValueError('empty_reply')
            return {'reply': reply, 'model': settings.assistant_model}
    except Exception as exc:
        raise AppError('assistant_unavailable', '助手未返回有效回复；请检查本机服务和模型。您的数据不会自动发送。', 503) from exc
