
document.addEventListener('DOMContentLoaded', function() {
    loadKeitaroCampaigns()

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

 
    setTimeout(checkAutoRefreshStatus, 1000);
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
                
          
                document.getElementById('telegramBotToken').value = config.telegram_bot_token || '';
                document.getElementById('telegramChatId').value = config.telegram_chat_id || '';
                
              
                document.getElementById('keitaroApiKey').value = config.keitaro_api_key || '';
                document.getElementById('keitaroDomain').value = config.keitaro_domain || 'uniaffnu.com';
                document.getElementById('keitaroRangeDays').value = config.keitaro_range_days || 1;
                document.getElementById('autoHeadlineOptimization').checked = config.auto_headline_optimization || false;
                document.getElementById('headlineOptimizationInterval').value = config.headline_optimization_interval || 60;
                document.getElementById('minRoiThreshold').value = config.min_roi_threshold || 20;
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
        auto_refresh_interval: parseInt(document.getElementById('autoRefreshInterval').value) || 5,
        telegram_bot_token: document.getElementById('telegramBotToken').value,
        telegram_chat_id: document.getElementById('telegramChatId').value,
        keitaro_api_key: document.getElementById('keitaroApiKey').value,
        keitaro_domain: document.getElementById('keitaroDomain').value,
        keitaro_range_days: parseInt(document.getElementById('keitaroRangeDays').value) || 1,
        auto_headline_optimization: document.getElementById('autoHeadlineOptimization').checked,
        headline_optimization_interval: parseInt(document.getElementById('headlineOptimizationInterval').value) || 60,
        min_roi_threshold: parseInt(document.getElementById('minRoiThreshold').value) || 20
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
    const interval = parseInt(document.getElementById('autoRefreshInterval').value) || 5;
    
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
            const interval = parseInt(document.getElementById('autoRefreshInterval').value) || 5;
            
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
        const interval = parseInt(document.getElementById('autoRefreshInterval').value) || 5;
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
    interval: 5,
    nextRefresh: null
};


function calculateNextRefreshTime(intervalMinutes) {
    const now = new Date();
    const nextRefresh = new Date(now.getTime() + intervalMinutes * 60000);
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

document.getElementById('runHeadlineOptimization')?.addEventListener('click', runHeadlineOptimization);
document.getElementById('headlineOptimizationStatus')?.addEventListener('click', checkHeadlineOptimizationStatus);

function runHeadlineOptimization() {
    const btn = document.getElementById('runHeadlineOptimization');
    const originalText = btn.innerHTML;
    
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Оптимизация...';
    
    fetch('/api/headline_optimization/run', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            campaign_id: 'all' 
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire({
                icon: 'success',
                title: 'Успех!',
                text: data.message,
                timer: 3000,
                showConfirmButton: false
            });
      
            setTimeout(checkHeadlineOptimizationStatus, 1000);
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
            text: 'Не удалось запустить оптимизацию',
            confirmButtonText: 'OK'
        });
    })
    .finally(() => {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-lightning-fill"></i> Запустить оптимизацию';
    });
}
function loadKeitaroCampaigns() {
    fetch('/api/keitaro/campaigns')
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const select = document.getElementById('campaignSelect');
         
            while (select.options.length > 1) {
                select.remove(1);
            }
            
         
            data.campaigns.forEach(campaign => {
                const option = document.createElement('option');
                option.value = campaign.id;
                option.textContent = `${campaign.name} (ID: ${campaign.id})`;
                select.appendChild(option);
            });
        }
    })
    .catch(error => {
        console.error('Ошибка загрузки кампаний:', error);
    });
}


function checkHeadlineOptimizationStatus() {
    const btn = document.getElementById('headlineOptimizationStatus');
    const originalText = btn.innerHTML;
    
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Проверка...';
    
    
    const campaignSelect = document.getElementById('campaignSelect');
    const campaignId = campaignSelect ? campaignSelect.value : 'all';
    
    fetch(`/api/headline_optimization/status?campaign_id=${campaignId}`)
    .then(response => response.json())
    .then(data => {
        const resultsContainer = document.getElementById('headlineOptimizationResults');
        
        if (data.success) {
            if (data.streams && data.streams.length > 0) {
                let html = `<h6>Статус потоков: ${data.campaign_id === 'all' ? 'Все кампании' : 'Кампания ' + data.campaign_id}</h6>`;
                html += `<p class="small">Всего потоков: ${data.total_streams}, Активных: ${data.active_streams}</p>`;
                html += '<div class="table-responsive"><table class="table table-sm table-striped stream-table">';
                html += '<thead><tr><th>Кампания</th><th>Поток</th><th>Вес</th><th>Конв.</th><th>Расход</th><th>Доход</th><th>ROI</th><th>Статус</th><th>Действия</th></tr></thead><tbody>';
                
                data.streams.forEach(stream => {
                    const isActive = stream.is_active ? '✅' : '❌';
                    const roiClass = stream.roi >= 0 ? 'text-success' : 'text-danger';
                    const roiIcon = stream.roi >= 0 ? '📈' : '📉';
                    
                    html += `<tr>
                        <td>${stream.campaign_name || 'N/A'}</td>
                        <td>${stream.name}</td>
                        <td>${stream.weight}%</td>
                        <td>${stream.conversions}</td>
                        <td>$${stream.cost.toFixed(2)}</td>
                        <td>$${stream.revenue.toFixed(2)}</td>
                        <td class="${roiClass} fw-bold">${roiIcon} ${stream.roi.toFixed(1)}%</td>
                        <td>${isActive}</td>
                        <td>
                            <div class="btn-group btn-group-sm">
                                <input type="number" class="form-control form-control-sm weight-control" 
                                    value="${stream.weight}" min="0" max="100" 
                                    onchange="updateStreamWeight(${stream.id}, this.value)"
                                    style="width: 60px;">
                            </div>
                        </td>
                    </tr>`;
                });
                
                html += '</tbody></table></div>';
                resultsContainer.innerHTML = html;
            } else {
                resultsContainer.innerHTML = '<div class="alert alert-info">Нет данных о потоках</div>';
            }
        } else {
            resultsContainer.innerHTML = `<div class="alert alert-danger">Ошибка: ${data.error}</div>`;
        }
    })
    .catch(error => {
        document.getElementById('headlineOptimizationResults').innerHTML = 
            '<div class="alert alert-danger">Ошибка получения статуса</div>';
    })
    .finally(() => {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-info-circle"></i> Статус';
    });
}
function checkHeadlineOptimizationStatus() {
    const btn = document.getElementById('headlineOptimizationStatus');
    const originalText = btn.innerHTML;
    
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Проверка...';
    

    const campaignSelect = document.getElementById('campaignSelect');
    const campaignId = campaignSelect ? campaignSelect.value : 'all';
    
    fetch(`/api/headline_optimization/status?campaign_id=${campaignId}`)
    .then(response => response.json())
    .then(data => {
        const resultsContainer = document.getElementById('headlineOptimizationResults');
        
        if (data.success) {
            if (data.streams && data.streams.length > 0) {
                let html = `<h6>Статус потоков: ${data.campaign_id === 'all' ? 'Все кампании' : 'Кампания ' + data.campaign_id}</h6>`;
                html += '<div class="table-responsive"><table class="table table-sm table-striped stream-table">';
                html += '<thead><tr><th>Кампания</th><th>Поток</th><th>Вес</th><th>Конверсии</th><th>Расход</th><th>CPA</th><th>ROI</th><th>Действия</th></tr></thead><tbody>';
                
                data.streams.forEach(stream => {
                    const isActive = stream.is_active ? '✅' : '❌';
                    html += `<tr>
                        <td>${stream.campaign_name || 'N/A'}</td>
                        <td>${stream.name}</td>
                        <td>${stream.weight}%</td>
                        <td>${stream.conversions}</td>
                        <td>$${stream.cost.toFixed(2)}</td>
                        <td>$${stream.cpa.toFixed(2)}</td>
                        <td class="${stream.roi >= 0 ? 'text-success' : 'text-danger'} fw-bold">${stream.roi.toFixed(1)}%</td>
                        <td>
                            <div class="btn-group btn-group-sm">
                                <input type="number" class="form-control form-control-sm weight-control" 
                                    value="${stream.weight}" min="0" max="100" 
                                    onchange="updateStreamWeight(${stream.id}, this.value)"
                                    style="width: 60px;">
                            </div>
                        </td>
                    </tr>`;
                });
                
                html += '</tbody></table></div>';
                resultsContainer.innerHTML = html;
            } else {
                resultsContainer.innerHTML = '<div class="alert alert-info">Нет данных о потоках</div>';
            }
        } else {
            resultsContainer.innerHTML = `<div class="alert alert-danger">Ошибка: ${data.error}</div>`;
        }
    })
    .catch(error => {
        document.getElementById('headlineOptimizationResults').innerHTML = 
            '<div class="alert alert-danger">Ошибка получения статуса</div>';
    })
    .finally(() => {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-info-circle"></i> Статус';
    });
}


function updateStreamWeight(streamId, newWeight) {
    fetch('/api/headline_optimization/update_weight', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            stream_id: streamId,
            new_weight: newWeight
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire('Успех!', data.message, 'success');
            checkHeadlineOptimizationStatus(); 
        } else {
            Swal.fire('Ошибка!', data.error, 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка сети!', 'Не удалось обновить вес', 'error');
    });
}


setInterval(checkHeadlineOptimizationStatus, 30000);