import sqlite3
from pathlib import Path


def run_sql(db_path: Path, sql: str) -> dict:
    """적재 데이터에 SQL을 읽기 전용으로 실행한다.

    Returns:
        성공하면 `columns`, `rows`를 담은 dict. SQL 오류는 예외 대신 `error` 메시지를 담아 돌려준다.
    """
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    # ATTACH는 읽기 전용 모드를 우회해 새 DB 파일을 만들 수 있으므로 막는다.
    conn.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
    try:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description or []]
        return {"columns": columns, "rows": [list(r) for r in cursor.fetchall()]}
    except sqlite3.Error as e:
        return {"error": str(e)}
    finally:
        conn.close()
