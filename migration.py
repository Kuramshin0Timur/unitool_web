# scripts/migrate_normalize_tokens.py
from backend.reserve_tokens import normalize_token, normalize_account_id
from database import get_db_connection
import logging

logger = logging.getLogger('migrate')
logging.basicConfig(level=logging.INFO)

def migrate(user_id=None):
    with get_db_connection(user_id) as conn:
        cur = conn.cursor()

        # 1) Нормализуем reserve_tokens.token
        cur.execute("SELECT id, user_id, king, token FROM reserve_tokens")
        rows = cur.fetchall()
        for r in rows:
            nid = normalize_token(r['token'])
            if nid != r['token']:
                try:
                    cur.execute("UPDATE reserve_tokens SET token = ? WHERE id = ?", (nid, r['id']))
                except Exception as e:
                    logger.error(f"Conflict/err updating token id {r['id']}: {e}")

        # 2) Нормализуем reserve_token_accounts.token и account_id
        cur.execute("SELECT id, user_id, king, token, account_id FROM reserve_token_accounts")
        rows = cur.fetchall()
        for r in rows:
            new_token = normalize_token(r['token'])
            new_acc = normalize_account_id(r['account_id'])
            if new_token != r['token'] or new_acc != r['account_id']:
                try:
                    cur.execute("""
                        UPDATE reserve_token_accounts SET token = ?, account_id = ? WHERE id = ?
                    """, (new_token, new_acc, r['id']))
                except Exception as e:
                    logger.error(f"Conflict updating reserve_token_accounts id {r['id']}: {e}")

        conn.commit()
        logger.info("Миграция завершена. Проверьте логи на предмет конфликтов.")

if __name__ == '__main__':
    # если multi-user: запустите для каждого user_id или модифицируйте чтобы пройтись по всем
    migrate(None)
