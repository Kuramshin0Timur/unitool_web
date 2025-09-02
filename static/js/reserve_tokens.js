document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, starting reserve tokens...');
    loadReserveTokens();
    loadTokensTable();
});

function loadTokensTable() {
    console.log('Loading tokens table...');
    fetch('/api/reserve_tokens/table')
        .then(response => {
            console.log('Response status:', response.status);
            return response.json();
        })
        .then(data => {
            console.log('Tokens data received:', data);
            if (data.success) {
                console.log('Tokens found:', data.tokens);
                renderTokensTable(data.tokens);
            } else {
                console.error('Error loading tokens:', data.error);
                renderEmptyTable();
            }
        })
        .catch(error => {
            console.error('Error loading table:', error);
            renderEmptyTable();
        });
}

// reserve_tokens.js - исправленная функция renderTokensTable
function renderTokensTable(tokens) {
    console.log('Rendering tokens table with data:', tokens);
    const tbody = document.querySelector('#tokensTable tbody');
    tbody.innerHTML = '';
    
    if (!tokens || Object.keys(tokens).length === 0) {
        console.log('No tokens data, rendering empty table');
        renderEmptyTable();
        return;
    }
    
    let hasData = false;
    let rowCount = 0;
    
    // Обрабатываем новую структуру данных
    if (Array.isArray(tokens)) {
        // Если tokens - это массив
        tokens.forEach(tokenObj => {
            if (!tokenObj || !tokenObj.token) {
                console.log('Skipping invalid token object:', tokenObj);
                return;
            }
            
            hasData = true;
            rowCount++;
            
            const king = tokenObj.king || '';
            const accounts = tokenObj.accounts || [];
            const accountIds = accounts.map(acc => acc.account_id).join(', ');
            
            console.log('Token:', tokenObj.token, 'King:', king, 'Accounts:', accounts.length);
            
            const requestsLimit = accounts.length > 0 ? accounts[0].requests_limit || 100 : 100;
            const requestsToday = accounts.length > 0 ? accounts[0].requests_today || 0 : 0;
            const requestsPercent = accounts.length > 0 ? accounts[0].requests_usage_percent || 0 : 0;
            
            const row = document.createElement('tr');
            row.innerHTML = `
                <td contenteditable="true" class="editable-cell">${king}</td>
                <td contenteditable="true" class="editable-cell">${tokenObj.token}</td>
                <td contenteditable="true" class="editable-cell">${accountIds}</td>
                <td>${requestsLimit}</td>
                <td>${requestsToday}</td>
                <td>
                    <div class="progress" style="height: 20px;">
                        <div class="progress-bar ${requestsPercent > 80 ? 'bg-warning' : 'bg-success'}" 
                             role="progressbar" style="width: ${Math.min(requestsPercent, 100)}%">
                            ${requestsPercent}%
                        </div>
                    </div>
                </td>
                <td>
                    <button class="btn btn-sm btn-primary me-1" onclick="updateTokenFromRow(this)">
                        <i class="bi bi-check"></i> Сохранить
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="deleteTokenFromRow(this, '${king}', '${tokenObj.token}')">
                        <i class="bi bi-trash"></i> Удалить
                    </button>
                </td>
            `;
            
            tbody.appendChild(row);
        });
    } else {
        // Если tokens - это объект (старая структура)
        for (const [king, tokenList] of Object.entries(tokens)) {
            console.log('Processing king:', king, 'with tokens:', tokenList);
            tokenList.forEach(tokenObj => {
                if (!tokenObj || !tokenObj.token) {
                    console.log('Skipping invalid token object:', tokenObj);
                    return;
                }
                
                hasData = true;
                rowCount++;
                const accounts = tokenObj.accounts || [];
                const accountIds = accounts.map(acc => acc.account_id).join(', ');
                
                console.log('Token:', tokenObj.token, 'Accounts:', accounts.length);
                
                const requestsLimit = accounts.length > 0 ? accounts[0].requests_limit || 100 : 100;
                const requestsToday = accounts.length > 0 ? accounts[0].requests_today || 0 : 0;
                const requestsPercent = accounts.length > 0 ? accounts[0].requests_usage_percent || 0 : 0;
                
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td contenteditable="true" class="editable-cell">${king}</td>
                    <td contenteditable="true" class="editable-cell">${tokenObj.token}</td>
                    <td contenteditable="true" class="editable-cell">${accountIds}</td>
                    <td>${requestsLimit}</td>
                    <td>${requestsToday}</td>
                    <td>
                        <div class="progress" style="height: 20px;">
                            <div class="progress-bar ${requestsPercent > 80 ? 'bg-warning' : 'bg-success'}" 
                                 role="progressbar" style="width: ${Math.min(requestsPercent, 100)}%">
                                ${requestsPercent}%
                            </div>
                        </div>
                    </td>
                    <td>
                        <button class="btn btn-sm btn-primary me-1" onclick="updateTokenFromRow(this)">
                            <i class="bi bi-check"></i> Сохранить
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="deleteTokenFromRow(this, '${king}', '${tokenObj.token}')">
                            <i class="bi bi-trash"></i> Удалить
                        </button>
                    </td>
                `;
                
                tbody.appendChild(row);
            });
        }
    }
    
    console.log('Total rows processed:', rowCount, 'Has data:', hasData);
    
    if (hasData) {
        addNewRow();
    } else {
        renderEmptyTable();
    }
}

function renderEmptyTable() {
    const tbody = document.querySelector('#tokensTable tbody');
    tbody.innerHTML = `
        <tr>
            <td colspan="7" class="text-center text-muted py-4">
                <i class="bi bi-inbox fs-1"></i>
                <p class="mt-2">Нет резервных токенов</p>
                <small>Добавьте токены через таблицу</small>
            </td>
        </tr>
    `;
    addNewRow();
}

function addNewRow() {
    const tbody = document.querySelector('#tokensTable tbody');
    // Проверяем, нет ли уже пустой строки
    const existingEmptyRows = tbody.querySelectorAll('tr');
    let hasEmptyRow = false;
    
    existingEmptyRows.forEach(row => {
        const cells = row.querySelectorAll('.editable-cell');
        if (cells.length === 3) {
            const king = cells[0].textContent.trim();
            const token = cells[1].textContent.trim();
            const accounts = cells[2].textContent.trim();
            
            if (!king && !token && !accounts) {
                hasEmptyRow = true;
            }
        }
    });
    
    if (!hasEmptyRow) {
        const newRow = document.createElement('tr');
        newRow.innerHTML = `
            <td contenteditable="true" class="editable-cell"></td>
            <td contenteditable="true" class="editable-cell"></td>
            <td contenteditable="true" class="editable-cell"></td>
            <td>-</td>
            <td>-</td>
            <td>-</td>
            <td>
                <button class="btn btn-sm btn-success" onclick="addTokenFromRow(this)">
                    <i class="bi bi-plus"></i> Добавить
                </button>
            </td>
        `;
        tbody.appendChild(newRow);
    }
}

function addTokenFromRow(button) {
    const row = button.closest('tr');
    const cells = row.querySelectorAll('.editable-cell');
    
    const king = cells[0].textContent.trim();
    const token = cells[1].textContent.trim();
    const accountIds = cells[2].textContent.trim();
    
    if (!king || !token) {
        Swal.fire('Ошибка', 'Заполните KING и токен', 'error');
        return;
    }
    
    const account_ids = accountIds ? accountIds.split(',').map(id => id.trim()).filter(id => id) : [];
    
    fetch('/api/reserve_tokens', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
            king: king, 
            token: token,
            account_ids: account_ids
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire('Успех', 'Токен успешно добавлен', 'success');
            loadTokensTable();
            loadReserveTokens();
        } else {
            Swal.fire('Ошибка', data.error || 'Ошибка добавления токена', 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка', 'Ошибка сети', 'error');
    });
}

function updateTokenFromRow(button) {
    const row = button.closest('tr');
    const cells = row.querySelectorAll('.editable-cell');
    
    const king = cells[0].textContent.trim();
    const token = cells[1].textContent.trim();
    const accountIds = cells[2].textContent.trim();
    
    if (!king || !token) {
        Swal.fire('Ошибка', 'Заполните KING и токен', 'error');
        return;
    }
    
    // Сначала удаляем старый токен, потом добавляем новый
    const oldKing = king;
    const oldToken = token;
    
    const account_ids = accountIds ? accountIds.split(',').map(id => id.trim()).filter(id => id) : [];
    
    // Удаляем старый токен
    fetch('/api/reserve_tokens', {
        method: 'DELETE',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ king: oldKing, token: oldToken })
    })
    .then(() => {
        // Добавляем обновленный токен
        return fetch('/api/reserve_tokens', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 
                king: king, 
                token: token,
                account_ids: account_ids
            })
        });
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire('Успех', 'Токен успешно обновлен', 'success');
            loadTokensTable();
            loadReserveTokens();
        } else {
            Swal.fire('Ошибка', data.error || 'Ошибка обновления токена', 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка', 'Ошибка сети', 'error');
    });
}

function deleteTokenFromRow(button, king, token) {
    Swal.fire({
        title: 'Удалить токен?',
        text: `Токен для KING "${king}" будет удален`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Да, удалить',
        cancelButtonText: 'Отмена'
    }).then((result) => {
        if (result.isConfirmed) {
            fetch('/api/reserve_tokens', {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ king: king, token: token })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    Swal.fire('Успех', 'Токен удален', 'success');
                    loadTokensTable();
                    loadReserveTokens();
                } else {
                    Swal.fire('Ошибка', data.error || 'Ошибка удаления токена', 'error');
                }
            })
            .catch(error => {
                Swal.fire('Ошибка', 'Ошибка сети', 'error');
            });
        }
    });
}

// Остальные функции остаются без изменений
function loadReserveTokens() {
    const accordion = document.getElementById('tokensAccordion');
    accordion.innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border" role="status">
                <span class="visually-hidden">Загрузка...</span>
            </div>
            <p class="mt-2">Загрузка токенов...</p>
        </div>
    `;
    
    fetch('/api/reserve_tokens')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                renderTokensAccordion(data.tokens);
            } else {
                showError('Ошибка загрузки токенов: ' + (data.error || ''));
            }
        })
        .catch(error => {
            console.error('Ошибка загрузки токенов:', error);
            showError('Ошибка сети при загрузке токенов');
        });
}

function renderTokensAccordion(tokens) {
    const accordion = document.getElementById('tokensAccordion');
    
    if (!tokens || Object.keys(tokens).length === 0) {
        accordion.innerHTML = `
            <div class="text-center text-muted py-4">
                <i class="bi bi-inbox fs-1"></i>
                <p class="mt-2">Нет резервных токенов</p>
                <small>Добавьте токены через таблицу выше</small>
            </div>
        `;
        return;
    }
    
    let html = '';
    let tokenIndex = 0;
    
    for (const [king, tokenList] of Object.entries(tokens)) {
        tokenList.forEach(tokenObj => {
            if (!tokenObj || !tokenObj.token) return;
            
            const tokenId = `token-${tokenIndex}`;
            const tokenPreview = tokenObj.token.length > 15 ? 
                tokenObj.token.substring(0, 15) + '...' : tokenObj.token;
            
            html += `
                <div class="accordion-item">
                    <h2 class="accordion-header">
                        <button class="accordion-button collapsed" type="button" 
                                data-bs-toggle="collapse" data-bs-target="#${tokenId}"
                                aria-expanded="false">
                            <strong>KING: ${king}</strong> 
                            <span class="badge bg-secondary ms-2">${tokenPreview}</span>
                            <span class="badge bg-info ms-2">Аккаунтов: ${tokenObj.accounts ? tokenObj.accounts.length : 0}</span>
                        </button>
                    </h2>
                    <div id="${tokenId}" class="accordion-collapse collapse">
                        <div class="accordion-body">
                            <div class="d-flex justify-content-between align-items-center mb-3">
                                <h6>Токен: <code>${tokenObj.token}</code></h6>
                                <div>
                                    <button class="btn btn-sm btn-outline-primary me-2" 
                                            onclick="copyToClipboard('${tokenObj.token}')">
                                        <i class="bi bi-copy"></i> Копировать
                                    </button>
                                    <button class="btn btn-sm btn-success me-2" 
                                            onclick="checkTokenLimits('${king}', '${tokenObj.token}')">
                                        <i class="bi bi-arrow-repeat"></i> Проверить лимиты
                                    </button>
                                    <button class="btn btn-sm btn-danger" 
                                            onclick="deleteToken('${king}', '${tokenObj.token}')">
                                        <i class="bi bi-trash"></i> Удалить
                                    </button>
                                </div>
                            </div>
                            
                            <div id="limits-${tokenIndex}" class="mt-3">
                                ${tokenObj.accounts && tokenObj.accounts.length > 0 ? 
                                    renderAccountsTable(tokenObj.accounts, tokenIndex, king, tokenObj.token) : 
                                    '<div class="alert alert-info">Нет добавленных аккаунтов</div>'
                                }
                            </div>
                        </div>
                    </div>
                </div>
            `;
            tokenIndex++;
        });
    }
    
    accordion.innerHTML = html;
}

function renderAccountsTable(accounts, tokenIndex, king, token) {
    return `
        <div class="table-responsive">
            <table class="table table-sm table-striped">
                <thead>
                    <tr>
                        <th>ID Аккаунта</th>
                        <th>Лимит расходов</th>
                        <th>Потрачено</th>
                        <th>Остаток</th>
                        <th>Статус</th>
                        <th>Лимит запросов</th>
                        <th>Использовано</th>
                        <th>Процент</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody id="accounts-body-${tokenIndex}">
                    ${accounts.map(account => `
                        <tr id="account-${account.account_id}">
                            <td><code>${account.account_id}</code></td>
                            <td>${account.spend_cap !== undefined && account.spend_cap !== null ? 
                                '$' + parseFloat(account.spend_cap).toFixed(2) : 'Не проверен'}</td>
                            <td>${account.amount_spent !== undefined && account.amount_spent !== null ? 
                                '$' + parseFloat(account.amount_spent).toFixed(2) : 'Не проверен'}</td>
                            <td>${account.remaining !== undefined && account.remaining !== null ? 
                                '$' + parseFloat(account.remaining).toFixed(2) : 'Не проверен'}</td>
                            <td>
                                <span class="badge bg-${account.status === 'ACTIVE' ? 'success' : 
                                    account.status === 'DISABLED' ? 'danger' : 'secondary'}">
                                    ${account.status || 'Не проверен'}
                                </span>
                            </td>
                            <td>${account.requests_limit || 100}</td>
                            <td>${account.requests_today || 0}</td>
                            <td>
                                <div class="progress" style="height: 20px; width: 100px;">
                                    <div class="progress-bar ${(account.requests_usage_percent || 0) > 80 ? 'bg-warning' : 'bg-success'}" 
                                         role="progressbar" style="width: ${account.requests_usage_percent || 0}%">
                                        ${account.requests_usage_percent || 0}%
                                    </div>
                                </div>
                            </td>
                            <td>
                                <button class="btn btn-sm btn-outline-danger" 
                                        onclick="removeAccount('${king}', '${token}', '${account.account_id}', ${tokenIndex})">
                                    <i class="bi bi-trash"></i>
                                </button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function removeAccount(king, token, accountId, tokenIndex) {
    Swal.fire({
        title: 'Удалить аккаунт?',
        text: `Аккаунт ${accountId} будет удален из этого токена`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Да, удалить',
        cancelButtonText: 'Отмена'
    }).then((result) => {
        if (result.isConfirmed) {
            fetch('/api/reserve_tokens/accounts', {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ 
                    king: king, 
                    token: token,
                    account_id: accountId 
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const row = document.getElementById(`account-${accountId}`);
                    if (row) row.remove();
                    
                    Swal.fire('Успех', 'Аккаунт удален', 'success');
                    
                    const tableBody = document.getElementById(`accounts-body-${tokenIndex}`);
                    if (tableBody && tableBody.children.length === 0) {
                        document.getElementById(`limits-${tokenIndex}`).innerHTML = 
                            '<div class="alert alert-info">Нет добавленных аккаунтов</div>';
                    }
                    
                    loadTokensTable();
                } else {
                    Swal.fire('Ошибка', data.error || 'Ошибка удаления аккаунта', 'error');
                }
            })
            .catch(error => {
                Swal.fire('Ошибка', 'Ошибка сети', 'error');
            });
        }
    });
}

function checkTokenLimits(king, token) {
    const tokenElement = document.querySelector(`button[data-bs-target*="token"]:contains("${king}")`);
    if (!tokenElement) return;
    
    const limitsDiv = tokenElement.closest('.accordion-item').querySelector('.accordion-body .table-responsive');
    
    if (limitsDiv) {
        limitsDiv.innerHTML = `
            <div class="text-center py-2">
                <div class="spinner-border spinner-border-sm" role="status">
                    <span class="visually-hidden">Проверка лимитов...</span>
                </div>
                <span class="ms-2">Проверка лимитов...</span>
            </div>
        `;
    }
    
    fetch('/api/reserve_tokens/check_limits', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ king: king, token: token })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire('Успех', `Проверено ${data.checked_accounts} аккаунтов`, 'success');
            loadReserveTokens();
            loadTokensTable();
        } else {
            Swal.fire('Ошибка', data.error || 'Ошибка проверки лимитов', 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка', 'Ошибка сети', 'error');
    });
}

function checkAllLimits() {
    Swal.fire({
        title: 'Проверить все лимиты?',
        text: 'Это может занять некоторое время',
        icon: 'question',
        showCancelButton: true,
        confirmButtonText: 'Да, проверить',
        cancelButtonText: 'Отмена'
    }).then((result) => {
        if (result.isConfirmed) {
            fetch('/api/reserve_tokens/check_all_limits', {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    Swal.fire('Успех', `Проверено ${data.total_checked} аккаунтов`, 'success');
                    loadReserveTokens();
                    loadTokensTable();
                } else {
                    Swal.fire('Ошибка', data.error || 'Ошибка проверки лимитов', 'error');
                }
            })
            .catch(error => {
                Swal.fire('Ошибка', 'Ошибка сети', 'error');
            });
        }
    });
}

function deleteToken(king, token) {
    Swal.fire({
        title: 'Удалить токен?',
        text: `Токен для KING "${king}" будет удален`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Да, удалить',
        cancelButtonText: 'Отмена'
    }).then((result) => {
        if (result.isConfirmed) {
            fetch('/api/reserve_tokens', {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ king: king, token: token })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    Swal.fire('Успех', 'Токен удален', 'success');
                    loadReserveTokens();
                    loadTokensTable();
                } else {
                    Swal.fire('Ошибка', data.error || 'Ошибка удаления токена', 'error');
                }
            })
            .catch(error => {
                Swal.fire('Ошибка', 'Ошибка сети', 'error');
            });
        }
    });
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        Swal.fire({
            icon: 'success',
            title: 'Скопировано!',
            text: 'Токен скопирован в буфер обмена',
            timer: 1500,
            showConfirmButton: false
        });
    });
}

function showError(message) {
    const accordion = document.getElementById('tokensAccordion');
    accordion.innerHTML = `
        <div class="alert alert-danger">
            <i class="bi bi-exclamation-triangle"></i> ${message}
            <button class="btn btn-sm btn-outline-secondary ms-2" onclick="loadReserveTokens()">
                <i class="bi bi-arrow-repeat"></i> Попробовать снова
            </button>
        </div>
    `;
}
