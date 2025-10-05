document.addEventListener('DOMContentLoaded', function() {
    loadSettings();

    document.getElementById('settingsForm').addEventListener('submit', function(e) {
        e.preventDefault();
        saveSettings();
    });

    document.getElementById('startAutoRefresh')?.addEventListener('click', startAutoRefresh);
    document.getElementById('stopAutoRefresh')?.addEventListener('click', stopAutoRefresh);
    document.getElementById('refreshStatus')?.addEventListener('click', checkAutoRefreshStatus);
    document.getElementById('testKeitaroBtn')?.addEventListener('click', testKeitaroConnection);
    document.getElementById('syncKeitaroBtn')?.addEventListener('click', syncKeitaroOnly);

    // Проверяем статус Telegram при загрузке
    setTimeout(checkTelegramStatus, 1000);
    
    // Проверяем статус каждые 30 секунд
    setInterval(checkTelegramStatus, 30000);
});

function loadSettings() {
    fetch('/api/settings')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const config = data.config;
                
                document.getElementById('syncApiKey').value = config.sync_api_key || '';
                document.getElementById('proxy').value = config.proxy || '';
                document.getElementById('useProxy').checked = config.use_proxy || false;
                document.getElementById('autoRefreshCampaigns').checked = config.auto_refresh_campaigns || false;
                document.getElementById('autoRefreshAdsets').checked = config.auto_refresh_adsets || false;
                document.getElementById('autoRefreshInterval').value = config.auto_refresh_interval || 15;
            
                document.getElementById('keitaroApiKey').value = config.keitaro_api_key || '';
                document.getElementById('keitaroDomain').value = config.keitaro_domain || 'uniaffnu.com';
                document.getElementById('keitaroRangeDays').value = config.keitaro_range_days || 1;

                console.log('Настройки загружены успешно');
            } else {
                console.error('Ошибка загрузки настроек:', data.error);
                Swal.fire('Ошибка', 'Не удалось загрузить настройки', 'error');
            }
        })
        .catch(error => {
            console.error('Ошибка загрузки настроек:', error);
            Swal.fire('Ошибка', 'Ошибка сети при загрузке настроек', 'error');
        });
}

function saveSettings() {
    const settings = {
        sync_api_key: document.getElementById('syncApiKey').value,
        proxy: document.getElementById('proxy').value,
        use_proxy: document.getElementById('useProxy').checked,
        auto_refresh_campaigns: document.getElementById('autoRefreshCampaigns').checked,
        auto_refresh_adsets: document.getElementById('autoRefreshAdsets').checked,
        auto_refresh_interval: parseInt(document.getElementById('autoRefreshInterval').value) || 60,
        keitaro_api_key: document.getElementById('keitaroApiKey').value,
        keitaro_domain: document.getElementById('keitaroDomain').value,
        keitaro_range_days: parseInt(document.getElementById('keitaroRangeDays').value) || 1
    };
    
    console.log('Сохранение настроек:', settings);

    const saveBtn = document.querySelector('#settingsForm button[type="submit"]');
    const originalText = saveBtn.innerHTML;
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Сохранение...';
    
    fetch('/api/settings', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(settings)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire({
                icon: 'success',
                title: 'Успех!',
                text: 'Настройки сохранены',
                timer: 2000,
                showConfirmButton: false
            });
            
            setTimeout(checkAutoRefreshStatus, 500);
            
        } else {
            Swal.fire('Ошибка!', data.error || 'Не удалось сохранить настройки', 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка!', 'Ошибка сети: ' + error, 'error');
    })
    .finally(() => {
        saveBtn.disabled = false;
        saveBtn.innerHTML = originalText;
    });
}

function startAutoRefresh() {
    const interval = parseInt(document.getElementById('autoRefreshInterval').value) || 60;
    
    if (interval < 1 || interval > 60) {
        Swal.fire('Ошибка', 'Интервал должен быть от 1 до 60 минут', 'error');
        return;
    }
    
    const btn = document.getElementById('startAutoRefresh');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Запуск...';
    
    fetch('/api/auto_refresh', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            action: 'start',
            interval: interval
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire({
                icon: 'success',
                title: 'Успех!',
                text: data.message,
                timer: 2000,
                showConfirmButton: false
            });
            updateAutoRefreshUI(true);
        } else {
            Swal.fire('Ошибка!', data.error, 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка!', 'Ошибка сети: ' + error, 'error');
    })
    .finally(() => {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-play-fill"></i> Запустить автообновление';
    });
}

function stopAutoRefresh() {
    const btn = document.getElementById('stopAutoRefresh');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Остановка...';
    
    fetch('/api/auto_refresh', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            action: 'stop'
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire({
                icon: 'success',
                title: 'Успех!',
                text: data.message,
                timer: 2000,
                showConfirmButton: false
            });
            updateAutoRefreshUI(false);
        } else {
            Swal.fire('Ошибка!', data.error, 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка!', 'Ошибка сети: ' + error, 'error');
    })
    .finally(() => {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-stop-fill"></i> Остановить автообновление';
    });
}

function checkAutoRefreshStatus() {
    const btn = document.getElementById('refreshStatus');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Проверка...';
    
    fetch('/api/auto_refresh', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            action: 'status'
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const status = data.status;
            const interval = parseInt(document.getElementById('autoRefreshInterval').value) || 60;
            
            let statusText = status.running 
                ? `✅ Система автоконтроля и автообновления запущена`
                : '⏸️ Система автоконтроля и автообновления остановлена';
            
            if (status.running) {
                statusText += `\n📊 Автоконтроль: ${status.auto_control_running ? '✅' : '❌'}`;
                statusText += `\n🔄 Автообновление: ${status.auto_refresh_running ? '✅' : '❌'}`;
                statusText += `\n⏰ Интервал: ${status.interval} мин`;
            }
            
            document.getElementById('autoRefreshStatus').textContent = statusText;
            updateAutoRefreshUI(status.running);
            
        } else {
            Swal.fire('Ошибка!', data.error, 'error');
        }
    })
    .catch(error => {
        console.error('Ошибка проверки статуса:', error);
        document.getElementById('autoRefreshStatus').textContent = '❌ Ошибка получения статуса';
    })
    .finally(() => {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-info-circle"></i> Статус';
    });
}

function updateAutoRefreshUI(isRunning) {
    document.getElementById('startAutoRefresh').disabled = isRunning;
    document.getElementById('stopAutoRefresh').disabled = !isRunning;
    
    const statusElement = document.getElementById('autoRefreshStatus');
    if (statusElement) {
        const interval = parseInt(document.getElementById('autoRefreshInterval').value) || 60;
        statusElement.className = isRunning ? 'mt-2 text-success fw-bold' : 'mt-2 text-muted';
    }
}

function testKeitaroConnection() {
    const btn = document.getElementById('testKeitaroBtn');
    const originalText = btn.innerHTML;
    
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Тестирование...';
    
    fetch('/api/test_keitaro', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire({
                icon: 'success',
                title: 'Успех!',
                html: `<p>${data.message}</p><p class="small">Кампаний: ${data.campaigns_count || 0}</p>`,
                timer: 3000,
                showConfirmButton: true
            });
        } else {
            Swal.fire({
                icon: 'error',
                title: 'Ошибка!',
                text: data.error,
                confirmButtonText: 'OK'
            });
        }
    })
    .catch(error => {
        Swal.fire({
            icon: 'error',
            title: 'Ошибка сети!',
            text: 'Не удалось подключиться к серверу',
            confirmButtonText: 'OK'
        });
    })
    .finally(() => {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-plug"></i> Тестировать соединение';
    });
}

function syncKeitaroOnly() {
    const btn = document.getElementById('syncKeitaroBtn');
    const originalText = btn.innerHTML;
    
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Синхронизация...';
    
    fetch('/api/sync/keitaro_only', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire({
                icon: 'success',
                title: 'Успех!',
                html: `<p>${data.message}</p>
                       <p class="small">Обновлено кампаний: ${data.updated_count || 0}</p>
                       <p class="small">Всего записей: ${data.total_records || 0}</p>`,
                timer: 3000,
                showConfirmButton: true
            });
        } else {
            Swal.fire({
                icon: 'error',
                title: 'Ошибка!',
                text: data.error,
                confirmButtonText: 'OK'
            });
        }
    })
    .catch(error => {
        Swal.fire({
            icon: 'error',
            title: 'Ошибка сети!',
            text: 'Не удалось подключиться к серверу',
            confirmButtonText: 'OK'
        });
    })
    .finally(() => {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-cloud-arrow-down"></i> Синхронизировать Keitaro';
    });
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show`;
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.getElementById('notifications');
    if (container) {
        container.appendChild(notification);
        
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 5000);
    }
}

const style = document.createElement('style');
style.textContent = `
    .spin { 
        animation: spin 1s linear infinite; 
    }
    
    @keyframes spin { 
        100% { 
            transform: rotate(360deg); 
        } 
    }
    
    .auto-refresh-status {
        font-family: 'Courier New', monospace;
        font-size: 0.9rem;
        padding: 0.5rem;
        border-radius: 0.25rem;
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
    }
    
    .settings-section {
        margin-bottom: 2rem;
        padding: 1.5rem;
        border: 1px solid #dee2e6;
        border-radius: 0.5rem;
        background-color: #fff;
    }
    
    .settings-section h5 {
        color: #0d6efd;
        border-bottom: 2px solid #0d6efd;
        padding-bottom: 0.5rem;
        margin-bottom: 1.5rem;
    }
    
    .form-label {
        font-weight: 500;
        color: #495057;
    }
    
    .btn-group-auto-refresh {
        display: flex;
        gap: 0.5rem;
        flex-wrap: wrap;
    }
    
    .btn-group-auto-refresh .btn {
        flex: 1;
        min-width: 120px;
    }
    
    @media (max-width: 768px) {
        .btn-group-auto-refresh {
            flex-direction: column;
        }
        
        .btn-group-auto-refresh .btn {
            width: 100%;
        }
    }
`;
document.head.appendChild(style);

let autoRefreshState = {
    running: false,
    interval: 60,
    nextRefresh: null
};

function connectTelegram() {
    const btn = document.getElementById('connectTelegramBtn');
    const originalText = btn.innerHTML;
    
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Подключение...';
    
    // Получаем уникальную ссылку для подключения
    fetch('/api/telegram/connect_link')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Открываем ссылку на бота
                window.open(data.connect_url, '_blank');
                
                // Показываем инструкцию
                Swal.fire({
                    title: 'Подключение Telegram',
                    html: `
                        <p>1. Перейдите в Telegram по ссылке выше</p>
                        <p>2. Нажмите кнопку "START" в диалоге с ботом</p>
                        <p>3. Вернитесь на эту страницу</p>
                        <p>4. Нажмите "Проверить подключение" через несколько секунд</p>
                    `,
                    icon: 'info',
                    confirmButtonText: 'Понятно'
                });
                
                // Автоматически проверяем статус через 10 секунд
                setTimeout(checkTelegramStatus, 10000);
            } else {
                Swal.fire('Ошибка', data.error, 'error');
            }
        })
        .catch(error => {
            Swal.fire('Ошибка', 'Ошибка сети: ' + error, 'error');
        })
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-telegram"></i> Подключить Telegram';
        });
}

function checkTelegramStatus() {
    fetch('/api/telegram/status')
        .then(response => response.json())
        .then(data => {
            const statusElement = document.getElementById('telegramStatus');
            if (data.success) {
                if (data.connected) {
                    statusElement.innerHTML = `
                        <span class="badge bg-success">✅ Подключен</span>
                        <p class="small text-muted mt-1">Ваш Telegram аккаунт подключен для уведомлений</p>
                        <button type="button" class="btn btn-sm btn-outline-danger mt-1" onclick="disconnectTelegram()">
                            <i class="bi bi-x-circle"></i> Отключить
                        </button>
                        <button type="button" class="btn btn-sm btn-outline-info mt-1" onclick="testTelegramNotification()">
                            <i class="bi bi-bell"></i> Тест уведомление
                        </button>
                    `;
                } else {
                    statusElement.innerHTML = `
                        <span class="badge bg-warning">❌ Не подключен</span>
                        <p class="small text-muted mt-1">Нажмите кнопку выше для подключения</p>
                    `;
                }
            }
        })
        .catch(error => {
            console.error('Error checking Telegram status:', error);
        });
}

function disconnectTelegram() {
    Swal.fire({
        title: 'Отключить Telegram?',
        text: 'Вы больше не будете получать уведомления в Telegram',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Да, отключить',
        cancelButtonText: 'Отмена'
    }).then((result) => {
        if (result.isConfirmed) {
            fetch('/api/telegram/disconnect', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    Swal.fire('Отключено', 'Telegram уведомления отключены', 'success');
                    checkTelegramStatus();
                } else {
                    Swal.fire('Ошибка', data.error, 'error');
                }
            })
            .catch(error => {
                Swal.fire('Ошибка', 'Ошибка сети: ' + error, 'error');
            });
        }
    });
}

function testTelegramNotification() {
    fetch('/api/telegram/test', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire('Успех', 'Тестовое уведомление отправлено', 'success');
        } else {
            Swal.fire('Ошибка', data.error, 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка', 'Ошибка сети: ' + error, 'error');
    });
}

function calculateNextRefreshTime(intervalMinutes) {
    const now = new Date();
    const nextRefresh = new Date();
    nextRefresh.setMinutes(nextRefresh.getMinutes() + intervalMinutes);
    nextRefresh.setSeconds(0, 0);
    return nextRefresh.toLocaleTimeString();
}

function updateNextRefreshInfo() {
    if (autoRefreshState.running) {
        const nextRefreshElement = document.getElementById('nextRefreshTime');
        if (nextRefreshElement) {
            nextRefreshElement.textContent = `Следующее обновление: ${calculateNextRefreshTime(autoRefreshState.interval)}`;
        }
    }
}

setInterval(updateNextRefreshInfo, 60000);

// Делаем функции глобальными, чтобы HTML onclick их видел
window.connectTelegram = connectTelegram;
window.checkTelegramStatus = checkTelegramStatus;
window.disconnectTelegram = disconnectTelegram;
window.testTelegramNotification = testTelegramNotification;