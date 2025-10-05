import requests
import logging
import threading
import time
import hashlib
from typing import Dict, Optional
from database import get_db_connection

logger = logging.getLogger(__name__)

# Конфигурация бота
TELEGRAM_BOT_TOKEN = "8270713137:AAF-pyYSF62KzA1hYkKWJXhMfGJ0bVvpwfs"
BOT_USERNAME = "arbitrationlog_bot"

# Хранилище для связи user_id и telegram_chat_id
user_telegram_mapping = {}
telegram_codes = {}  # {code: user_id} для временного хранения кодов
mapping_lock = threading.Lock()

def init_telegram_bot():
    """Инициализация Telegram бота"""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("❌ Telegram bot token not configured!")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get('ok'):
            bot_info = data['result']
            logger.info(f"✅ Telegram bot initialized: @{bot_info['username']} ({bot_info['first_name']})")
            return True
        else:
            logger.error(f"❌ Failed to initialize Telegram bot: {data.get('description')}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error initializing Telegram bot: {e}")
        return False

def get_bot_info():
    """Получить информацию о боте"""
    return {
        'token': TELEGRAM_BOT_TOKEN,
        'username': BOT_USERNAME,
        'bot_url': f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else None
    }

def set_user_telegram_chat_id(user_id: int, chat_id: str) -> bool:
    """Сохранить связь user_id с telegram_chat_id"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Обновляем настройки пользователя
            cursor.execute("""
                UPDATE settings 
                SET telegram_chat_id = ? 
                WHERE user_id = ?
            """, (chat_id, user_id))
            
            if cursor.rowcount == 0:
                # Если запись настроек не существует, создаем ее
                cursor.execute("""
                    INSERT INTO settings (user_id, telegram_chat_id)
                    VALUES (?, ?)
                """, (user_id, chat_id))
            
            conn.commit()
            
            # Сохраняем в памяти для быстрого доступа
            with mapping_lock:
                user_telegram_mapping[user_id] = chat_id
            
            logger.info(f"✅ Telegram chat ID {chat_id} saved for user {user_id}")
            return True
            
    except Exception as e:
        logger.error(f"❌ Error saving Telegram chat ID for user {user_id}: {e}")
        return False

def get_user_telegram_chat_id(user_id: int) -> Optional[str]:
    """Получить telegram_chat_id для пользователя"""
    # Сначала проверяем в памяти
    with mapping_lock:
        if user_id in user_telegram_mapping:
            return user_telegram_mapping[user_id]
    
    # Если нет в памяти, загружаем из базы
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT telegram_chat_id 
                FROM settings 
                WHERE user_id = ?
            """, (user_id,))
            
            row = cursor.fetchone()
            if row and row['telegram_chat_id']:
                chat_id = row['telegram_chat_id']
                # Сохраняем в памяти
                with mapping_lock:
                    user_telegram_mapping[user_id] = chat_id
                return chat_id
            return None
            
    except Exception as e:
        logger.error(f"❌ Error getting Telegram chat ID for user {user_id}: {e}")
        return None

def send_telegram_message(message: str, user_id: int = None, chat_id: str = None) -> bool:
    """Отправить сообщение в Telegram"""
    try:
        if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
            logger.debug("Telegram bot token not configured")
            return False
        
        # Определяем chat_id
        target_chat_id = chat_id
        if user_id and not target_chat_id:
            target_chat_id = get_user_telegram_chat_id(user_id)
        
        if not target_chat_id:
            logger.debug(f"No Telegram chat ID found for user {user_id}")
            return False

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': target_chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }

        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        logger.debug(f"✅ Telegram message sent to user {user_id} (chat_id: {target_chat_id})")
        return True

    except requests.exceptions.RequestException as e:
        logger.warning(f"❌ Failed to send Telegram message: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error sending Telegram message: {e}")
        return False

def send_welcome_message(chat_id: str, username: str = None):
    """Отправить приветственное сообщение"""
    welcome_text = f"""
🤖 <b>Добро пожаловать в UniTool!</b>

✅ Ваш Telegram аккаунт успешно подключен к системе.

Теперь вы будете получать уведомления о:
• Автоматическом контроле рекламных кампаний
• Изменениях статусов адсетов
• Критических событиях и ошибках
• Результатах оптимизации

Для отключения уведомлений используйте команду /stop
"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': welcome_text,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, json=payload, timeout=10)
        return response.json().get('ok', False)
    except Exception as e:
        logger.error(f"Error sending welcome message: {e}")
        return False

def disconnect_telegram(user_id: int) -> bool:
    """Отключить Telegram уведомления для пользователя"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE settings 
                SET telegram_chat_id = NULL 
                WHERE user_id = ?
            """, (user_id,))
            
            conn.commit()
            
            # Удаляем из памяти
            with mapping_lock:
                if user_id in user_telegram_mapping:
                    del user_telegram_mapping[user_id]
            
            logger.info(f"✅ Telegram disconnected for user {user_id}")
            return True
            
    except Exception as e:
        logger.error(f"❌ Error disconnecting Telegram for user {user_id}: {e}")
        return False

def process_telegram_update(update: Dict):
    """Обработать входящее обновление от Telegram"""
    try:
        if 'message' not in update:
            return
        
        message = update['message']
        chat_id = str(message['chat']['id'])
        text = message.get('text', '').strip()
        
        if text.startswith('/start'):
            # Извлекаем код из команды /start
            parts = text.split()
            if len(parts) > 1:
                code = parts[1]
                user_id = telegram_codes.get(code)
                
                if user_id:
                    # Сохраняем связь user_id -> chat_id
                    if set_user_telegram_chat_id(user_id, chat_id):
                        # Удаляем использованный код
                        telegram_codes.pop(code, None)
                        send_welcome_message(chat_id)
                        logger.info(f"✅ User {user_id} connected Telegram chat {chat_id}")
                        return
                    else:
                        send_telegram_direct_message(chat_id, "❌ Ошибка при подключении. Попробуйте снова.")
                        return
            
            # Если код невалидный или отсутствует
            send_telegram_direct_message(chat_id, 
                "🤖 <b>UniTool Bot</b>\n\n"
                "Для подключения:\n"
                "1. Перейдите в настройки UniTool\n"
                "2. Нажмите 'Подключить Telegram'\n"
                "3. Используйте полученную ссылку")
            
        elif text == '/stop':
            send_telegram_direct_message(chat_id, 
                "Для отключения уведомлений перейдите в настройки вашего аккаунта в UniTool.")
            
    except Exception as e:
        logger.error(f"Error processing Telegram update: {e}")

def send_telegram_direct_message(chat_id: str, text: str):
    """Отправить сообщение напрямую по chat_id"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, json=payload, timeout=10)
        return response.json().get('ok', False)
    except Exception as e:
        logger.error(f"Error sending direct Telegram message: {e}")
        return False

def generate_connect_code(user_id: int) -> str:
    """Сгенерировать уникальный код для подключения"""
    unique_code = hashlib.md5(f"{user_id}_{TELEGRAM_BOT_TOKEN}_{time.time()}".encode()).hexdigest()[:8]
    telegram_codes[unique_code] = user_id
    return unique_code

# Инициализируем бот при импорте
if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
    init_telegram_bot()