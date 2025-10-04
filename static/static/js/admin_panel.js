// admin_panel.js
let limitsChart = null;
let spendChart = null;

document.addEventListener('DOMContentLoaded', function() {
    // Проверяем права доступа при загрузке
    checkAdminAccess();
    
    // Загружаем данные
    loadAccountLimits();
    
    // Автообновление каждые 5 минут
    setInterval(loadAccountLimits, 300000);
});

function checkAdminAccess() {
    fetch('/api/admin/check_access')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.is_admin) {
                document.querySelector('.admin-panel').style.display = 'block';
            } else {
                document.body.innerHTML = `
                    <div class="container mt-5">
                        <div class="alert alert-danger text-center">
                            <h4><i class="bi bi-shield-exclamation"></i> Доступ запрещен</h4>
                            <p>У вас нет прав для просмотра этой страницы</p>
                            <a href="/dashboard" class="btn btn-primary">Вернуться в панель</a>
                        </div>
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Ошибка проверки доступа:', error);
        });
}

function loadAccountLimits() {
    showLoading();
    
    fetch('/api/admin/account_limits')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateStats(data.stats);
                renderLimitsTable(data.accounts);
                updateCharts(data.accounts);
            } else {
                showError('Ошибка загрузки данных', data.error);
            }
        })
        .catch(error => {
            showError('Ошибка сети', error.message);
        })
        .finally(() => {
            hideLoading();
        });
}

function updateStats(stats) {
    document.getElementById('totalAccounts').textContent = stats.total_accounts;
    document.getElementById('activeAccounts').textContent = stats.active_accounts;
    document.getElementById('totalSpend').textContent = `$${stats.total_spend.toFixed(2)}`;
    document.getElementById('limitUsage').textContent = `${stats.limit_usage}%`;
}

function renderLimitsTable(accounts) {
    const tbody = document.querySelector('#limitsTable tbody');
    tbody.innerHTML = '';
    
    accounts.forEach(account => {
        const usagePercent = (account.spend / account.limit) * 100;
        const requestsUsage = (account.requests_today / account.requests_limit) * 100;
        
        const row = `
            <tr>
                <td>
                    <strong>${account.account_id}</strong><br>
                    <small class="text-muted">${account.name || 'N/A'}</small>
                </td>
                <td>
                    <span class="badge ${account.status === 'ACTIVE' ? 'bg-success' : 'bg-secondary'}">
                        ${account.status}
                    </span>
                </td>
                <td>$${account.limit.toFixed(2)}</td>
                <td>$${account.spend.toFixed(2)}</td>
                <td>$${(account.limit - account.spend).toFixed(2)}</td>
                <td>
                    <div class="progress" style="height: 20px;">
                        <div class="progress-bar 
                            ${usagePercent < 50 ? 'bg-success' : usagePercent < 80 ? 'bg-warning' : 'bg-danger'}" 
                            style="width: ${usagePercent}%">
                            ${usagePercent.toFixed(1)}%
                        </div>
                    </div>
                </td>
                <td>${account.requests_today}</td>
                <td>${account.requests_limit}</td>
                <td>
                    <span class="badge ${getLimitStatusClass(requestsUsage)}">
                        ${getLimitStatusText(requestsUsage)}
                    </span>
                </td>
                <td>
                    <button class="btn btn-sm btn-outline-primary" onclick="refreshAccount('${account.account_id}')">
                        <i class="bi bi-arrow-repeat"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-info" onclick="showAccountDetails('${account.account_id}')">
                        <i class="bi bi-info-circle"></i>
                    </button>
                </td>
            </tr>
        `;
        tbody.innerHTML += row;
    });
    
    // Инициализируем DataTable если еще не инициализирована
    if (!$.fn.DataTable.isDataTable('#limitsTable')) {
        $('#limitsTable').DataTable({
            order: [[5, 'desc']],
            language: {
                url: '//cdn.datatables.net/plug-ins/1.11.5/i18n/ru.json'
            },
            pageLength: 25
        });
    }
}

function getLimitStatusClass(usage) {
    if (usage < 50) return 'bg-success';
    if (usage < 80) return 'bg-warning';
    return 'bg-danger';
}

function getLimitStatusText(usage) {
    if (usage < 50) return 'Норма';
    if (usage < 80) return 'Внимание';
    return 'Критично';
}

function updateCharts(accounts) {
    updateLimitsChart(accounts);
    updateSpendChart(accounts);
}

function updateLimitsChart(accounts) {
    const ctx = document.getElementById('limitsChart').getContext('2d');
    
    if (limitsChart) {
        limitsChart.destroy();
    }
    
    const labels = accounts.map(acc => acc.account_id);
    const usageData = accounts.map(acc => (acc.spend / acc.limit) * 100);
    
    limitsChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Использование лимита (%)',
                data: usageData,
                backgroundColor: usageData.map(usage => 
                    usage < 50 ? '#198754' : usage < 80 ? '#fd7e14' : '#dc3545'
                ),
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    title: {
                        display: true,
                        text: 'Процент использования'
                    }
                }
            }
        }
    });
}

function updateSpendChart(accounts) {
    const ctx = document.getElementById('spendChart').getContext('2d');
    
    if (spendChart) {
        spendChart.destroy();
    }
    
    const labels = accounts.map(acc => acc.account_id);
    const spendData = accounts.map(acc => acc.spend);
    
    spendChart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: labels,
            datasets: [{
                data: spendData,
                backgroundColor: [
                    '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0',
                    '#9966FF', '#FF9F40', '#FF6384', '#C9CBCF'
                ]
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'right',
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `$${context.raw.toFixed(2)}`;
                        }
                    }
                }
            }
        }
    });
}

function refreshAccount(accountId) {
    fetch(`/api/admin/refresh_account/${accountId}`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Данные аккаунта обновлены', 'success');
            loadAccountLimits();
        } else {
            showError('Ошибка обновления', data.error);
        }
    })
    .catch(error => {
        showError('Ошибка сети', error.message);
    });
}

function showAccountDetails(accountId) {
    fetch(`/api/admin/account_details/${accountId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Показываем модальное окно с деталями
                showAccountModal(data.account);
            } else {
                showError('Ошибка загрузки', data.error);
            }
        })
        .catch(error => {
            showError('Ошибка сети', error.message);
        });
}

function showAccountModal(account) {
    // Создаем и показываем модальное окно с детальной информацией
    const modalHtml = `
        <div class="modal fade" id="accountModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Детали аккаунта: ${account.account_id}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="row">
                            <div class="col-md-6">
                                <h6>Основная информация</h6>
                                <p><strong>Название:</strong> ${account.name || 'N/A'}</p>
                                <p><strong>Статус:</strong> <span class="badge ${account.status === 'ACTIVE' ? 'bg-success' : 'bg-secondary'}">${account.status}</span></p>
                                <p><strong>Баланс:</strong> $${account.balance?.toFixed(2) || 'N/A'}</p>
                            </div>
                            <div class="col-md-6">
                                <h6>Лимиты</h6>
                                <p><strong>Дневной лимит:</strong> $${account.limit?.toFixed(2) || 'N/A'}</p>
                                <p><strong>Израсходовано:</strong> $${account.spend?.toFixed(2) || 'N/A'}</p>
                                <p><strong>Остаток:</strong> $${(account.limit - account.spend)?.toFixed(2) || 'N/A'}</p>
                            </div>
                        </div>
                        <hr>
                        <h6>Статистика запросов</h6>
                        <div class="row">
                            <div class="col-md-6">
                                <p><strong>Запросов сегодня:</strong> ${account.requests_today || 0}</p>
                                <p><strong>Лимит запросов:</strong> ${account.requests_limit || 0}</p>
                            </div>
                            <div class="col-md-6">
                                <div class="progress" style="height: 20px;">
                                    <div class="progress-bar ${getLimitStatusClass((account.requests_today / account.requests_limit) * 100)}" 
                                         style="width: ${(account.requests_today / account.requests_limit) * 100}%">
                                        ${((account.requests_today / account.requests_limit) * 100).toFixed(1)}%
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Закрыть</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Добавляем модальное окно в DOM и показываем
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    const modal = new bootstrap.Modal(document.getElementById('accountModal'));
    modal.show();
    
    // Удаляем модальное окно после закрытия
    document.getElementById('accountModal').addEventListener('hidden.bs.modal', function() {
        this.remove();
    });
}

function showLoading() {
    // Показываем индикатор загрузки
    const refreshBtn = document.querySelector('button[onclick="loadAccountLimits()"]');
    if (refreshBtn) {
        refreshBtn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Загрузка...';
        refreshBtn.disabled = true;
    }
}

function hideLoading() {
    // Скрываем индикатор загрузки
    const refreshBtn = document.querySelector('button[onclick="loadAccountLimits()"]');
    if (refreshBtn) {
        refreshBtn.innerHTML = '<i class="bi bi-arrow-repeat"></i> Обновить';
        refreshBtn.disabled = false;
    }
}

function showError(title, message) {
    console.error(title, message);
    // Показываем уведомление об ошибке
    const alert = document.createElement('div');
    alert.className = 'alert alert-danger alert-dismissible fade show position-fixed';
    alert.style.top = '20px';
    alert.style.right = '20px';
    alert.style.zIndex = '1060';
    alert.innerHTML = `
        <strong>${title}</strong><br>${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    document.body.appendChild(alert);
    
    // Автоматическое скрытие через 5 секунд
    setTimeout(() => {
        if (alert.parentNode) {
            alert.remove();
        }
    }, 5000);
}

function showNotification(message, type = 'success') {
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    alert.style.top = '20px';
    alert.style.right = '20px';
    alert.style.zIndex = '1060';
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    document.body.appendChild(alert);
    
    setTimeout(() => {
        if (alert.parentNode) {
            alert.remove();
        }
    }, 3000);
}

// Стиль для анимации спиннера
const style = document.createElement('style');
style.textContent = `
    .spin { animation: spin 1s linear infinite; }
    @keyframes spin { 100% { transform: rotate(360deg); } }
    .progress-bar { min-width: 30px; }
`;
document.head.appendChild(style);