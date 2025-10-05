document.addEventListener('DOMContentLoaded', function() {
    const runBtn = document.getElementById('runAutoControl');
    const stopBtn = document.getElementById('stopAutoControl');
    const intervalInput = document.getElementById('autoRefreshInterval');
    const logContainer = document.getElementById('autoControlLog');
    const statusElement = document.getElementById('systemStatus');
    
    let autoRefreshInterval = null;
    let systemStatus = {
        running: false,
        auto_control: false,
        auto_refresh: false,
        interval: 60
    };
    
    // Инициализация системы
    initializeSystem();
    
    // Обработчики событий
    runBtn?.addEventListener('click', startAutoSystem);
    stopBtn?.addEventListener('click', stopAutoSystem);
    intervalInput?.addEventListener('change', updateInterval);
    
    function initializeSystem() {
        loadStats();
        checkSystemStatus();
        loadCurrentInterval();
    }
    
    function startAutoSystem() {
        const intervalInput = document.getElementById('autoRefreshInterval');
        const interval = parseInt(intervalInput?.value) || 60;
        
        if (interval < 1 || interval > 120) {
            addLog('❌ Интервал должен быть от 1 до 120 минут', 'error');
            Swal.fire('Ошибка', 'Интервал должен быть от 1 до 120 минут', 'error');
            return;
        }
        
        const runBtn = document.getElementById('runAutoControl');
        showLoading(runBtn, 'Запуск системы...');
        
        fetch('/api/auto_refresh', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                action: 'start' 
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                addLog(`✅ ${data.message}`, 'success');
                Swal.fire('Запущено!', data.message, 'success');
            } else {
                addLog(`❌ Ошибка запуска: ${data.error}`, 'error');
                Swal.fire('Ошибка!', data.error, 'error');
            }
        })
        .catch(error => {
            addLog(`❌ Сетевая ошибка: ${error}`, 'error');
            Swal.fire('Сетевая ошибка!', 'Не удалось запустить систему.', 'error');
        })
        .finally(() => {
            hideLoading(runBtn, '<i class="bi bi-play-fill"></i> Запустить');
            setTimeout(checkSystemStatus, 1000); 
        });
    }
    
    function stopAutoSystem() {
        showLoading(stopBtn, 'Остановка...');
        
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
                addLog('⏹️ Система остановлена. Автоконтроль + автообновление отключены', 'warning');
                updateSystemUI(false);
                
                Swal.fire({
                    icon: 'info',
                    title: 'Система остановлена',
                    text: 'Автоконтроль и автообновление отключены',
                    timer: 2000,
                    showConfirmButton: false
                });
            } else {
                addLog('❌ Ошибка остановки: ' + (data.error || 'Неизвестная ошибка'), 'error');
                Swal.fire('Ошибка!', data.error || 'Не удалось остановить систему', 'error');
            }
        })
        .catch(error => {
            addLog('❌ Ошибка сети: ' + error.message, 'error');
            Swal.fire('Ошибка сети!', 'Не удалось подключиться к серверу', 'error');
        })
        .finally(() => {
            hideLoading(stopBtn, 'Остановить систему');
        });
    }
    
    function checkSystemStatus() {
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
                systemStatus = data.effective_status;
                updateSystemUI(systemStatus.running);
                
                if (systemStatus.running) {
                    addLog('✅ Система работает. Автоконтроль + автообновление активны', 'success');
                }
            }
        })
        .catch(error => {
            console.error('Ошибка проверки статуса системы:', error);
            addLog('⚠️ Не удалось проверить статус системы', 'warning');
        });
    }
    
    function loadCurrentInterval() {
        fetch('/api/settings')
            .then(response => response.json())
            .then(data => {
                if (data.success && data.config.auto_refresh_interval) {
                    const interval = data.config.auto_refresh_interval;
                    if (intervalInput) {
                        intervalInput.value = interval;
                    }
                    systemStatus.interval = interval;
                }
            })
            .catch(error => {
                console.error('Ошибка загрузки интервала:', error);
            });
    }
    
    function updateInterval() {
        const newInterval = parseInt(intervalInput.value) || 60;
        
        if (newInterval < 1 || newInterval > 60) {
            Swal.fire('Ошибка', 'Интервал должен быть от 1 до 60 минут', 'error');
            intervalInput.value = systemStatus.interval;
            return;
        }
        
        if (systemStatus.running) {
            Swal.fire({
                title: 'Обновить интервал?',
                text: `Система работает. Обновить интервал на ${newInterval} минут?`,
                icon: 'question',
                showCancelButton: true,
                confirmButtonText: 'Да, обновить',
                cancelButtonText: 'Отмена'
            }).then((result) => {
                if (result.isConfirmed) {
                    updateSystemInterval(newInterval);
                } else {
                    intervalInput.value = systemStatus.interval;
                }
            });
        } else {
            systemStatus.interval = newInterval;
            addLog(`📊 Интервал обновлен: ${newInterval} минут`, 'info');
        }
    }
    
    function updateSystemInterval(interval) {
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
                systemStatus.interval = interval;
                addLog(`🔄 Интервал обновлен: ${interval} минут`, 'success');
                
                Swal.fire({
                    icon: 'success',
                    title: 'Интервал обновлен!',
                    text: `Новый интервал: ${interval} минут`,
                    timer: 2000,
                    showConfirmButton: false
                });
            } else {
                addLog('❌ Ошибка обновления интервала: ' + data.error, 'error');
                intervalInput.value = systemStatus.interval;
                Swal.fire('Ошибка!', 'Не удалось обновить интервал', 'error');
            }
        })
        .catch(error => {
            addLog('❌ Ошибка сети при обновлении интервала', 'error');
            intervalInput.value = systemStatus.interval;
            Swal.fire('Ошибка сети!', 'Не удалось обновить интервал', 'error');
        });
    }
    
    function updateSystemUI(isRunning) {
        if (runBtn) runBtn.disabled = isRunning;
        if (stopBtn) stopBtn.disabled = !isRunning;
        if (intervalInput) intervalInput.disabled = isRunning;
        
        if (statusElement) {
            if (isRunning) {
                statusElement.innerHTML = `
                    <div class="d-flex align-items-center">
                        <span class="badge bg-success me-2">✅</span>
                        <div>
                            <strong>Система работает</strong>
                            <div class="small">Автоконтроль + автообновление (${systemStatus.interval} мин)</div>
                        </div>
                    </div>
                `;
                statusElement.className = 'text-success mb-3';
            } else {
                statusElement.innerHTML = `
                    <div class="d-flex align-items-center">
                        <span class="badge bg-secondary me-2">⏸️</span>
                        <div>
                            <strong>Система остановлена</strong>
                            <div class="small">Автоконтроль + автообновление отключены</div>
                        </div>
                    </div>
                `;
                statusElement.className = 'text-muted mb-3';
            }
        }
        
        if (runBtn) {
            runBtn.innerHTML = isRunning 
                ? '<i class="bi bi-check-circle"></i> Система запущена' 
                : '<i class="bi bi-play-fill"></i> Запустить систему';
            runBtn.className = isRunning 
                ? 'btn btn-success' 
                : 'btn btn-primary';
        }
        
        if (stopBtn) {
            stopBtn.disabled = !isRunning;
        }
    }
    
    function loadStats() {
        fetch('/api/adsets')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    updateStats(data.data);
                }
            })
            .catch(error => {
                console.error('Ошибка загрузки статистики:', error);
                updateStats([]);
            });
    }
    
    function updateStats(adsets) {
        const total = adsets.length;
        const active = adsets.filter(a => a.effective_status === 'ACTIVE').length;
        const paused = adsets.filter(a => a.effective_status === 'PAUSED').length;
        
        const updateStatElement = (id, value) => {
            const element = document.getElementById(id);
            if (element) element.textContent = value;
        };
        
        updateStatElement('totalAdsets', total);
        updateStatElement('activeAdsets', active);
        updateStatElement('pausedAdsets', paused);
        
        const progressBar = document.getElementById('activeProgress');
        if (progressBar && total > 0) {
            const percentage = (active / total) * 100;
            progressBar.style.width = `${percentage}%`;
            progressBar.setAttribute('aria-valuenow', percentage);
            progressBar.textContent = `${Math.round(percentage)}%`;
        }
    }
    
    function addLog(message, type = 'info') {
        if (!logContainer) return;
        
        const now = new Date();
        const timeString = now.toLocaleTimeString();
        
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${getLogClass(type)}`;
        logEntry.innerHTML = `
            <span class="log-time text-muted">[${timeString}]</span>
            <span class="log-message">${message}</span>
        `;
        
        logContainer.prepend(logEntry);
        
        if (logContainer.children.length > 100) {
            logContainer.removeChild(logContainer.lastChild);
        }
        
        logContainer.scrollTop = 0;
    }
    
    function getLogClass(type) {
        const classes = {
            'info': 'text-info',
            'success': 'text-success',
            'warning': 'text-warning',
            'error': 'text-danger'
        };
        return classes[type] || 'text-info';
    }
    
    function showLoading(button, text) {
        if (!button) return;
        button.disabled = true;
        button.innerHTML = `<i class="bi bi-arrow-repeat spin"></i> ${text}`;
    }
    
    function hideLoading(button, text) {
        if (!button) return;
        button.disabled = false;
        button.innerHTML = text;
    }
    
    // Функция для переключения статуса исключения адсета
    // includeFlag: true  -> вернуть в автоконтроль
// includeFlag: false -> исключить из автоконтроля
function toggleAdsetExclusion(adsetId, name, includeFlag = false) {
    const exclude = !Boolean(includeFlag); // true = исключить
    const actionText = exclude ? 'Исключить' : 'Вернуть';
    const confirmText = exclude ? `Исключить адсет "${name}" из автоконтроля?` : `Вернуть адсет "${name}" в автоконтроль?`;

    Swal.fire({
        title: actionText,
        text: confirmText,
        icon: 'question',
        showCancelButton: true,
        confirmButtonText: actionText,
        cancelButtonText: 'Отмена'
    }).then(result => {
        if (!result.isConfirmed) return;

        // Найдём кнопку на странице (если есть) чтобы показать локальный спиннер
        // лучшее — передавать кнопку явным параметром, но ищем по data-id
        const btnSelector = `.exclude-btn[onclick*="${adsetId}"], .include-btn[onclick*="${adsetId}"]`;
        const btn = document.querySelector(btnSelector);

        const originalBtnHtml = btn ? btn.innerHTML : null;
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<i class="bi bi-arrow-repeat spin"></i> ${actionText}...`;
        }

        fetch('/api/adsets/exclude', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin', // важно — чтобы сессия (cookie) пришла на бэкенд
            body: JSON.stringify({ adset_id: adsetId, exclude: exclude })
        })
        .then(response => {
            if (!response.ok) {
                // читаем текст ошибки (html / текст) для логирования
                return response.text().then(text => { throw new Error(text || response.statusText); });
            }
            // ожидаем JSON; если сервер вернул не JSON — упадём в catch
            return response.json();
        })
        .then(data => {
            if (data && data.success) {
                addLog(`✅ Адсет "${name}" ${exclude ? 'исключён' : 'возвращён'} в автоконтроль`, 'success');
                Swal.fire('Готово', data.message || `${actionText} выполнено`, 'success');
                // Перезагрузим таблицы, чтобы отразить изменения
                reloadAllTables();
            } else {
                const err = (data && data.error) ? data.error : 'Неизвестная ошибка';
                addLog(`❌ Ошибка: ${err}`, 'error');
                Swal.fire('Ошибка', err, 'error');
            }
        })
        .catch(err => {
            console.error('toggleAdsetExclusion error:', err);
            addLog(`❌ Сетевая/серверная ошибка: ${err.message}`, 'error');
            Swal.fire('Ошибка', err.message || 'Сервер вернул некорректный ответ', 'error');
        })
        .finally(() => {
            if (btn) {
                btn.disabled = false;
                // восстановим оригинальный HTML кнопки — если не знаем, подставим текст
                btn.innerHTML = originalBtnHtml || (exclude ? '<i class="bi bi-slash-circle"></i> Исключить' : '<i class="bi bi-arrow-clockwise"></i> Вернуть');
            }
        });
    });
}

    
    // Периодическая проверка статуса
    setInterval(checkSystemStatus, 30000);
    
    // Стили
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
        
        .log-container { 
            max-height: 400px; 
            overflow-y: auto; 
            font-family: 'Courier New', monospace;
            font-size: 0.85rem;
            background-color: #f8f9fa;
            border-radius: 0.375rem;
            padding: 1rem;
        }
        
        .log-entry { 
            padding: 0.5rem 0; 
            border-bottom: 1px solid #e9ecef;
            line-height: 1.4;
        }
        
        .log-entry:last-child {
            border-bottom: none;
        }
        
        .log-time {
            font-size: 0.75rem;
            margin-right: 0.5rem;
        }
        
        .stats-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 0.5rem;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }
        
        .stat-number {
            font-size: 2rem;
            font-weight: bold;
            margin-bottom: 0.25rem;
        }
        
        .stat-label {
            font-size: 0.875rem;
            opacity: 0.9;
        }
        
        .progress {
            height: 1rem;
            margin-top: 0.5rem;
        }
        
        .control-panel {
            background-color: #f8f9fa;
            border-radius: 0.5rem;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            border: 1px solid #dee2e6;
        }
        
        .interval-control {
            max-width: 200px;
        }
        
        .btn-system {
            min-width: 120px;
            font-weight: 500;
        }
        
        .btn-exclude {
            min-width: 100px;
            font-size: 0.8rem;
        }
        
        @media (max-width: 768px) {
            .btn-system {
                width: 100%;
                margin-bottom: 0.5rem;
            }
            
            .interval-control {
                max-width: 100%;
            }
            
            .btn-exclude {
                min-width: 80px;
                font-size: 0.75rem;
            }
        }
    `;
    document.head.appendChild(style);
});

// Глобальный объект для управления системой
window.AutoControlSystem = {
    start: function() {
        const runBtn = document.getElementById('runAutoControl');
        if (runBtn) runBtn.click();
    },
    
    stop: function() {
        const stopBtn = document.getElementById('stopAutoControl');
        if (stopBtn) stopBtn.click();
    },
    
    getStatus: function() {
        return new Promise((resolve) => {
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
            .then(data => resolve(data))
            .catch(() => resolve({ success: false }));
        });
    },
    
    addLog: function(message, type = 'info') {
        const logContainer = document.getElementById('autoControlLog');
        if (logContainer) {
            const now = new Date();
            const timeString = now.toLocaleTimeString();
            const logEntry = document.createElement('div');
            logEntry.className = `log-entry ${type === 'error' ? 'text-danger' : type === 'success' ? 'text-success' : type === 'warning' ? 'text-warning' : 'text-info'}`;
            logEntry.innerHTML = `<span class="text-muted">[${timeString}]</span> ${message}`;
            logContainer.prepend(logEntry);
        }
    },
    
    excludeAdset: function(adsetId, adsetName) {
        // Вызываем глобальную функцию toggleAdsetExclusion
        if (typeof toggleAdsetExclusion === 'function') {
            toggleAdsetExclusion(adsetId, adsetName, false);
        }
    },
    
    includeAdset: function(adsetId, adsetName) {
        // Вызываем глобальную функцию toggleAdsetExclusion
        if (typeof toggleAdsetExclusion === 'function') {
            toggleAdsetExclusion(adsetId, adsetName, true);
        }
    },
    
    // Новая функция для массового исключения адсетов
    excludeMultipleAdsets: function(adsetIds, adsetNames) {
        if (!adsetIds || !adsetIds.length) {
            Swal.fire('Ошибка!', 'Не выбраны адсеты для исключения', 'error');
            return;
        }
        
        Swal.fire({
            title: 'Исключить несколько адсетов?',
            html: `Будет исключено <strong>${adsetIds.length}</strong> адсетов из автоконтроля<br><br>
                   <small>Адсеты будут пропускаться системой автоконтроля</small>`,
            icon: 'question',
            showCancelButton: true,
            confirmButtonText: 'Исключить',
            cancelButtonText: 'Отмена'
        }).then((result) => {
            if (result.isConfirmed) {
                fetch('/api/adsets/exclude_multiple', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        adset_ids: adsetIds,
                        exclude: true
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const message = `✅ ${adsetIds.length} адсетов исключено из автоконтроля`;
                        this.addLog(message, 'success');
                        Swal.fire('Успех!', message, 'success');
                        
                        // Обновляем таблицу
                        if (window.adsetsTable) {
                            window.adsetsTable.ajax.reload();
                        }
                    } else {
                        Swal.fire('Ошибка!', data.error || 'Не удалось исключить адсеты', 'error');
                    }
                })
                .catch(error => {
                    Swal.fire('Ошибка сети!', 'Не удалось подключиться к серверу', 'error');
                });
            }
        });
    }
};
function toggleAdsetExclusion(adsetId, name, includeFlag = false) {
    const exclude = !Boolean(includeFlag); 
    const actionText = exclude ? 'Исключить' : 'Вернуть';

    fetch('/api/adsets/exclude', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ adset_id: adsetId, exclude: exclude })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            addLog(`✅ Адсет "${name}" ${exclude ? 'исключён' : 'возвращён'} в автоконтроль`, 'success');
            Swal.fire('Успех', data.message, 'success');
            reloadAllTables(); // только таблицы
        } else {
            Swal.fire('Ошибка', data.error || 'Не удалось изменить статус адсета', 'error');
        }
    })
    .catch(err => {
        Swal.fire('Ошибка сети!', err.message, 'error');
    });
}
