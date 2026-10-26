from pathlib import Path
from argparse import ArgumentParser
import sqlite3


def get_db_summary(path_to_db: str) -> None | dict[str, int]:
    """Считает количество направлений, руководителей, аудиторий, 
    активных и неактивных кружков, регулярных занятий и исключений"""
    db_path = Path(path_to_db).resolve()
    if not db_path.is_file():
        print(f"База данных не найдена по пути: {db_path}")
        return None
    
    conn = None
    try:
        conn = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
        cursor = conn.cursor()
        categories_num = cursor.execute(
            "SELECT COUNT(*) FROM categories"
        ).fetchone()[0]
        leaders_num = cursor.execute(
            "SELECT COUNT(*) FROM leaders"
        ).fetchone()[0]
        rooms_num = cursor.execute(
            "SELECT COUNT(*) FROM rooms"
        ).fetchone()[0]
        sessions_num = cursor.execute(
            "SELECT COUNT(*) FROM sessions"
        ).fetchone()[0]
        session_exceptions_num = cursor.execute(
            "SELECT COUNT(*) FROM session_exceptions"
        ).fetchone()[0]
        active_clubs_num = cursor.execute(
            "SELECT COUNT(*) FROM clubs WHERE is_active = 1"
        ).fetchone()[0]
        non_active_clubs_num = cursor.execute(
            "SELECT COUNT(*) FROM clubs WHERE is_active = 0"
        ).fetchone()[0]
        res = {
            "categories": categories_num,
            "leaders": leaders_num,
            "rooms": rooms_num,
            "sessions": sessions_num,
            "sessions_exceptions": session_exceptions_num,
            "active_clubs": active_clubs_num,
            "non_active_clubs": non_active_clubs_num
        }
        print("Сводка по базе данных:")
        print(f"  Кол-во направлений:        {categories_num}")
        print(f"  Кол-во руководителей:      {leaders_num}")
        print(f"  Кол-во аудиторий:          {rooms_num}")
        print(f"  Кол-во активных кружков:   {active_clubs_num}")
        print(f"  Кол-во неактивных кружков: {non_active_clubs_num}")
        print(f"  Кол-во регулярных занятий: {sessions_num}")
        print(f"  Кол-во исключений:         {session_exceptions_num}")
        return res  
    except sqlite3.Error as error:
        print(f"Ошибка при работе с бд: {error}")
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    parser = ArgumentParser(
        description="Утилита для краткой сводки по базе данных (sqlite)"
    )
    parser.add_argument(
        "-p", "--path", required=True, help="Путь к дб (sqlite)", type=str
    )
    args = parser.parse_args()
    get_db_summary(args.path)
