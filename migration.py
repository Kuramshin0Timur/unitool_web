# migration.py
from database import get_db_connection

def migrate_database():
    """Добавляет новые колонки в таблицу settings"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Проверяем существование колонок и добавляем их если нужно
        cursor.execute("PRAGMA table_info(settings)")
        columns = [column[1] for column in cursor.fetchall()]
        
        new_columns = [
            ('keitaro_api_key', 'TEXT'),
            ('keitaro_domain', 'TEXT DEFAULT "uniaffnu.com"'),
            ('keitaro_range_days', 'INTEGER DEFAULT 1')
        ]
        
        for column_name, column_type in new_columns:
            if column_name not in columns:
                try:
                    cursor.execute(f"ALTER TABLE settings ADD COLUMN {column_name} {column_type}")
                    print(f"Добавлена колонка {column_name}")
                except Exception as e:
                    print(f"Ошибка добавления колонки {column_name}: {e}")
        
        conn.commit()
        print("Миграция базы данных завершена")

if __name__ == "__main__":
    migrate_database()