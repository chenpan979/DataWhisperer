from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class ProductBase(DeclarativeBase):
    """产品管理库 ORM 基类。

    DataWhisperer 现在有两类数据库：
    - `datawhisperer_demo`：被 AI 查询分析的业务示例库；
    - `datawhisperer_product`：平台自身的产品管理库，保存租户、用户、数据源和会话。

    单独定义 ProductBase，可以避免把业务库表和产品库表混到同一个 metadata 里。
    """


@lru_cache
def get_product_engine() -> Engine:
    """创建并缓存产品管理库 Engine。

    这里连接的是 `PRODUCT_DATABASE_URL`，不要复用 `DATABASE_URL`。
    `DATABASE_URL` 仍然代表用户要分析的业务库。
    """

    settings = get_settings()
    return create_engine(settings.product_database_url, pool_pre_ping=True, future=True)


@lru_cache
def get_product_session_factory() -> sessionmaker[Session]:
    """返回产品管理库 Session 工厂。

    Session 是一次数据库工作单元。Repository 会通过它完成查询、写入和事务提交。
    """

    return sessionmaker(
        bind=get_product_engine(),
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )


def get_product_session() -> Generator[Session]:
    """FastAPI 依赖函数：为一次请求提供产品库 Session。"""

    session_factory = get_product_session_factory()
    with session_factory() as session:
        yield session


@contextmanager
def product_session_scope() -> Generator[Session]:
    """脚本或后台任务使用的产品库事务上下文。

    API 层通常使用 `get_product_session`，命令行脚本、同步任务或测试辅助工具可以使用
    这个上下文，确保异常时自动回滚。
    """

    session_factory = get_product_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
