def start_auto_control_and_refresh(user_id):
    """Запускает и автоконтроль и автообновление вместе"""
    settings = get_user_settings(user_id)
    interval = settings.get('auto_refresh_interval', 5)
    
    # Запускаем автоконтроль
    with auto_control_lock:
        if user_id not in auto_control_threads:
            auto_control_threads[user_id] = {
                'running': True,
                'thread': threading.Thread(
                    target=run_auto_control_for_user,
                    args=(user_id,),
                    daemon=True
                )
            }
            auto_control_threads[user_id]['thread'].start()
            logger.info(f"Автоконтроль запущен для пользователя {user_id}")
    
    # Запускаем автообновление
    with auto_refresh_lock:
        # Останавливаем предыдущий таймер, если есть
        if user_id in auto_refresh_timers:
            auto_refresh_timers[user_id].cancel()
        
        # Создаем новый таймер
        interval_seconds = interval * 60
        timer = threading.Timer(interval_seconds, lambda: auto_refresh_user_data(user_id, interval))
        timer.daemon = True
        timer.start()
        
        auto_refresh_timers[user_id] = timer
        logger.info(f"Автообновление запущено для пользователя {user_id}, интервал: {interval} мин")
