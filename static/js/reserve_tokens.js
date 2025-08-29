document.addEventListener('DOMContentLoaded', function() {
    loadReserveTokens();
    
    document.getElementById('addTokenForm').addEventListener('submit', function(e) {
        e.preventDefault();
        
        const king = document.getElementById('kingInput').value.trim();
        const token = document.getElementById('tokenInput').value.trim();
        const accountIds = document.getElementById('accountIdsInput').value.trim();
        
        if (!king || !token) {
            Swal.fire('Ошибка', 'Заполните KING и токен', 'error');
            return;
        }
        
        addReserveToken(king, token, accountIds);
    });
});

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
                <small>Добавьте токены через форму выше</small>
            </div>
        `;
        return;
    }
    
    let html = '';
    let tokenIndex = 0;
    
    for (const [king, tokenList] of Object.entries(tokens)) {
        tokenList.forEach(tokenObj => {
            // Проверяем что tokenObj существует и имеет token
            if (!tokenObj || !tokenObj.token) {
                console.error('Invalid token object:', tokenObj);
                return;
            }
            
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
                                    <button class="btn btn-sm btn-info me-2" 
                                            onclick="showAddAccountModal('${king}', '${tokenObj.token}')">
                                        <i class="bi bi-plus"></i> Добавить аккаунт
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
                                <span class="badge bg-${account.status === 'success' ? 'success' : 
                                    account.status === 'error' ? 'danger' : 'secondary'}">
                                    ${account.status || 'Не проверен'}
                                </span>
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

function showAddAccountModal(king, token) {
    document.getElementById('modalKing').value = king;
    document.getElementById('modalToken').value = token;
    new bootstrap.Modal(document.getElementById('addAccountModal')).show();
}

function addAccountToToken() {
    const king = document.getElementById('modalKing').value;
    const token = document.getElementById('modalToken').value;
    const accountId = document.getElementById('modalAccountId').value.trim();
    
    if (!accountId) {
        Swal.fire('Ошибка', 'Введите ID аккаунта', 'error');
        return;
    }
    
    fetch('/api/reserve_tokens/accounts', {
        method: 'POST',
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
            Swal.fire('Успех', 'Аккаунт добавлен', 'success');
            document.getElementById('addAccountModal').querySelector('.btn-close').click();
            loadReserveTokens();
        } else {
            Swal.fire('Ошибка', data.error || 'Ошибка добавления аккаунта', 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка', 'Ошибка сети', 'error');
    });
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
                    // Удаляем строку из таблицы
                    const row = document.getElementById(`account-${accountId}`);
                    if (row) row.remove();
                    
                    Swal.fire('Успех', 'Аккаунт удален', 'success');
                    
                    // Если больше нет аккаунтов, показываем сообщение
                    const tableBody = document.getElementById(`accounts-body-${tokenIndex}`);
                    if (tableBody && tableBody.children.length === 0) {
                        document.getElementById(`limits-${tokenIndex}`).innerHTML = 
                            '<div class="alert alert-info">Нет добавленных аккаунтов</div>';
                    }
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
    const tokenElement = document.querySelector(`button[data-bs-target*="token"]:contains("${king}")`).closest('.accordion-item');
    const limitsDiv = tokenElement.querySelector('.accordion-body .table-responsive');
    
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
            loadReserveTokens(); // Перезагружаем для обновления данных
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

function addReserveToken(king, token, accountIds) {
    const btn = document.querySelector('#addTokenForm button[type="submit"]');
    const originalText = btn.innerHTML;
    
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Добавление...';
    
    // Подготавливаем account_ids
    const account_ids = accountIds ? 
        accountIds.split(',').map(id => id.trim()).filter(id => id) : [];
    
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
            document.getElementById('addTokenForm').reset();
            loadReserveTokens();
        } else {
            Swal.fire('Ошибка', data.error || 'Ошибка добавления токена', 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка', 'Ошибка сети', 'error');
    })
    .finally(() => {
        btn.disabled = false;
        btn.innerHTML = originalText;
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