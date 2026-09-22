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

    # ===== 持久化：memory（零依赖）或 postgres（Phase 3 交付）=====
    persistence_type: str = "memory"
    postgres_uri: str = ""

    # ===== 可观测性（Phase 2 填充，仅保留开关与连接占位）=====
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例（进程内缓存）。"""
    return Settings()
