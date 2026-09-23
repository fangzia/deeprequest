"""全局配置。

使用 pydantic-settings 统一管理环境变量与 .env 文件，
所有 DeepQuest 专属变量均带 ``DEEPQUEST_`` 前缀（Tavily/Jina/Langfuse 等第三方 key 除外）。
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """DeepQuest 全局配置项。"""

    model_config = SettingsConfigDict(
        env_prefix="DEEPQUEST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ===== LLM（OpenAI 兼容接口，默认示例为 DeepSeek）=====
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_max_retries: int = 3

    # ===== 搜索工具（Tavily，https://tavily.com 免费注册）=====
    # .env 中无 DEEPQUEST_ 前缀，因此显式声明别名
    tavily_api_key: str = Field(default="", validation_alias="TAVILY_API_KEY")

    # ===== 网页抓取（Jina Reader，key 可选，无 key 时走匿名限流）=====
    jina_api_key: str = ""

    # ===== 持久化：memory（零依赖）或 postgres =====
    persistence_type: str = "memory"
    postgres_uri: str = ""

    # ===== MCP 工具（可选，MCP 多服务器配置文件路径，空则禁用）=====
    mcp_config: str = ""

    # ===== 可观测性（Langfuse，可选组件，自托管免费）=====
    # .env 中无 DEEPQUEST_ 前缀，因此显式声明别名
    langfuse_enabled: bool = False
    langfuse_public_key: str = Field(default="", validation_alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", validation_alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(
        default="http://localhost:3000", validation_alias="LANGFUSE_HOST"
    )


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例（进程内缓存）。"""
    return Settings()
