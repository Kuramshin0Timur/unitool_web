import sqlite3
import os

# Путь к вашему файлу базы данных
DB_PATH = "unitool.db"

def run_migration():
    """Выполняет SQL-запрос для добавления колонки max_cpa."""
    if not os.path.exists(DB_PATH):
        print(f"Ошибка: Файл базы данных '{DB_PATH}' не найден. Убедитесь, что скрипт находится в той же папке.")
        return

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Попытка добавить новую колонку
        print("Попытка добавить колонку 'max_cpa' в таблицу geo_config...")
        
        # ЭТО ТОТ САМЫЙ ЗАПРОС, который мы не смогли найти
        cursor.execute("ALTER TABLE geo_config ADD COLUMN max_cpa REAL DEFAULT 0.0;")
        conn.commit()
        
        print("✅ Успех! Колонка 'max_cpa' добавлена. База данных готова.")
        
    except sqlite3.OperationalError as e:
        # Если колонка уже была добавлена, игнорируем ошибку
        if "duplicate column name" in str(e):
            print("ℹ️ Колонка 'max_cpa' уже существует. Пропускаем. База данных готова.")
        else:
            print(f"❌ Критическая ошибка при работе с БД: {e}")
            
    except Exception as e:
        print(f"❌ Непредвиденная ошибка: {e}")
        
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    run_migration()