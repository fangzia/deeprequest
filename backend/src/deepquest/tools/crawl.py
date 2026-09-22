"""网页抓取工具：基于 Jina Reader（https://r.jina.ai/{url}）将网页转为 markdown。"""

import logging
from typing import Annotated

import httpx
from langchain_core.tools import tool

from deepquest.config.settings import get_settings

logger = logging.getLogger(__name__)

# 抓取内容最大保留长度，防止超长网页撑爆上下文
_MAX_CONTENT_CHARS = 30_000


@tool
async def crawl_tool(
    url: Annotated[str, "要抓取的网页 URL。"],
) -> str:
    """抓取指定 URL 的网页内容并转换为 markdown 格式。"""
    settings = get_settings()
    headers = {
        "X-Return-Format": "markdown",
    }
    if settings.jina_api_key:
        headers["Authorization"] = f"Bearer {settings.jina_api_key}"

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(f"https://r.jina.ai/{url}", headers=headers)
        if response.status_code != 200:
            error_msg = f"Jina Reader 返回状态码 {response.status_code}：{response.text[:200]}"
            logger.error("crawl_tool 抓取失败 url=%s: %s", url, error_msg)
            return f"Error: {error_msg}"

        content = response.text
        if not content.strip():
            logger.warning("crawl_tool 抓取到空内容 url=%s", url)
            return "Error: Jina Reader 返回空内容"

        if len(content) > _MAX_CONTENT_CHARS:
            content = content[:_MAX_CONTENT_CHARS] + "\n...(内容已截断)"
        return content
    except httpx.HTTPError as e:
        error_msg = f"请求 Jina Reader 失败：{e!r}"
        logger.error("crawl_tool 请求异常 url=%s: %s", url, error_msg)
        return f"Error: {error_msg}"
