"""数据库引擎与 session（从 1 号项目适配，dev 用 SQLite async）。

设计：模块级 ``engine`` 由 ``settings.DATABASE_URL`` 构建，供应用运行时使用。
测试不走模块引擎——conftest 自建内存引擎（StaticPool）并建表，保证测试间隔离。
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # commit 后对象还能用
)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


async def get_db():
    """每个请求拿一个 session，用完还回连接池。"""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """启动时验证数据库连通性并建表（alembic 接管迁移后可移除建表逻辑）。"""
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
        await conn.run_sync(Base.metadata.create_all)
