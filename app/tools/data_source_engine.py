from __future__ import annotations

import base64
from collections.abc import Callable
from urllib.parse import unquote

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from app.api.auth import AuthContext
from app.core.config import get_settings
from app.core.database import get_engine
from app.db.product_models import DataSource
from app.repositories.product import DataSourceRepository

PASSWORD_PLACEHOLDERS = {"", "******", "********", "••••••", "••••••••"}


def encode_demo_password(password: str) -> str:
    """把本地演示密码编码后再写入产品库。

    这里不是生产级加密，只是为了让 V3.13.6 先跑通“后端托管密钥”的产品链路。
    真正上线时应替换为 KMS、Vault 或数据库字段级加密。
    """

    encoded = base64.urlsafe_b64encode(password.encode("utf-8")).decode("ascii")
    return f"local-demo:{encoded}"


def decode_demo_password(secret: str | None) -> str | None:
    """读取本地演示密码。

    兼容早期初始化脚本里的占位值，遇到不可解码内容时返回 None。
    """

    if not secret or secret == "demo-encrypted-password-placeholder":
        return None
    if secret.startswith("local-demo:"):
        raw = secret.removeprefix("local-demo:")
        try:
            return base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8")
        except Exception:
            return None
    if secret.startswith("plain:"):
        return secret.removeprefix("plain:")
    return None


def is_password_placeholder(value: str | None) -> bool:
    """判断前端传来的密码是否只是“沿用旧密码”的占位符。"""

    return (value or "").strip() in PASSWORD_PLACEHOLDERS


def get_default_data_source_engine(
    *,
    session: Session,
    auth_context: AuthContext,
    fallback_engine_factory: Callable[[], Engine] = get_engine,
) -> Engine:
    """为当前工作空间默认数据源创建业务库 Engine。

    V1-V3.13.5 主要依赖 .env 的 DATABASE_URL。V3.13.6 开始，登录态下优先读取
    产品库中的默认数据源配置；如果是旧 demo 数据源且还没有保存真实密码，则平滑回退到
    DATABASE_URL，避免升级后本地演示库无法同步。
    """

    data_source = DataSourceRepository(session).get_default_for_workspace(auth_context.workspace)
    if data_source is None:
        raise ValueError("当前工作空间还没有默认数据源，请先在系统设置中保存数据源配置。")
    return build_engine_for_data_source(data_source, fallback_engine_factory=fallback_engine_factory)


def build_engine_for_data_source(
    data_source: DataSource,
    password: str | None = None,
    fallback_engine_factory: Callable[[], Engine] = get_engine,
) -> Engine:
    """根据数据源配置创建 SQLAlchemy Engine。

    第一阶段只正式支持 MySQL；其他数据库会在后续版本接入方言、连接测试和 schema 读取适配。
    """

    normalized_type = data_source.db_type.lower()
    if normalized_type == "sqlite":
        # 测试环境仍然通过 get_engine 注入内存业务库，这里保留兼容。
        return fallback_engine_factory()
    if normalized_type != "mysql":
        raise ValueError(f"当前版本暂只支持 MySQL 数据源，收到：{data_source.db_type}")

    resolved_password = password if password is not None else resolve_data_source_password(data_source)
    if resolved_password is None:
        if _matches_env_database_url(data_source):
            return fallback_engine_factory()
        raise ValueError("该数据源还没有保存可用密码，请在系统设置中填写密码后再测试连接。")

    url = URL.create(
        "mysql+pymysql",
        username=data_source.username,
        password=resolved_password,
        host=data_source.host,
        port=data_source.port,
        database=data_source.database_name,
        query={"charset": "utf8mb4"},
    )
    return create_engine(url, pool_pre_ping=True, future=True)


def resolve_data_source_password(data_source: DataSource) -> str | None:
    """解析数据源密码。

    先读产品库凭据；如果凭据还是旧占位值，则尝试从 DATABASE_URL 里拿本地 demo 密码。
    """

    password = decode_demo_password(data_source.credential.encrypted_password if data_source.credential else None)
    if password:
        return password
    if _matches_env_database_url(data_source):
        return _password_from_env_database_url()
    return None


def _matches_env_database_url(data_source: DataSource) -> bool:
    settings = get_settings()
    try:
        url = make_url(settings.database_url)
    except Exception:
        return False

    return (
        (url.get_backend_name() or "").lower().startswith(data_source.db_type.lower())
        and (url.host or "") == data_source.host
        and int(url.port or 0) == int(data_source.port)
        and (url.database or "") == data_source.database_name
        and (url.username or "") == data_source.username
    )


def _password_from_env_database_url() -> str | None:
    settings = get_settings()
    try:
        password = make_url(settings.database_url).password
    except Exception:
        return None
    return unquote(password) if password else None
