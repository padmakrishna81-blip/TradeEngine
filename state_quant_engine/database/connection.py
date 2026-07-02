"""Database connection and session management."""
from __future__ import annotations
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import Engine
from state_quant_engine.models.base import Base
from loguru import logger


_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def init_db(db_path: str = "data/sqe.db") -> None:
    """Initialize database, creating tables if they don't exist."""
    global _engine, _SessionLocal
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        echo=False,
    )

    @event.listens_for(_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(_engine)
    _run_migrations(_engine)
    logger.info(f"Database initialized at {db_path}")


def _run_migrations(engine: Engine) -> None:
    """Apply lightweight additive migrations for new columns and constraint fixes."""
    with engine.connect() as conn:
        text = __import__("sqlalchemy").text
        simple_cols = [
            ("strategy",     "ALTER TABLE strategy ADD COLUMN drawdown_days INTEGER DEFAULT 52"),
            ("position",     "ALTER TABLE position ADD COLUMN version_id INTEGER DEFAULT 1"),
            ("trade_log",    "ALTER TABLE trade_log ADD COLUMN version_id INTEGER DEFAULT 1"),
            ("scan_history", "ALTER TABLE scan_history ADD COLUMN version_id INTEGER DEFAULT 1"),
            ("watchlist",    "ALTER TABLE watchlist ADD COLUMN watchlist_group_id INTEGER DEFAULT NULL"),
        ]
        for label, sql in simple_cols:
            try:
                conn.execute(text(sql))
                conn.commit()
                logger.info(f"Migration applied: {label}")
            except Exception:
                pass  # column already exists

        # Fix scan_history unique constraint: old=(date,symbol), new=(date,symbol,version_id)
        # SQLite doesn't support ALTER CONSTRAINT, so rebuild the table.
        try:
            row = conn.execute(text(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name='uq_scan_date_symbol_ver'"
            )).fetchone()
            if row is None:
                # Need to rebuild to drop the old constraint and add new one
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS scan_history_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date DATE NOT NULL,
                        symbol VARCHAR(50) NOT NULL,
                        score FLOAT DEFAULT 0.0,
                        recommendation VARCHAR(20) DEFAULT 'WATCH',
                        version_id INTEGER DEFAULT 1,
                        UNIQUE (date, symbol, version_id)
                    )
                """))
                conn.execute(text("""
                    INSERT OR IGNORE INTO scan_history_new
                        (id, date, symbol, score, recommendation, version_id)
                    SELECT id, date, symbol, score, recommendation,
                           COALESCE(version_id, 1)
                    FROM scan_history
                """))
                conn.execute(text("DROP TABLE scan_history"))
                conn.execute(text("ALTER TABLE scan_history_new RENAME TO scan_history"))
                conn.commit()
                logger.info("Migration: rebuilt scan_history with (date,symbol,version_id) unique constraint")
        except Exception as e:
            logger.warning(f"scan_history constraint migration skipped: {e}")

        # Fix position unique constraint: old=(symbol,cycle,chunk_no), new includes version_id
        try:
            row = conn.execute(text(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name='uq_position_cycle_chunk_ver'"
            )).fetchone()
            if row is None:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS position_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol VARCHAR(50) NOT NULL,
                        cycle INTEGER DEFAULT 1,
                        chunk_no INTEGER DEFAULT 1,
                        quantity FLOAT DEFAULT 0.0,
                        buy_price FLOAT DEFAULT 0.0,
                        buy_date DATE,
                        current_price FLOAT DEFAULT 0.0,
                        highest_price FLOAT DEFAULT 0.0,
                        highest_profit FLOAT DEFAULT 0.0,
                        current_profit FLOAT DEFAULT 0.0,
                        health_score FLOAT DEFAULT 0.0,
                        status VARCHAR(20) DEFAULT 'OPEN',
                        version_id INTEGER DEFAULT 1,
                        UNIQUE (symbol, cycle, chunk_no, version_id)
                    )
                """))
                conn.execute(text("""
                    INSERT OR IGNORE INTO position_new
                        (id, symbol, cycle, chunk_no, quantity, buy_price, buy_date,
                         current_price, highest_price, highest_profit, current_profit,
                         health_score, status, version_id)
                    SELECT id, symbol, cycle, chunk_no, quantity, buy_price, buy_date,
                           current_price, highest_price, highest_profit, current_profit,
                           health_score, status, COALESCE(version_id, 1)
                    FROM position
                """))
                conn.execute(text("DROP TABLE position"))
                conn.execute(text("ALTER TABLE position_new RENAME TO position"))
                conn.commit()
                logger.info("Migration: rebuilt position with (symbol,cycle,chunk_no,version_id) unique constraint")
        except Exception as e:
            logger.warning(f"position constraint migration skipped: {e}")

        # Migrate watchlist: rebuild to drop UNIQUE(symbol) and assign existing rows to group 1
        try:
            wl_sql = conn.execute(text(
                "SELECT sql FROM sqlite_master WHERE name='watchlist'"
            )).fetchone()
            if wl_sql and "UNIQUE (symbol)" in wl_sql[0]:
                # Old constraint present — rebuild table
                conn.execute(text(
                    "INSERT OR IGNORE INTO watchlist_group (id, name, description, is_default) "
                    "VALUES (1, 'Default', 'Default watchlist', 1)"
                ))
                conn.commit()
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS watchlist_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol VARCHAR(50) NOT NULL,
                        name VARCHAR(200),
                        exchange VARCHAR(20),
                        asset_type VARCHAR(20) NOT NULL DEFAULT 'STOCK',
                        enabled BOOLEAN DEFAULT 1,
                        priority INTEGER DEFAULT 5,
                        watchlist_group_id INTEGER DEFAULT 1 REFERENCES watchlist_group(id),
                        asset_type_id INTEGER REFERENCES asset_type(id)
                    )
                """))
                conn.execute(text("""
                    INSERT INTO watchlist_new
                        (id, symbol, name, exchange, asset_type, enabled, priority,
                         watchlist_group_id, asset_type_id)
                    SELECT id, symbol, name, exchange, asset_type, enabled, priority,
                           COALESCE(watchlist_group_id, 1), asset_type_id
                    FROM watchlist
                """))
                conn.execute(text("DROP TABLE watchlist"))
                conn.execute(text("ALTER TABLE watchlist_new RENAME TO watchlist"))
                conn.commit()
                logger.info("Migration: rebuilt watchlist — dropped UNIQUE(symbol), added watchlist_group_id")
            else:
                # Ensure group 1 exists and orphaned items get assigned to it
                conn.execute(text(
                    "INSERT OR IGNORE INTO watchlist_group (id, name, description, is_default) "
                    "VALUES (1, 'Default', 'Default watchlist', 1)"
                ))
                conn.execute(text(
                    "UPDATE watchlist SET watchlist_group_id = 1 "
                    "WHERE watchlist_group_id IS NULL"
                ))
                conn.commit()
        except Exception as e:
            logger.warning(f"watchlist group migration skipped: {e}")


def get_session() -> Session:
    """Get a new database session."""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _SessionLocal()


def get_engine() -> Engine:
    """Get the database engine."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine
