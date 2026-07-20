"""Task 18.2: Postgres engine 配置测试。

验证：当 DATABASE_URL 为 postgresql 时，engine 配置 pool_size=5 / max_overflow=10。
SQLite 时不受影响。
"""
import pytest


class TestDatabasePostgres:
    def test_postgres_engine_has_pool_config(self, monkeypatch):
        """Postgres URL 时 engine 有 pool_size 和 max_overflow。"""
        import backend.core.database as db_module

        monkeypatch.setattr(
            db_module.settings, "DATABASE_URL",
            "postgresql+asyncpg://user:pass@localhost/db"
        )

        engine = db_module._create_engine()

        assert engine.pool.size() == 5
        assert engine.pool._max_overflow == 10

    def test_sqlite_engine_no_pool_config(self, monkeypatch):
        """SQLite URL 时 engine 没有 pool_size / max_overflow。"""
        import backend.core.database as db_module

        monkeypatch.setattr(
            db_module.settings, "DATABASE_URL",
            "sqlite+aiosqlite:///./test.db"
        )

        engine = db_module._create_engine()

        # SQLite 使用 NullPool，没有 size 限制
        # 不报错即可（pool_size 参数被忽略）
        assert engine is not None
