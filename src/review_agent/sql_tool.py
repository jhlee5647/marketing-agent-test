import sqlite3
from pathlib import Path


def run_sql(db_path: Path, sql: str) -> dict:
    """적재 데이터에 SQL을 실행한다.

    Returns:
        성공하면 `columns`, `rows`를 담은 dict.
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description]
        return {"columns": columns, "rows": [list(r) for r in cursor.fetchall()]}
    finally:
        conn.close()
