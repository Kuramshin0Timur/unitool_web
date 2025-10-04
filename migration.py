import sqlite3
from pathlib import Path

DB_PATH = Path("unitool.db")

def migrate_add_exclude_field():
    """Добавляет поле exclude_from_autocontrol в таблицу adsets"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Проверяем, существует ли уже поле
        cursor.execute("PRAGMA table_info(adsets)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'exclude_from_autocontrol' not in columns:
            # Добавляем поле
            cursor.execute("ALTER TABLE adsets ADD COLUMN exclude_from_autocontrol BOOLEAN DEFAULT 0")
            print("✅ Поле exclude_from_autocontrol успешно добавлено в таблицу adsets")
            
            # Создаем индекс для улучшения производительности
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_adsets_exclude ON adsets (user_id, exclude_from_autocontrol)")
            print("✅ Индекс для поля exclude_from_autocontrol создан")
        else:
            print("ℹ️ Поле exclude_from_autocontrol уже существует")
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")

if __name__ == "__main__":
    migrate_add_exclude_field()