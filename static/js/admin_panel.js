
document.addEventListener('DOMContentLoaded', function() {
   
    initAdminPanel();
});
function loadInitialData() {
    console.log('Loading initial data...');
    
   
    loadData();
    

    loadUsers();
    

    loadTokensStats();
    
 
    initTooltips();
    
 
    loadDebugInfo();
}
function initAdminPanel() {
    console.log('Initializing admin panel...');
    
    try {
       
        if (typeof loadData === 'undefined' || 
            typeof loadUsers === 'undefined' || 
            typeof loadTokensStats === 'undefined') {
            throw new Error('Не все функции загружены');
        }
        
     
        checkAdminAccess();
        
      
        setupEventListeners();
        
      
        loadInitialData();
        
        console.log('Admin panel initialized successfully');
    } catch (error) {
        console.error('Error initializing admin panel:', error);
        showError('Ошибка инициализации панели: ' + error.message);
        
        
        initBasicFunctionality();
    }
}

let allAccounts = [];
let allUsers = [];
let tokensStats = [];

function checkAdminAccess() {
    fetch('/api/admin/check_access')
        .then(response => {
            if (!response.ok) {
                throw new Error('Ошибка сети');
            }
            return response.json();
        })
        .then(data => {
            if (!data.success || !data.is_admin) {
                showError('Доступ запрещен. Недостаточно прав.');
                setTimeout(() => {
                    window.location.href = '/dashboard';
                }, 2000);
            }
        })
        .catch(error => {
            console.error('Ошибка проверки доступа:', error);
            showError('Ошибка подключения к серверу');
        });
}

function loadUsers() {
    fetch('/api/admin/users')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                allUsers = data.users;
                updateUserFilter();
            }
        })
        .catch(error => {
            console.error('Ошибка загрузки пользователей:', error);
        });
}

function loadTokensStats() {
    fetch('/api/admin/reserve_tokens_stats')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                tokensStats = data.stats;
                renderTokensTable();
            }
        })
        .catch(error => {
            console.error('Ошибка загрузки статистики токенов:', error);
        });
}

function initTooltips() {
   
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

function loadDebugInfo() {
    const debugInfo = document.getElementById('debugInfo');
    if (!debugInfo) return;
    
    debugInfo.style.display = 'block';
    debugInfo.innerHTML = '<div class="spinner-border spinner-border-sm"></div> Загрузка отладочной информации...';

    fetch('/api/admin/debug_accounts')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                let html = `
                    <h6>Статистика системы:</h6>
                    <ul class="list-group">
                        <li class="list-group-item">Пользователей: ${data.users_count}</li>
                        <li class="list-group-item">Всего аккаунтов в БД: ${data.raw_accounts_count}</li>
                        <li class="list-group-item">Валидных аккаунтов: ${data.valid_accounts_count}</li>
                    </ul>
                    
                    <h6 class="mt-3">Первые 10 аккаунтов из БД:</h6>
                    <div class="table-responsive">
                        <table class="table table-sm">
                            <thead>
                                <tr>
                                    <th>User ID</th>
                                    <th>Username</th>
                                    <th>Account ID</th>
                                    <th>Token</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                (data.raw_accounts || []).slice(0, 10).forEach(acc => {
                    html += `
                        <tr>
                            <td>${acc.user_id}</td>
                            <td>${escapeHtml(acc.username)}</td>
                            <td>${escapeHtml(acc.account_id)}</td>
                            <td class="text-truncate" style="max-width: 100px;">${escapeHtml(acc.token || '')}</td>
                        </tr>
                    `;
                });

                html += `
                            </tbody>
                        </table>
                    </div>
                `;

                debugInfo.innerHTML = html;
            } else {
                debugInfo.innerHTML = `<div class="alert alert-danger">Ошибка: ${data.error}</div>`;
            }
        })
        .catch(error => {
            debugInfo.innerHTML = `<div class="alert alert-danger">Ошибка сети: ${error.message}</div>`;
        });
}
function loadData() {
    console.log('Loading data...');
    
  
    const tbody = document.getElementById('accountsTableBody');
    if (tbody) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center"><div class="spinner-border"></div> Загрузка данных...</td></tr>';
    }

    fetch('/api/admin/all_accounts_limits')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                console.log('Data loaded successfully:', data);
                allAccounts = normalizeAccountData(data.accounts || []);
                
              
                allAccounts = allAccounts.map(account => {
                    
                    ['status', 'name', 'account_id', 'username'].forEach(field => {
                        if (account[field] === undefined || account[field] === null) {
                            account[field] = 'UNKNOWN';
                        } else if (typeof account[field] !== 'string') {
                            account[field] = String(account[field]);
                        }
                    });
                    
                 
                    ['spend', 'balance', 'spend_cap', 'daily_limit', 'requests_today', 'requests_limit', 'requests_usage_percent'].forEach(field => {
                        if (account[field] === undefined || account[field] === null) {
                            account[field] = 0;
                        } else if (typeof account[field] !== 'number') {
                            account[field] = parseFloat(account[field]) || 0;
                        }
                    });
                    
                    return account;
                });
                
                updateStats(normalizeStats(data.stats || {}));

                renderAccountsTable(allAccounts);
                
            } else {
                showError('Ошибка загрузки данных: ' + (data.error || 'Неизвестная ошибка'));
            }
        })
        .catch(error => {
            console.error('Load error:', error);
            showError('Ошибка загрузки: ' + error.message);
            
       
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" class="text-center">
                            <div class="alert alert-warning">
                                <i class="fas fa-exclamation-triangle"></i>
                                Ошибка загрузки данных
                                <br>
                                <button class="btn btn-sm btn-primary mt-2" onclick="loadData()">
                                    <i class="fas fa-redo"></i> Попробовать снова
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            }
        });
}
function normalizeAccountData(accounts) {
    if (!accounts || !Array.isArray(accounts)) return [];
    
    return accounts.map(account => {
       
        const normalized = {...account};
        
       
        if (normalized.status === undefined || normalized.status === null) {
            normalized.status = 'UNKNOWN';
        } else if (typeof normalized.status !== 'string') {
            normalized.status = String(normalized.status);
        }
        
 
        ['name', 'account_id', 'username', 'error'].forEach(field => {
            if (normalized[field] === undefined || normalized[field] === null) {
                normalized[field] = '';
            } else if (typeof normalized[field] !== 'string') {
                normalized[field] = String(normalized[field]);
            }
        });
        
    
        ['spend', 'balance', 'spend_cap', 'daily_limit', 'requests_today', 'requests_limit', 'requests_usage_percent'].forEach(field => {
            if (normalized[field] === undefined || normalized[field] === null) {
                normalized[field] = 0;
            } else if (typeof normalized[field] !== 'number') {
                normalized[field] = parseFloat(normalized[field]) || 0;
            }
        });
        
        return normalized;
    });
}
function showInfo(message) {
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-info alert-dismissible fade show';
    alertDiv.innerHTML = `
        <i class="fas fa-info-circle"></i> ${escapeHtml(message)}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.querySelector('.container');
    if (container) {
        container.insertBefore(alertDiv, container.firstChild);
    }
}

function formatCurrency(amount) {
    if (amount === undefined || amount === null) return '$0.00';
    
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(amount);
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
function loadTokensStats() {
    fetch('/api/admin/reserve_tokens_stats')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                tokensStats = data.stats;
                renderTokensTable();
            }
        })
        .catch(error => {
            console.error('Ошибка загрузки статистики токенов:', error);
        });
}
function normalizeStats(stats) {
    return {
        totalAccounts: stats.total_accounts ?? stats.totalAccounts ?? 0,
        activeAccounts: stats.active_accounts ?? stats.activeAccounts ?? 0,
        disabledAccounts: stats.disabled_accounts ?? stats.disabledAccounts ?? 0,
        errorAccounts: stats.error_accounts ?? stats.errorAccounts ?? 0,
        totalSpend: stats.total_spend ?? stats.totalSpend ?? 0,
        totalBalance: stats.total_balance ?? stats.totalBalance ?? 0,
        totalLimit: stats.total_limit ?? stats.totalLimit ?? 0,
        totalRequests: stats.total_requests ?? stats.totalRequests ?? 0,
    };
}

function updateStats(stats) {
    const elements = {
        'totalAccounts': document.getElementById('totalAccounts'),
        'activeAccounts': document.getElementById('activeAccounts'),
        'errorAccounts': document.getElementById('errorAccounts'),
        'totalSpend': document.getElementById('totalSpend'),
        'totalBalance': document.getElementById('totalBalance'),
        'totalLimit': document.getElementById('totalLimit'),
        'disabledAccounts': document.getElementById('disabledAccounts'),
        'totalRequests': document.getElementById('totalRequests')
    };

    // Создаем недостающие элементы статистики
    createMissingStatsElements(stats);

    // Обновляем значения
    for (const [key, element] of Object.entries(elements)) {
        if (element && stats[key] !== undefined && stats[key] !== null) {
            if (key.includes('Spend') || key.includes('Balance') || key.includes('Limit')) {
                element.textContent = formatCurrency(stats[key]);
            } else {
                element.textContent = stats[key].toLocaleString();
            }
        } else if (element) {
            if (key.includes('Spend') || key.includes('Balance') || key.includes('Limit')) {
                element.textContent = formatCurrency(0);
            } else {
                element.textContent = '0';
            }
        }
    }
}

function createMissingStatsElements(stats) {
    const statsContainer = document.getElementById('statsSection');
    if (!statsContainer) return;

    const statsConfig = [
        { 
            id: 'totalBalance', 
            title: 'Тотал баланс', 
            icon: 'fa-wallet', 
            bg: 'primary', 
            value: stats.totalBalance,
            formatter: 'currency'
        },
        { 
            id: 'totalLimit', 
            title: 'Общий лимит', 
            icon: 'fa-credit-card', 
            bg: 'dark', 
            value: stats.totalLimit,
            formatter: 'currency'
        },
        { 
            id: 'disabledAccounts', 
            title: 'Отключенных', 
            icon: 'fa-pause-circle', 
            bg: 'danger', 
            value: stats.disabledAccounts,
            formatter: 'number'
        },
        { 
            id: 'totalRequests', 
            title: 'Запросов API', 
            icon: 'fa-server', 
            bg: 'info', 
            value: stats.totalRequests,
            formatter: 'number'
        }
    ];

    statsConfig.forEach(stat => {
        let element = document.getElementById(stat.id);
        
        // Если элемента нет - создаем его
        if (!element) {
            const col = document.createElement('div');
            col.className = 'col-md-3 mb-3';
            col.innerHTML = `
                <div class="card stat-card bg-${stat.bg} text-white">
                    <div class="card-body text-center">
                        <h5><i class="fas ${stat.icon}"></i> ${stat.title}</h5>
                        <h3 id="${stat.id}">${stat.formatter === 'currency' ? formatCurrency(stat.value || 0) : (stat.value || 0).toLocaleString()}</h3>
                    </div>
                </div>
            `;
            statsContainer.appendChild(col);
            
            // Находим созданный элемент
            element = document.getElementById(stat.id);
        }
        
        // Обновляем значение
        if (element) {
            if (stat.formatter === 'currency') {
                element.textContent = formatCurrency(stat.value || 0);
            } else {
                element.textContent = (stat.value || 0).toLocaleString();
            }
        }
    });
}
function updateTotalBalance(stats) {
    // Создаем элемент если его нет
    let totalBalanceElement = document.getElementById('totalBalance');
    let totalBalanceCard = document.getElementById('totalBalanceCard');
    
    if (!totalBalanceCard) {
        const statsContainer = document.getElementById('statsSection');
        if (statsContainer) {
            const col = document.createElement('div');
            col.className = 'col-md-3 mb-3';
            col.innerHTML = `
                <div class="card stat-card bg-primary text-white" id="totalBalanceCard">
                    <div class="card-body">
                        <h5><i class="fas fa-wallet"></i> Тотал баланс</h5>
                        <h3 id="totalBalance">${formatCurrency(stats.totalBalance || 0)}</h3>
                    </div>
                </div>
            `;
            statsContainer.appendChild(col);
        }
    } else if (totalBalanceElement) {
        totalBalanceElement.textContent = formatCurrency(stats.totalBalance || 0);
    }
}

function createMissingStatsElements(stats) {
    const statsContainer = document.getElementById('statsSection');
    if (!statsContainer) return;

    const statsToCreate = [
        { id: 'totalBalance', title: 'Общий баланс', icon: 'fa-wallet', bg: 'secondary', value: stats.totalBalance },
        { id: 'totalLimit', title: 'Общий лимит', icon: 'fa-credit-card', bg: 'dark', value: stats.totalLimit },
        { id: 'disabledAccounts', title: 'Отключенных', icon: 'fa-pause-circle', bg: 'danger', value: stats.disabledAccounts },
        { id: 'totalRequests', title: 'Запросов API', icon: 'fa-server', bg: 'info', value: stats.totalRequests }
    ];

    statsToCreate.forEach(stat => {
        if (stat.value !== undefined && !document.getElementById(stat.id)) {
            const col = document.createElement('div');
            col.className = 'col-md-3 mb-3';
            col.innerHTML = `
                <div class="card stat-card bg-${stat.bg} text-white" id="${stat.id}Card">
                    <div class="card-body">
                        <h5><i class="fas ${stat.icon}"></i> ${stat.title}</h5>
                        <h3 id="${stat.id}">${stat.id.includes('Spend') || stat.id.includes('Balance') || stat.id.includes('Limit') ? 
                            formatCurrency(stat.value) : stat.value.toLocaleString()}</h3>
                    </div>
                </div>
            `;
            statsContainer.appendChild(col);
        }
    });
}

function updateUserFilter() {
    const userFilter = document.getElementById('userFilter');
    if (!userFilter) return;
    
    userFilter.innerHTML = '<option value="">Все пользователи</option>';
    
    (allUsers || []).forEach(user => {
        const option = document.createElement('option');
        option.value = user.id;
        option.textContent = `${user.username} (ID: ${user.id})`;
        userFilter.appendChild(option);
    });
}
function renderAccountsTable(accounts) {
    const tbody = document.getElementById('accountsTableBody');
    if (!tbody) {
        console.error('Table body not found');
        return;
    }
    
    if (!accounts || accounts.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="text-center">
                    <div class="alert alert-info">
                        <i class="fas fa-info-circle"></i>
                        Нет данных об аккаунтах для отображения
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    let html = '';
    accounts.forEach(account => {
       
        const status = account.status || 'UNKNOWN';
        const statusClass = getStatusClass(status);
        const requestsPercent = account.requests_usage_percent || 0;
        const requestsColor = getUsageColor(requestsPercent);
        const hasError = account.error || 
                        status === 'ERROR' || 
                        status === 'NETWORK_ERROR' || 
                        status === 'API_ERROR' ||
                        status === 'INVALID_DATA';
        
        
        const spend = account.spend !== undefined ? account.spend : 0;
        const balance = account.balance !== undefined ? account.balance : 0;
        const spendCap = account.spend_cap !== undefined ? account.spend_cap : 0;
        const dailyLimit = account.daily_limit !== undefined ? account.daily_limit : 0;
        
        html += `
            <tr class="${statusClass}">
                <td>
                    <strong>${escapeHtml(account.username)}</strong>
                    <br>
                    <small class="text-muted">ID: ${account.user_id}</small>
                </td>
                <td>
                    <div class="d-flex flex-column">
                        <span class="fw-bold">${escapeHtml(account.name)}</span>
                        <small class="text-muted">${account.account_id}</small>
                        ${hasError ? `
                        <small class="text-danger mt-1">
                            <i class="fas fa-exclamation-triangle"></i>
                            ${escapeHtml(account.error || status)}
                        </small>
                        ` : ''}
                    </div>
                </td>
                <td>
                    <span class="badge ${getStatusBadgeClass(status)}">
                        <i class="${getStatusIcon(status)}"></i>
                        ${status}
                    </span>
                </td>
                <td class="text-nowrap">${formatCurrency(balance)}</td>
                <td class="text-nowrap">${formatCurrency(spend)}</td>
                <td class="text-nowrap">
                    ${formatCurrency(spendCap)}
                    ${dailyLimit > 0 ? `<br><small class="text-muted">Дневной: ${formatCurrency(dailyLimit)}</small>` : ''}
                </td>
                <td>
                    <div class="d-flex align-items-center">
                        <div class="progress flex-grow-1 me-2" style="height: 8px;">
                            <div class="progress-bar bg-${requestsColor}" 
                                 style="width: ${Math.min(requestsPercent, 100)}%"
                                 title="${requestsPercent}% использовано">
                            </div>
                        </div>
                        <small class="text-nowrap">${account.requests_today}/${account.requests_limit}</small>
                    </div>
                    <small class="text-muted">${requestsPercent}%</small>
                </td>
                <td>
                    <div class="btn-group-vertical">
                        <button class="btn btn-sm btn-outline-primary" 
                                onclick="viewAccountDetails('${escapeHtml(account.account_id)}')"
                                title="Детали аккаунта">
                            <i class="fas fa-info-circle"></i>
                        </button>
                        ${hasError ? `
                        <button class="btn btn-sm btn-outline-danger mt-1" 
                                onclick="testAccountToken('${escapeHtml(account.account_id)}')"
                                title="Тестировать токен">
                            <i class="fas fa-bug"></i>
                        </button>
                        ` : ''}
                        <button class="btn btn-sm btn-outline-secondary mt-1" 
                                onclick="refreshAccount('${escapeHtml(account.account_id)}')"
                                title="Обновить данные">
                            <i class="fas fa-sync-alt"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = html;
}

function loadDebugInfo() {
    const debugInfo = document.getElementById('debugInfo');
    debugInfo.style.display = 'block';
    debugInfo.innerHTML = '<div class="spinner-border spinner-border-sm"></div> Загрузка отладочной информации...';

    fetch('/api/admin/debug_accounts')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                let html = `
                    <h6>Статистика системы:</h6>
                    <ul class="list-group">
                        <li class="list-group-item">Пользователей: ${data.users_count}</li>
                        <li class="list-group-item">Всего аккаунтов в БД: ${data.raw_accounts_count}</li>
                        <li class="list-group-item">Валидных аккаунтов: ${data.valid_accounts_count}</li>
                    </ul>
                    
                    <h6 class="mt-3">Первые 10 аккаунтов из БД:</h6>
                    <div class="table-responsive">
                        <table class="table table-sm">
                            <thead>
                                <tr>
                                    <th>User ID</th>
                                    <th>Username</th>
                                    <th>Account ID</th>
                                    <th>Token</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                data.raw_accounts.forEach(acc => {
                    html += `
                        <tr>
                            <td>${acc.user_id}</td>
                            <td>${escapeHtml(acc.username)}</td>
                            <td>${escapeHtml(acc.account_id)}</td>
                            <td class="text-truncate" style="max-width: 100px;">${escapeHtml(acc.token)}</td>
                        </tr>
                    `;
                });

                html += `
                            </tbody>
                        </table>
                    </div>
                `;

                debugInfo.innerHTML = html;
            } else {
                debugInfo.innerHTML = `<div class="alert alert-danger">Ошибка: ${data.error}</div>`;
            }
        })
        .catch(error => {
            debugInfo.innerHTML = `<div class="alert alert-danger">Ошибка сети: ${error.message}</div>`;
        });
}

function checkDatabase() {
    fetch('/api/admin/debug_accounts')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log('Отладочная информация:', data);
                if (data.raw_accounts_count === 0) {
                    showError('В базе данных нет аккаунтов! Проверьте, что пользователи добавили кампании.');
                } else if (data.valid_accounts_count === 0) {
                    showError('Аккаунты есть в БД, но все имеют ошибки. Проверьте токены.');
                }
            }
        });
}


setTimeout(checkDatabase, 2000);
function renderTokensTable() {
    const tbody = document.getElementById('tokensTableBody');
    if (!tbody) return;
    
    if (!tokensStats || tokensStats.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center">Нет данных о резервных токенах</td></tr>';
        return;
    }

    let html = '';
    tokensStats.forEach(stat => {
        html += `
            <tr>
                <td>
                    <strong>${escapeHtml(stat.username)}</strong>
                    <br>
                    <small class="text-muted">ID: ${stat.user_id}</small>
                </td>
                <td>
                    <span class="badge bg-info fs-6">${stat.total_tokens}</span>
                </td>
                <td>
                    <span class="badge bg-success fs-6">${stat.kings_count}</span>
                </td>
                <td>
                    <div class="d-flex flex-wrap gap-1">
                        ${(stat.kings || []).map(king => `
                            <span class="badge bg-secondary">${escapeHtml(king)}</span>
                        `).join('')}
                        ${!stat.kings || stat.kings.length === 0 ? '<span class="text-muted">Нет данных</span>' : ''}
                    </div>
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = html;
}
function applyFilters() {
    const searchText = document.getElementById('searchInput').value.toLowerCase();
    const statusFilter = document.getElementById('statusFilter').value;
    const userFilter = document.getElementById('userFilter').value;

    let filteredAccounts = allAccounts.filter(account => {
        const matchesSearch = account.name.toLowerCase().includes(searchText) ||
                            account.account_id.toLowerCase().includes(searchText) ||
                            account.username.toLowerCase().includes(searchText) ||
                            (account.error && account.error.toLowerCase().includes(searchText));
        const matchesStatus = !statusFilter || 
                            account.status === statusFilter ||
                            (statusFilter === 'ERROR' && account.error) ||
                            (statusFilter === 'ACTIVE' && account.status === 'ACTIVE' && !account.error);
        const matchesUser = !userFilter || account.user_id.toString() === userFilter;

        return matchesSearch && matchesStatus && matchesUser;
    });

    renderAccountsTable(filteredAccounts);
    

    showFilterCount(filteredAccounts.length);
}

function showFilterCount(count) {
   
    let countElement = document.getElementById('filterCount');
    if (!countElement) {
        countElement = document.createElement('div');
        countElement.id = 'filterCount';
        countElement.className = 'text-muted mt-2';
        document.querySelector('.card-header').appendChild(countElement);
    }
    
    countElement.textContent = `Показано: ${count} из ${allAccounts.length} аккаунтов`;
}

function viewAccountDetails(accountId) {
    const account = allAccounts.find(acc => acc.account_id === accountId);
    if (!account) return;

   
    const modalHtml = `
        <div class="modal fade" id="accountModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="fas fa-info-circle"></i>
                            Детали аккаунта: ${escapeHtml(account.name)}
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="row">
                            <div class="col-md-6">
                                <h6><i class="fas fa-user"></i> Основная информация</h6>
                                <table class="table table-sm">
                                    <tr><th>ID аккаунта:</th><td>${account.account_id}</td></tr>
                                    <tr><th>Пользователь:</th><td>${escapeHtml(account.username)} (ID: ${account.user_id})</td></tr>
                                    <tr><th>Статус:</th><td><span class="badge ${getStatusBadgeClass(account.status)}">${account.status}</span></td></tr>
                                    <tr><th>Баланс:</th><td>${formatCurrency(account.balance)}</td></tr>
                                </table>
                            </div>
                            <div class="col-md-6">
                                <h6><i class="fas fa-chart-line"></i> Финансовая информация</h6>
                                <table class="table table-sm">
                                    <tr><th>Общий расход:</th><td>${formatCurrency(account.spend)}</td></tr>
                                    <tr><th>Дневной лимит:</th><td>${formatCurrency(account.daily_limit)}</td></tr>
                                    <tr><th>Общий лимит:</th><td>${formatCurrency(account.spend_cap)}</td></tr>
                                    <tr><th>Минимальный бюджет:</th><td>${formatCurrency(account.min_daily_budget || 0)}</td></tr>
                                </table>
                            </div>
                        </div>
                        
                        ${account.error ? `
                        <div class="alert alert-danger mt-3">
                            <h6><i class="fas fa-exclamation-triangle"></i> Ошибка</h6>
                            <p class="mb-0">${escapeHtml(account.error)}</p>
                        </div>
                        ` : ''}
                        
                        <div class="row mt-3">
                            <div class="col-12">
                                <h6><i class="fas fa-server"></i> Использование API</h6>
                                <div class="progress" style="height: 20px;">
                                    <div class="progress-bar bg-${getUsageColor(account.requests_usage_percent)}" 
                                         style="width: ${account.requests_usage_percent}%">
                                        ${account.requests_usage_percent}%
                                    </div>
                                </div>
                                <small class="text-muted">
                                    Запросов сегодня: ${account.requests_today} из ${account.requests_limit}
                                    (${account.requests_usage_percent}%)
                                </small>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            <i class="fas fa-times"></i> Закрыть
                        </button>
                        <button type="button" class="btn btn-primary" onclick="refreshAccount('${account.account_id}')">
                            <i class="fas fa-sync-alt"></i> Обновить
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

   
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    const modal = new bootstrap.Modal(document.getElementById('accountModal'));
    modal.show();

   
    document.getElementById('accountModal').addEventListener('hidden.bs.modal', function() {
        this.remove();
    });
}

function testAccountToken(accountId) {
    const account = allAccounts.find(acc => acc.account_id === accountId);
    if (!account) return;

    fetch('/api/admin/test_tokens')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const accountInfo = data.results.find(acc => acc.account_id === accountId);
                if (accountInfo) {
                    showAlert(`
                        <h5><i class="fas fa-bug"></i> Диагностика токена</h5>
                        <p><strong>Аккаунт:</strong> ${accountInfo.account_id}</p>
                        <p><strong>Пользователь:</strong> ${accountInfo.username}</p>
                        <p><strong>Токен валиден:</strong> ${accountInfo.token_valid ? '✅ Да' : '❌ Нет'}</p>
                        <p><strong>Статус:</strong> ${accountInfo.status || 'Неизвестно'}</p>
                        ${accountInfo.error ? `<p><strong>Ошибка:</strong> ${accountInfo.error}</p>` : ''}
                    `, accountInfo.token_valid ? 'success' : 'danger');
                }
            }
        })
        .catch(error => {
            showAlert('Ошибка тестирования токена: ' + error.message, 'danger');
        });
}

function refreshAccount(accountId) {
    const account = allAccounts.find(acc => acc.account_id === accountId);
    if (!account) return;

    
    const button = event?.target || document.querySelector(`[onclick="refreshAccount('${accountId}')"]`);
    const originalHtml = button.innerHTML;
    button.innerHTML = '<div class="spinner-border spinner-border-sm"></div>';
    button.disabled = true;

    
    fetch('/api/admin/all_accounts_limits')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                allAccounts = data.accounts;
                renderAccountsTable(allAccounts);
                showAlert('Данные успешно обновлены', 'success');
            }
        })
        .catch(error => {
            showAlert('Ошибка обновления: ' + error.message, 'danger');
        })
        .finally(() => {
            button.innerHTML = originalHtml;
            button.disabled = false;
        });
}

function setupEventListeners() {
  
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(applyFilters, 300));
    }

   
    const statusFilter = document.getElementById('statusFilter');
    const userFilter = document.getElementById('userFilter');
    
    if (statusFilter) {
        statusFilter.addEventListener('change', applyFilters);
    }
    if (userFilter) {
        userFilter.addEventListener('change', applyFilters);
    }

    
    const refreshBtn = document.getElementById('refreshButton');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            this.innerHTML = '<div class="spinner-border spinner-border-sm"></div> Обновление...';
            this.disabled = true;
            
            loadData();
            loadTokensStats();
            loadDebugInfo();
            
            setTimeout(() => {
                this.innerHTML = '<i class="fas fa-sync-alt"></i> Обновить';
                this.disabled = false;
            }, 2000);
        });
    }

  
    const tabLinks = document.querySelectorAll('[data-bs-toggle="tab"]');
    tabLinks.forEach(tab => {
        tab.addEventListener('shown.bs.tab', function(e) {
            const target = e.target.getAttribute('data-bs-target');
            if (target === '#tokens-tab' && (!tokensStats || tokensStats.length === 0)) {
                loadTokensStats();
            }
        });
    });
}

function initTooltips() {
    
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}


function getStatusClass(status) {
    if (!status || typeof status !== 'string') return '';
    
    const statusStr = String(status).toUpperCase();
    switch(statusStr) {
        case 'ACTIVE': 
            return 'table-success';
        case 'DISABLED': 
            return 'table-danger';
        case 'PENDING_REVIEW': 
        case 'PENDING':
            return 'table-warning';
        case 'ERROR': 
        case 'NETWORK_ERROR': 
        case 'API_ERROR':
        case 'INVALID_DATA':
            return 'table-danger';
        default: 
            return '';
    }
}

function getStatusBadgeClass(status) {
    if (!status || typeof status !== 'string') return 'bg-secondary';
    
    const statusStr = String(status).toUpperCase();
    switch(statusStr) {
        case 'ACTIVE': 
            return 'bg-success';
        case 'DISABLED': 
        case 'ERROR':
        case 'NETWORK_ERROR':
        case 'API_ERROR':
        case 'INVALID_DATA':
            return 'bg-danger';
        case 'PENDING_REVIEW': 
        case 'PENDING':
            return 'bg-warning';
        default: 
            return 'bg-secondary';
    }
}

function getStatusIcon(status) {
    if (!status || typeof status !== 'string') return 'fas fa-question-circle';
    
    const statusStr = String(status).toUpperCase();
    switch(statusStr) {
        case 'ACTIVE': 
            return 'fas fa-check-circle';
        case 'DISABLED': 
            return 'fas fa-ban';
        case 'PENDING_REVIEW': 
        case 'PENDING':
            return 'fas fa-clock';
        case 'ERROR': 
        case 'NETWORK_ERROR': 
        case 'API_ERROR':
        case 'INVALID_DATA':
            return 'fas fa-exclamation-triangle';
        default: 
            return 'fas fa-question-circle';
    }
}
function getUsageColor(percent) {
    if (percent === undefined || percent === null) return 'secondary';
    if (percent > 80) return 'danger';
    if (percent > 60) return 'warning';
    return 'success';
}

function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(amount);
}
function initBasicFunctionality() {
    console.log('Основной JS не загружен, инициализируем базовый функционал');
    
 
    const refreshBtn = document.getElementById('refreshButton');
    if (refreshBtn) {
        refreshBtn.onclick = function() {
            location.reload();
        };
    }
    
    
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.oninput = function() {
            const searchText = this.value.toLowerCase();
            const rows = document.querySelectorAll('#accountsTableBody tr');
            
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(searchText) ? '' : 'none';
            });
        };
    }
    
    console.log('Базовый функционал инициализирован');
}


setTimeout(() => {
    if (typeof loadData === 'undefined') {
        initBasicFunctionality();
    }
}, 1000);


if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAdminPanel);
} else {
    initAdminPanel();
}
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function showError(message) {
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-danger alert-dismissible fade show';
    alertDiv.innerHTML = `
        <i class="fas fa-exclamation-triangle"></i> ${escapeHtml(message)}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.querySelector('.container');
    container.insertBefore(alertDiv, container.firstChild);
    
    
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}

function showAlert(message, type = 'info') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 1050; min-width: 300px;';
    alertDiv.innerHTML = `
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        ${message}
    `;
    
    document.body.appendChild(alertDiv);
    
   
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}


window.viewAccountDetails = viewAccountDetails;
window.testAccountToken = testAccountToken;
window.refreshAccount = refreshAccount;
window.loadData = loadData;
window.applyFilters = applyFilters;


setInterval(() => {
    console.log('Автообновление данных...');
    loadData();
    loadTokensStats();
}, 5 * 60 * 1000);


document.addEventListener('visibilitychange', function() {
    if (!document.hidden) {
        loadData();
    }
});


if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        initAdminPanel,
        loadData,
        applyFilters
    };
}