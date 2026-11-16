from precedent.store.base import Store, ZoningInfo
from precedent.store.local import LocalStore

__all__ = ["LocalStore", "Store", "ZoningInfo", "open_store"]


def open_store(database_url: str | None = None, data_dir: str | None = None) -> Store:
    """PostGIS when a DATABASE URL is given, otherwise the file-backed local store."""
    if database_url:
        from precedent.store.postgres import PostgresStore

        return PostgresStore(database_url)
    from pathlib import Path

    return LocalStore(Path(data_dir or "data"))
