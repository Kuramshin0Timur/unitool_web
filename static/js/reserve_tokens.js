document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, starting reserve tokens...');
    loadCombinedTokensTable();
    addAutoPopulateButton();
});


function showReplaceTokenModal(king, oldToken) {
    Swal.fire({
        title: 'Заменить токен',
        html: `
            <div class="mb-3">
                <label class="form-label">KING:</label>
                <input type="text" class="form-control" value="${king}" readonly>
            </div>
            <div class="mb-3">
                <label class="form-label">Старый токен:</label>
                <textarea class="form-control" readonly>${oldToken}</textarea>
            </div>
            <div class="mb-3">
                <label class="form-label">Новый токен:</label>
                <textarea class="form-control" id="newTokenValue" rows="3" placeholder="Введите новый токен" required></textarea>
            </div>
        `,
        showCancelButton: true,
        confirmButtonText: 'Заменить',
        cancelButtonText: 'Отмена',
        preConfirm: () => {
            const newToken = document.getElementById('newTokenValue').value.trim();
            
            if (!newToken) {
                Swal.showValidationMessage('Введите новый токен');
                return false;
            }
            
            return { king, oldToken, newToken };
        }
    }).then((result) => {
        if (result.isConfirmed) {
            replaceToken(result.value);
        }
    });
}

function replaceToken(data) {
    fetch('/api/replace_token', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire('Успех', data.message, 'success');
            loadCombinedTokensTable();
        } else {
            Swal.fire('Ошибка', data.error || 'Ошибка замены токена', 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка', 'Ошибка сети', 'error');
    });
}
function loadCombinedTokensTable() {
    console.log('Loading combined tokens table...');
    fetch('/api/combined_tokens_table')
        .then(response => {
            console.log('Response status:', response.status);
            return response.json();
        })
        .then(data => {
            console.log('Combined tokens data received:', data);
            if (data.success) {
                console.log('Combined tokens found:', data.tokens);
                renderCombinedTokensTable(data.tokens);
            } else {
                console.error('Error loading combined tokens:', data.error);
                renderEmptyTable();
            }
        })
        .catch(error => {
            console.error('Error loading combined table:', error);
            renderEmptyTable();
        });
}





function saveNewToken(king, oldToken, inputId, accountsInputId) {
    const newToken = document.getElementById(inputId).value.trim();
    const accountsInput = document.getElementById(accountsInputId).value.trim();

    if (!newToken && !accountsInput) {
        Swal.fire('Ошибка', 'Введите новый токен или аккаунты для изменения', 'error');
        return;
    }

    const account_ids = accountsInput ? accountsInput.split(',').map(id => id.trim()).filter(id => id) : [];

    const data = { 
        king, 
        oldToken, 
        newToken: newToken || oldToken,
        account_ids: account_ids.length > 0 ? account_ids : undefined
    };

    fetch('/api/replace_token', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire('Успех', data.message, 'success');
            loadCombinedTokensTable();
        } else {
            Swal.fire('Ошибка', data.error || 'Ошибка замены токена', 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка', 'Ошибка сети', 'error');
    });
}

function editKing(button) {
    const container = button.closest('.editable-king');
    const currentKing = container.getAttribute('data-king');
    const token = container.getAttribute('data-token');
    
    Swal.fire({
        title: 'Изменить KING',
        html: `
            <div class="mb-3">
                <label class="form-label">Текущий KING:</label>
                <input type="text" class="form-control" id="editKingInput" value="${currentKing}" required>
            </div>
            <div class="mb-3">
                <label class="form-label">Токен:</label>
                <textarea class="form-control" readonly>${token}</textarea>
            </div>
        `,
        showCancelButton: true,
        confirmButtonText: 'Сохранить',
        cancelButtonText: 'Отмена',
        preConfirm: () => {
            const newKing = document.getElementById('editKingInput').value.trim();
            if (!newKing) {
                Swal.showValidationMessage('Введите новый KING');
                return false;
            }
            return { currentKing, newKing, token };
        }
    }).then((result) => {
        if (result.isConfirmed) {
            updateKing(result.value);
        }
    });
}


function editToken(button) {
    const container = button.closest('.editable-token');
    const king = container.getAttribute('data-king');
    const currentToken = container.getAttribute('data-token');
    
    Swal.fire({
        title: 'Изменить токен',
        html: `
            <div class="mb-3">
                <label class="form-label">KING:</label>
                <input type="text" class="form-control" value="${king}" readonly>
            </div>
            <div class="mb-3">
                <label class="form-label">Текущий токен:</label>
                <textarea class="form-control" readonly>${currentToken}</textarea>
            </div>
            <div class="mb-3">
                <label class="form-label">Новый токен:</label>
                <textarea class="form-control" id="editTokenInput" rows="3" placeholder="Введите новый токен" required></textarea>
            </div>
        `,
        showCancelButton: true,
        confirmButtonText: 'Сохранить',
        cancelButtonText: 'Отмена',
        preConfirm: () => {
            const newToken = document.getElementById('editTokenInput').value.trim();
            if (!newToken) {
                Swal.showValidationMessage('Введите новый токен');
                return false;
            }
            return { king, currentToken, newToken };
        }
    }).then((result) => {
        if (result.isConfirmed) {
            updateToken(result.value);
        }
    });
}


function updateKing(data) {
    fetch('/api/update_king', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            Swal.fire('Успех', result.message, 'success');
            loadCombinedTokensTable();
        } else {
            Swal.fire('Ошибка', result.error, 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка', 'Ошибка сети', 'error');
    });
}


function updateToken(data) {
    fetch('/api/update_token', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            Swal.fire('Успех', result.message, 'success');
            loadCombinedTokensTable();
        } else {
            Swal.fire('Ошибка', result.error, 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка', 'Ошибка сети', 'error');
    });
}


function saveTokenChanges(king, oldToken, kingInputId, tokenInputId, accountsInputId) {
    const newKing = document.getElementById(kingInputId).value.trim();
    const newToken = document.getElementById(tokenInputId).value.trim();
    const accountsInput = document.getElementById(accountsInputId).value.trim();

    if (!newKing && !newToken && !accountsInput) {
        Swal.fire('Ошибка', 'Введите изменения для сохранения', 'error');
        return;
    }

    const account_ids = accountsInput ? accountsInput.split(',').map(id => id.trim()).filter(id => id) : [];
    const finalKing = newKing || king;
    const finalToken = newToken || oldToken;

    const data = { 
        oldKing: king,  // Исправлено: передаем старый KING
        oldToken: oldToken,
        newKing: finalKing,
        newToken: finalToken,
        account_ids: account_ids.length > 0 ? account_ids : undefined
    };

    fetch('/api/update_token_complete', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            Swal.fire('Успех', result.message, 'success');
            loadCombinedTokensTable();
        } else {
            Swal.fire('Ошибка', result.error, 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка', 'Ошибка сети', 'error');
    });
}
function showAddGroupModal() {
    Swal.fire({
        title: '<i class="bi bi-plus-circle text-primary"></i> Создать новую группу токенов',
        html: `
            <div class="container-fluid">
                <div class="row">
                    <div class="col-md-6">
                        <div class="card h-100">
                            <div class="card-header bg-primary text-white">
                                <h6 class="mb-0"><i class="bi bi-tag"></i> Настройки группы</h6>
                            </div>
                            <div class="card-body">
                                <div class="mb-3">
                                    <label class="form-label"><strong>KING группы:</strong></label>
                                    <input type="text" class="form-control" id="groupKing" 
                                           placeholder="Facebook, Instagram, TikTok..." required>
                                    <small class="text-muted">Уникальное имя для группы токенов</small>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-6">
                        <div class="card h-100">
                            <div class="card-header bg-success text-white">
                                <h6 class="mb-0"><i class="bi bi-key"></i> Токены группы</h6>
                            </div>
                            <div class="card-body">
                                <div class="mb-3">
                                    <label class="form-label"><strong>Токены:</strong></label>
                                    <textarea class="form-control" id="groupTokens" rows="5" 
                                              placeholder="Введите каждый токен с новой строки" required></textarea>
                                    <small class="text-muted">Один токен на строку</small>
                                </div>
                                
                                <div class="d-flex justify-content-between align-items-center">
                                    <span class="badge bg-info" id="tokenCount">0 токенов</span>
                                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="addSampleTokens()">
                                        <i class="bi bi-magic"></i> Пример
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="row mt-3">
                    <div class="col-12">
                        <div class="card border-info">
                            <div class="card-header bg-info text-white">
                                <h6 class="mb-0"><i class="bi bi-people"></i> Аккаунты для группы</h6>
                            </div>
                            <div class="card-body">
                                <div class="mb-3">
                                    <label class="form-label"><strong>ID аккаунтов:</strong></label>
                                    <textarea class="form-control" id="groupAccounts" rows="4" 
                                              placeholder="Введите ID аккаунтов, каждый с новой строки\nМожно вводить с act_ или без\n\nПример:\n123456789\n987654321\nact_1122334455"></textarea>
                                    <small class="text-muted">Один ID аккаунта на строку (с act_ или без)</small>
                                </div>
                                
                                <div class="d-flex justify-content-between align-items-center">
                                    <span class="badge bg-info" id="accountCount">0 аккаунтов</span>
                                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="addSampleAccounts()">
                                        <i class="bi bi-magic"></i> Пример
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="row mt-3">
                    <div class="col-12">
                        <div class="card border-warning">
                            <div class="card-header bg-warning text-white">
                                <h6 class="mb-0"><i class="bi bi-eye"></i> Предпросмотр группы</h6>
                            </div>
                            <div class="card-body">
                                <div id="groupPreview" class="text-muted">
                                    Заполните поля выше для предпросмотра группы
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `,
        width: '90%',
        showCancelButton: true,
        confirmButtonText: '<i class="bi bi-plus-circle"></i> Создать группу',
        cancelButtonText: 'Отмена',
        didOpen: () => {
            // Обновляем счетчики
            const tokensTextarea = document.getElementById('groupTokens');
            const accountsTextarea = document.getElementById('groupAccounts');
            const tokenCount = document.getElementById('tokenCount');
            const accountCount = document.getElementById('accountCount');
            const preview = document.getElementById('groupPreview');
            
            tokensTextarea.addEventListener('input', updatePreview);
            accountsTextarea.addEventListener('input', updatePreview);
            document.getElementById('groupKing').addEventListener('input', updatePreview);
            
            function updatePreview() {
                const king = document.getElementById('groupKing').value.trim();
                const tokens = tokensTextarea.value.split('\n').filter(t => t.trim());
                const accounts = accountsTextarea.value.split('\n').filter(a => a.trim());
                
                tokenCount.textContent = `${tokens.length} токенов`;
                accountCount.textContent = `${accounts.length} аккаунтов`;
                
                let previewHtml = '';
                if (king) {
                    previewHtml += `<p><strong>KING:</strong> <span class="badge bg-primary">${king}</span></p>`;
                }
                if (tokens.length > 0) {
                    previewHtml += `<p><strong>Токены:</strong> ${tokens.length} шт.</p>`;
                    previewHtml += `<div class="token-preview-list">`;
                    tokens.slice(0, 3).forEach(token => {
                        previewHtml += `<span class="badge bg-secondary me-1 mb-1">${token.substring(0, 10)}...</span>`;
                    });
                    if (tokens.length > 3) {
                        previewHtml += `<span class="badge bg-light text-dark">+${tokens.length - 3} еще</span>`;
                    }
                    previewHtml += `</div>`;
                }
                if (accounts.length > 0) {
                    previewHtml += `<p><strong>Аккаунты:</strong> ${accounts.length} шт.</p>`;
                    previewHtml += `<div class="accounts-preview-list">`;
                    accounts.slice(0, 5).forEach(account => {
                        const cleanAccount = normalizeAccountId(account);
                        previewHtml += `<span class="badge bg-info me-1 mb-1">${cleanAccount}</span>`;
                    });
                    if (accounts.length > 5) {
                        previewHtml += `<span class="badge bg-light text-dark">+${accounts.length - 5} еще</span>`;
                    }
                    previewHtml += `</div>`;
                }
                
                preview.innerHTML = previewHtml || '<p class="text-muted">Заполните поля для предпросмотра</p>';
            }
            
            updatePreview();
        },
        preConfirm: () => {
            const king = document.getElementById('groupKing').value.trim();
            const tokens = document.getElementById('groupTokens').value.split('\n').filter(t => t.trim());
            const accounts = document.getElementById('groupAccounts').value.split('\n').filter(a => a.trim());
            
            if (!king) {
                Swal.showValidationMessage('Введите KING группы');
                return false;
            }
            if (tokens.length === 0) {
                Swal.showValidationMessage('Добавьте хотя бы один токен');
                return false;
            }
            
         
            const normalizedAccounts = accounts.map(account => normalizeAccountId(account));
            
            return { king, tokens, accounts: normalizedAccounts };
        }
    }).then((result) => {
        if (result.isConfirmed) {
            createTokenGroup(result.value);
        }
    });
}

function normalizeAccountId(accountId) {
    if (!accountId) return '';
    
    let cleanId = accountId.trim().toString();
    

    if (cleanId.toLowerCase().startsWith('act_')) {
        cleanId = cleanId.substring(4);
    }
    
   
    cleanId = cleanId.replace(/\D/g, '');
    
 
    if (!cleanId || !/^\d+$/.test(cleanId)) {
        return '';
    }
    

    return `act_${cleanId}`;
}


function addSampleAccounts() {
    const sampleAccounts = [
        '123456789',
        '987654321',
        'act_1122334455',
        '5566778899',
        '9988776655'
    ];
    
    document.getElementById('groupAccounts').value = sampleAccounts.join('\n');
    

    const event = new Event('input', { bubbles: true });
    document.getElementById('groupAccounts').dispatchEvent(event);
}



function addSampleAccountsToNew() {
    const sampleAccounts = [
        '123456789',
        '987654321',
        '1122334455'
    ];
    
    document.getElementById('newTokenAccounts').value = sampleAccounts.join('\n');
    
    // Trigger update
    const event = new Event('input', { bubbles: true });
    document.getElementById('newTokenAccounts').dispatchEvent(event);
}

function showEditTokenModal(king, oldToken, currentAccounts = []) {
  
    const accountIdsWithoutAct = currentAccounts.map(acc => {
        return acc.account_id.replace('act_', '');
    }).join('\n');

    Swal.fire({
        title: `<i class="bi bi-pencil text-primary"></i> Редактирование токена`,
        html: `
            <div class="container-fluid">
                <div class="row">
                    <div class="col-md-6">
                        <div class="card h-100">
                            <div class="card-header bg-primary text-white">
                                <h6 class="mb-0"><i class="bi bi-tag"></i> Настройки токена</h6>
                            </div>
                            <div class="card-body">
                                <div class="mb-3">
                                    <label class="form-label"><strong>KING:</strong></label>
                                    <input type="text" class="form-control" id="editTokenKing" 
                                           value="${king}" placeholder="Введите KING группы">
                                    <small class="text-muted">Можно изменить группу токена</small>
                                </div>
                                
                                <div class="mb-3">
                                    <label class="form-label"><strong>Токен:</strong></label>
                                    <textarea class="form-control" id="editTokenValue" rows="4" 
                                              placeholder="Введите токен" required>${oldToken}</textarea>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-6">
                        <div class="card h-100">
                            <div class="card-header bg-info text-white">
                                <h6 class="mb-0"><i class="bi bi-people"></i> Аккаунты токена</h6>
                            </div>
                            <div class="card-body">
                                <div class="mb-3">
                                    <label class="form-label"><strong>ID аккаунтов (только цифры):</strong></label>
                                    <textarea class="form-control" id="editTokenAccounts" rows="8" 
                                              placeholder="Введите ID аккаунтов, каждый с новой строки\nТолько цифры, без act_">${accountIdsWithoutAct}</textarea>
                                    <small class="text-muted">Один ID аккаунта на строку (только цифры)</small>
                                </div>
                                
                                <div class="d-flex justify-content-between align-items-center">
                                    <span class="badge bg-info" id="editAccountCount">${currentAccounts.length} аккаунтов</span>
                                    <div>
                                        <button type="button" class="btn btn-sm btn-outline-secondary me-2" onclick="addSampleAccountsToEdit()">
                                            <i class="bi bi-magic"></i> Пример
                                        </button>
                                        <button type="button" class="btn btn-sm btn-outline-secondary" onclick="clearEditAccounts()">
                                            <i class="bi bi-trash"></i> Очистить
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="row mt-3">
                    <div class="col-12">
                        <div class="card border-warning">
                            <div class="card-header bg-warning text-white">
                                <h6 class="mb-0"><i class="bi bi-eye"></i> Предпросмотр изменений</h6>
                            </div>
                            <div class="card-body">
                                <div id="editTokenPreview">
                                    <p><strong>Текущий KING:</strong> <span class="badge bg-primary">${king}</span></p>
                                    <p><strong>Токен:</strong> <code>${oldToken.substring(0, 20)}...</code></p>
                                    <p><strong>Аккаунты:</strong> ${currentAccounts.length} шт.</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `,
        width: '90%',
        showCancelButton: true,
        confirmButtonText: '<i class="bi bi-check-circle"></i> Сохранить изменения',
        cancelButtonText: 'Отмена',
        didOpen: () => {
            const kingInput = document.getElementById('editTokenKing');
            const tokenInput = document.getElementById('editTokenValue');
            const accountsTextarea = document.getElementById('editTokenAccounts');
            const accountCount = document.getElementById('editAccountCount');
            const preview = document.getElementById('editTokenPreview');
            
           
            kingInput.addEventListener('input', updatePreview);
            tokenInput.addEventListener('input', updatePreview);
            accountsTextarea.addEventListener('input', updatePreview);
            
            function updatePreview() {
                const newKing = kingInput.value.trim() || king;
                const newToken = tokenInput.value.trim() || oldToken;
                const accounts = accountsTextarea.value.split('\n').filter(a => a.trim());
                const normalizedAccounts = accounts.map(account => normalizeAccountId(account)).filter(a => a);
                
                accountCount.textContent = `${normalizedAccounts.length} аккаунтов`;
                
                let previewHtml = `
                    <p><strong>KING:</strong> <span class="badge bg-primary">${newKing}</span> ${newKing !== king ? '<span class="badge bg-warning text-dark">ИЗМЕНЕНО</span>' : ''}</p>
                    <p><strong>Токен:</strong> <code>${newToken.substring(0, 20)}${newToken.length > 20 ? '...' : ''}</code> ${newToken !== oldToken ? '<span class="badge bg-warning text-dark">ИЗМЕНЕНО</span>' : ''}</p>
                    <p><strong>Аккаунты:</strong> ${normalizedAccounts.length} шт. ${normalizedAccounts.length !== currentAccounts.length ? '<span class="badge bg-warning text-dark">ИЗМЕНЕНО</span>' : ''}</p>
                `;
                
                if (normalizedAccounts.length > 0) {
                    previewHtml += `<div class="accounts-preview-list mt-2">`;
                    normalizedAccounts.slice(0, 5).forEach(account => {
                        previewHtml += `<span class="badge bg-info me-1 mb-1">${account}</span>`;
                    });
                    if (normalizedAccounts.length > 5) {
                        previewHtml += `<span class="badge bg-light text-dark">+${normalizedAccounts.length - 5} еще</span>`;
                    }
                    previewHtml += `</div>`;
                }
                
                preview.innerHTML = previewHtml;
            }
            
            updatePreview();
        },
        preConfirm: () => {
            const newKing = document.getElementById('editTokenKing').value.trim();
            const newToken = document.getElementById('editTokenValue').value.trim();
            const accountsText = document.getElementById('editTokenAccounts').value;
            
            if (!newKing) {
                Swal.showValidationMessage('Введите KING');
                return false;
            }
            if (!newToken) {
                Swal.showValidationMessage('Введите токен');
                return false;
            }
            
  
            const accounts = accountsText.split('\n')
                .map(line => line.trim())
                .filter(line => line.length > 0);
            
    
            const normalizedAccounts = accounts.map(account => {
                let cleanId = account.trim();
                
            
                if (cleanId.toLowerCase().startsWith('act_')) {
                    cleanId = cleanId.substring(4);
                }
                
           
                cleanId = cleanId.replace(/\D/g, '');
                
              
                return cleanId ? `act_${cleanId}` : '';
            }).filter(a => a);
            
            return { 
                oldKing: king, 
                newKing: newKing,
                oldToken: oldToken,
                newToken: newToken,
                accounts: normalizedAccounts 
            };
        }
    }).then((result) => {
        if (result.isConfirmed) {
            saveTokenChangesFromModal(result.value);
        }
    });
}


function clearEditAccounts() {
    document.getElementById('editTokenAccounts').value = '';
    
   
    const event = new Event('input', { bubbles: true });
    document.getElementById('editTokenAccounts').dispatchEvent(event);
}


function clearAccounts() {
    document.getElementById('editTokenAccounts').value = '';
    
   
    const event = new Event('input', { bubbles: true });
    document.getElementById('editTokenAccounts').dispatchEvent(event);
}



function handleApiError(error, defaultMessage = 'Ошибка сервера') {
    console.error('API Error:', error);
    
    if (error.response && error.response.data && error.response.data.error) {
        return error.response.data.error;
    }
    
    if (error.message) {
        return error.message;
    }
    
    return defaultMessage;
}


fetch('/api/user/reserve_tokens', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
    },
    body: JSON.stringify({ 
        king: data.king, 
        token: data.token,
        account_ids: account_ids
    })
})
.then(response => {
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
})
.then(data => {
    if (data.success) {
        Swal.fire('Успех', data.message, 'success');
        loadCombinedTokensTable();
    } else {
        Swal.fire('Ошибка', data.error || 'Ошибка добавления токена', 'error');
    }
})
.catch(error => {
    const errorMessage = handleApiError(error, 'Ошибка сети');
    Swal.fire('Ошибка', errorMessage, 'error');
});

function saveTokenChangesFromModal(data) {
    fetch('/api/update_token_complete', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
            oldKing: data.oldKing,
            newKing: data.newKing,
            oldToken: data.oldToken,
            newToken: data.newToken,
            account_ids: data.accounts
        })
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            Swal.fire('Успех', result.message, 'success');
            loadCombinedTokensTable();
        } else {
            Swal.fire('Ошибка', result.error, 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка', 'Ошибка сети', 'error');
    });
}

function addSampleTokens() {
    const sampleTokens = [
        'EAACEdEose0cBA1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ',
        'EAACEdEose0cBA0987654321zyxwvutsrqponmlkjihgfedcbaZYXWVUTSRQPONMLKJIHGFEDCBA',
        'EAACEdEose0cBA1122334455abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    ];
    
    document.getElementById('groupTokens').value = sampleTokens.join('\n');
    document.getElementById('groupKing').value = 'Facebook';
    document.getElementById('groupAccounts').value = 'act_123456789, act_987654321';
    
   
    const event = new Event('input', { bubbles: true });
    document.getElementById('groupTokens').dispatchEvent(event);
    document.getElementById('groupKing').dispatchEvent(event);
    document.getElementById('groupAccounts').dispatchEvent(event);
}


function showAddTokenToGroupModal(king) {
    Swal.fire({
        title: `<i class="bi bi-plus-circle text-success"></i> Добавить токен в группу "${king}"`,
        html: `
            <div class="container-fluid">
                <div class="row">
                    <div class="col-md-6">
                        <div class="card h-100">
                            <div class="card-header bg-primary text-white">
                                <h6 class="mb-0"><i class="bi bi-key"></i> Токен</h6>
                            </div>
                            <div class="card-body">
                                <div class="mb-3">
                                    <label class="form-label"><strong>Токен:</strong></label>
                                    <textarea class="form-control" id="newTokenValue" rows="4" 
                                              placeholder="Введите токен" required></textarea>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-6">
                        <div class="card h-100">
                            <div class="card-header bg-info text-white">
                                <h6 class="mb-0"><i class="bi bi-people"></i> Аккаунты</h6>
                            </div>
                            <div class="card-body">
                                <div class="mb-3">
                                    <label class="form-label"><strong>ID аккаунтов:</strong></label>
                                    <textarea class="form-control" id="newTokenAccounts" rows="4" 
                                              placeholder="Введите ID аккаунтов, каждый с новой строки"></textarea>
                                    <small class="text-muted">Один ID аккаунта на строку (с act_ или без)</small>
                                </div>
                                
                                <div class="d-flex justify-content-between align-items-center">
                                    <span class="badge bg-info" id="newTokenAccountCount">0 аккаунтов</span>
                                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="addSampleAccountsToNew()">
                                        <i class="bi bi-magic"></i> Пример
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `,
        width: '80%',
        showCancelButton: true,
        confirmButtonText: '<i class="bi bi-plus"></i> Добавить токен',
        cancelButtonText: 'Отмена',
        didOpen: () => {
            const accountsTextarea = document.getElementById('newTokenAccounts');
            const accountCount = document.getElementById('newTokenAccountCount');
            
            accountsTextarea.addEventListener('input', () => {
                const accounts = accountsTextarea.value.split('\n').filter(a => a.trim());
                const normalizedAccounts = accounts.map(account => normalizeAccountId(account)).filter(a => a);
                accountCount.textContent = `${normalizedAccounts.length} аккаунтов`;
            });
        },
        preConfirm: () => {
            const token = document.getElementById('newTokenValue').value.trim();
            const accounts = document.getElementById('newTokenAccounts').value.split('\n').filter(a => a.trim());
            
            if (!token) {
                Swal.showValidationMessage('Введите токен');
                return false;
            }
            
          
            const normalizedAccounts = accounts.map(account => normalizeAccountId(account)).filter(a => a);
            
            return { king, token, accounts: normalizedAccounts };
        }
    }).then((result) => {
        if (result.isConfirmed) {
            addTokenToGroup(result.value);
        }
    });
}

function deleteGroup(king) {
    Swal.fire({
        title: 'Удалить группу?',
        html: `<p>Вы уверены, что хотите удалить группу <strong>${king}</strong> со всеми токенами?</p>
               <p class="text-danger">Это действие нельзя отменить!</p>`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Да, удалить группу',
        cancelButtonText: 'Отмена',
        confirmButtonColor: '#dc3545'
    }).then((result) => {
        if (result.isConfirmed) {
            fetch('/api/user/reserve_tokens/group', {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ king: king })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    Swal.fire('Удалено!', `Группа "${king}" удалена`, 'success');
                    loadCombinedTokensTable();
                } else {
                    Swal.fire('Ошибка', data.error || 'Ошибка удаления группы', 'error');
                }
            })
            .catch(error => {
                Swal.fire('Ошибка', 'Ошибка сети', 'error');
            });
        }
    });
}

function createTokenGroup(data) {
    const tokens = data.tokens;
    const account_ids = data.accounts.filter(a => a);
    
    Swal.fire({
        title: 'Создание группы...',
        html: `Добавляется ${tokens.length} токенов с ${account_ids.length} аккаунтами`,
        allowOutsideClick: false,
        didOpen: () => {
            Swal.showLoading();
        }
    });

    let added = 0;
    let errors = 0;

    tokens.forEach((token) => {
        fetch('/api/user/reserve_tokens', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 
                king: data.king, 
                token: token.trim(),
                account_ids: account_ids
            })
        })
        .then(response => response.json())
        .then(result => {
            added++;
            
            if (added + errors === tokens.length) {
                Swal.close();
                if (errors > 0) {
                    Swal.fire('Частично успешно', `Добавлено ${added} из ${tokens.length} токенов`, 'warning');
                } else {
                    Swal.fire('Успех', `Создана группа "${data.king}" с ${tokens.length} токенами`, 'success');
                }
                loadCombinedTokensTable();
            }
        })
        .catch(error => {
            errors++;
            if (added + errors === tokens.length) {
                Swal.close();
                Swal.fire('Ошибка', `Добавлено ${added} из ${tokens.length} токенов`, 'error');
                loadCombinedTokensTable();
            }
        });
    });
}


function addTokenToGroup(data) {
    const account_ids = data.accounts ? data.accounts : [];
    
    fetch('/api/user/reserve_tokens', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
            king: data.king, 
            token: data.token,
            account_ids: account_ids
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire('Успех', data.message, 'success');
            loadCombinedTokensTable();
        } else {
            Swal.fire('Ошибка', data.error || 'Ошибка добавления токена', 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка', 'Ошибка сети', 'error');
    });
}



function checkGroupLimits(king) {
    Swal.fire({
        title: 'Проверить лимиты группы?',
        text: `Будут проверены все токены в группе "${king}"`,
        icon: 'question',
        showCancelButton: true,
        confirmButtonText: 'Да, проверить',
        cancelButtonText: 'Отмена'
    }).then((result) => {
        if (result.isConfirmed) {
           
            fetch('/api/user/reserve_tokens')
            .then(response => response.json())
            .then(data => {
                if (data.success && data.tokens[king]) {
                    const tokens = data.tokens[king];
                    let checked = 0;
                    
                    Swal.fire({
                        title: 'Проверка лимитов...',
                        html: `Проверено ${checked} из ${tokens.length} токенов`,
                        allowOutsideClick: false,
                        didOpen: () => {
                            Swal.showLoading();
                            
                            tokens.forEach(tokenObj => {
                                fetch('/api/reserve_tokens/check_limits', {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json',
                                    },
                                    body: JSON.stringify({ 
                                        king: king, 
                                        token: tokenObj.token 
                                    })
                                })
                                .finally(() => {
                                    checked++;
                                    Swal.getHtmlContainer().innerHTML = 
                                        `Проверено ${checked} из ${tokens.length} токенов`;
                                    
                                    if (checked === tokens.length) {
                                        Swal.close();
                                        Swal.fire('Успех', `Проверено ${tokens.length} токенов`, 'success');
                                        loadCombinedTokensTable();
                                    }
                                });
                            });
                        }
                    });
                }
            });
        }
    });
}


function saveTokenChanges(king, oldToken, tokenInputId, accountsInputId) {
    const newToken = document.getElementById(tokenInputId).value.trim();
    const accountsInput = document.getElementById(accountsInputId).value.trim();

    if (!newToken && !accountsInput) {
        Swal.fire('Ошибка', 'Введите изменения для сохранения', 'error');
        return;
    }

    const account_ids = accountsInput ? accountsInput.split(',').map(id => id.trim()).filter(id => id) : [];
    const finalToken = newToken || oldToken;

    const data = { 
        king, 
        oldToken,
        newToken: finalToken,
        account_ids: account_ids.length > 0 ? account_ids : undefined
    };

    fetch('/api/update_token_complete', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            Swal.fire('Успех', result.message, 'success');
            loadCombinedTokensTable();
        } else {
            Swal.fire('Ошибка', result.error, 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка', 'Ошибка сети', 'error');
    });
}

function saveTokenFromCollapse(oldKing, oldToken, kingInputId, tokenInputId, accountsInputId) {
    console.log('Сохранение изменений:', { oldKing, oldToken, kingInputId, tokenInputId, accountsInputId });
    
    const newKing = document.getElementById(kingInputId).value.trim();
    const newToken = document.getElementById(tokenInputId).value.trim();
    const accountsText = document.getElementById(accountsInputId).value;
    
    console.log('Полученные значения:', { newKing, newToken, accountsText });
    
    if (!newKing) {
        Swal.fire('Ошибка', 'Введите KING', 'error');
        return;
    }
    if (!newToken) {
        Swal.fire('Ошибка', 'Введите токен', 'error');
        return;
    }
    

    const accounts = accountsText.split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0);
    
    console.log('Обработанные аккаунты:', accounts);
    
 
    const normalizedAccounts = accounts.map(account => {
        let cleanId = account.trim();
        
   
        if (cleanId.toLowerCase().startsWith('act_')) {
            cleanId = cleanId.substring(4);
        }
        
       
        cleanId = cleanId.replace(/\D/g, '');
        
      
        return cleanId ? `act_${cleanId}` : '';
    }).filter(a => a);
    
    console.log('Нормализованные аккаунты:', normalizedAccounts);
    
   
    Swal.fire({
        title: 'Сохранение...',
        text: 'Пожалуйста, подождите',
        allowOutsideClick: false,
        didOpen: () => {
            Swal.showLoading();
        }
    });
    
   
    fetch('/api/update_token_complete', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
            oldKing: oldKing,
            newKing: newKing,
            oldToken: oldToken,
            newToken: newToken,
            account_ids: normalizedAccounts
        })
    })
    .then(response => {
        console.log('Ответ сервера:', response);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(result => {
        console.log('Результат сохранения:', result);
        
        Swal.close();
        
        if (result.success) {
            Swal.fire({
                title: 'Успех!',
                text: result.message,
                icon: 'success',
                timer: 2000,
                showConfirmButton: false
            }).then(() => {
              
                const collapseElement = document.querySelector('.collapse.show');
                if (collapseElement) {
                    const bsCollapse = new bootstrap.Collapse(collapseElement);
                    bsCollapse.hide();
                }
           
                loadCombinedTokensTable();
            });
        } else {
            Swal.fire('Ошибка', result.error || 'Неизвестная ошибка', 'error');
        }
    })
    .catch(error => {
        console.error('Ошибка при сохранении:', error);
        Swal.close();
        Swal.fire('Ошибка', 'Ошибка сети: ' + error.message, 'error');
    });
}

function debugElements() {
    console.log('=== ДЕБАГ ЭЛЕМЕНТОВ ===');
    console.log('Все элементы с ID:');
    document.querySelectorAll('[id]').forEach(el => {
        console.log(`ID: ${el.id}, Tag: ${el.tagName}`);
    });
    
    console.log('Все textarea:');
    document.querySelectorAll('textarea').forEach((ta, index) => {
        console.log(`Textarea ${index}:`, ta.id, ta.value);
    });
    
    console.log('Все input:');
    document.querySelectorAll('input').forEach((input, index) => {
        console.log(`Input ${index}:`, input.id, input.value);
    });
}

function updateAccountCount(accountsInputId, countElementId) {
    const accountsText = document.getElementById(accountsInputId).value;
    const accounts = accountsText.split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0);
    
    const normalizedAccounts = accounts.map(account => {
        let cleanId = account.trim();
        if (cleanId.toLowerCase().startsWith('act_')) {
            cleanId = cleanId.substring(4);
        }
        cleanId = cleanId.replace(/\D/g, '');
        return cleanId ? `act_${cleanId}` : '';
    }).filter(a => a);
    
    document.getElementById(countElementId).textContent = `${normalizedAccounts.length} аккаунтов`;
    
    Swal.fire({
        title: 'Счетчик обновлен',
        text: `Найдено ${normalizedAccounts.length} аккаунтов`,
        icon: 'success',
        timer: 1500,
        showConfirmButton: false
    });
}


function addSampleAccountsToEdit(accountsInputId) {
    const sampleAccounts = [
        '123456789',
        '987654321',
        '1122334455',
        '5566778899',
        '9988776655'
    ];
    
    document.getElementById(accountsInputId).value = sampleAccounts.join('\n');
    

    Swal.fire({
        title: 'Добавлены примеры',
        text: '5 примеров аккаунтов добавлено',
        icon: 'success',
        timer: 1500,
        showConfirmButton: false
    });
}


function clearEditAccounts(accountsInputId) {
    document.getElementById(accountsInputId).value = '';
    
    Swal.fire({
        title: 'Очищено',
        text: 'Список аккаунтов очищен',
        icon: 'info',
        timer: 1500,
        showConfirmButton: false
    });
}
function renderCombinedTokensTable(tokens) {
    console.log('Rendering combined tokens table with data:', tokens);
    const tbody = document.querySelector('#tokensTable tbody');
    tbody.innerHTML = '';

    if (!tokens || Object.keys(tokens).length === 0) {
        console.log('No combined tokens data, rendering empty table');
        renderEmptyTable();
        return;
    }

    let hasData = false;

    for (const [king, tokenList] of Object.entries(tokens)) {
        if (!tokenList || tokenList.length === 0) continue;
        
        hasData = true;

   
        const groupHeader = document.createElement('tr');
        groupHeader.className = 'group-header';
        groupHeader.innerHTML = `
            <td colspan="7" class="bg-light">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <span class="badge bg-primary fs-6">KING: ${king}</span>
                        <span class="badge bg-secondary ms-2">${tokenList.length} токенов</span>
                    </div>
                    <div>
                        <button class="btn btn-sm btn-success me-2" onclick="showAddTokenToGroupModal('${king}')">
                            <i class="bi bi-plus-circle"></i> Добавить токен
                        </button>
                        <button class="btn btn-sm btn-primary me-2" onclick="checkGroupLimits('${king}')">
                            <i class="bi bi-arrow-repeat"></i> Проверить
                        </button>
                    </div>
                </div>
            </td>
        `;
        tbody.appendChild(groupHeader);

      
        tokenList.forEach((tokenObj, index) => {
            if (!tokenObj || !tokenObj.token) return;

            const accounts = tokenObj.accounts || [];
            const accountDetails = accounts.map(acc =>
                `<span class="badge bg-info me-1 mb-1">${acc.account_id}</span>`
            ).join('');

            const rowId = `collapse_${king}_${index}`;

            const tr = document.createElement('tr');
            tr.className = 'token-row';
            tr.innerHTML = `
                <td class="king-cell">
                    <span class="badge bg-primary">${king}</span>
                </td>
                <td class="token-cell">
                    <div class="d-flex align-items-center">
                        <div class="token-preview" title="${tokenObj.token}">
                            ${tokenObj.token.substring(0, 20)}${tokenObj.token.length > 20 ? '...' : ''}
                        </div>
                        <button class="btn btn-sm btn-outline-secondary ms-2" onclick="copyToClipboard('${tokenObj.token}')">
                            <i class="bi bi-copy"></i>
                        </button>
                    </div>
                </td>
                <td class="accounts-cell">
                    ${accountDetails || '<span class="text-muted">нет аккаунтов</span>'}
                </td>
                <td class="limit-cell text-center">
                    <span class="badge bg-light text-dark">${tokenObj.requests_limit || 100}</span>
                </td>
                <td class="usage-cell text-center">
                    <span class="badge bg-light text-dark">${tokenObj.requests_today || 0}</span>
                </td>
                <td class="progress-cell">
                    <div class="progress" style="height: 20px;">
                        <div class="progress-bar ${getProgressBarClass(tokenObj.requests_usage_percent || 0)}" 
                             role="progressbar" style="width: ${Math.min(tokenObj.requests_usage_percent || 0, 100)}%">
                            ${tokenObj.requests_usage_percent || 0}%
                        </div>
                    </div>
                </td>
                <td class="actions-cell">
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-primary" 
                                data-bs-toggle="collapse" 
                                data-bs-target="#${rowId}"
                                title="Редактировать">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-outline-info" onclick="checkTokenLimits('${king}', '${tokenObj.token}')"
                                title="Проверить лимиты">
                            <i class="bi bi-arrow-repeat"></i>
                        </button>
                        <button class="btn btn-outline-danger" onclick="deleteReserveToken('${king}', '${tokenObj.token}')"
                                title="Удалить токен">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);

         
            const collapseTr = document.createElement('tr');
            collapseTr.className = 'collapse-row';
            collapseTr.innerHTML = `
                <td colspan="7" class="p-0">
                    <div class="collapse" id="${rowId}">
                        <div class="card m-2 border-primary">
                            <div class="card-header bg-primary text-white">
                                <h6 class="card-title mb-0">
                                    <i class="bi bi-gear"></i> Редактирование токена - ${king}
                                </h6>
                            </div>
                            <div class="card-body">
                                <div class="row">
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label"><strong>KING:</strong></label>
                                            <input type="text" class="form-control" id="editKing_${king}_${index}" 
                                                   value="${king}" placeholder="Введите KING">
                                            <small class="text-muted">Группа токена</small>
                                        </div>
                                        
                                        <div class="mb-3">
                                            <label class="form-label"><strong>Токен:</strong></label>
                                            <textarea class="form-control" id="editToken_${king}_${index}" rows="4" 
                                                      placeholder="Введите токен">${tokenObj.token}</textarea>
                                        </div>
                                    </div>
                                    
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label"><strong>Аккаунты (каждый с новой строки):</strong></label>
                                            <textarea class="form-control" id="editAccounts_${king}_${index}" rows="8" 
                                                      placeholder="Введите ID аккаунтов, каждый с новой строки\nТолько цифры, без act_">${accounts.map(acc => acc.account_id.replace('act_', '')).join('\n')}</textarea>
                                            <small class="text-muted">Один ID аккаунта на строку</small>
                                        </div>
                                        
                                        <div class="d-flex justify-content-between align-items-center">
                                            <span class="badge bg-info" id="accountCount_${king}_${index}">${accounts.length} аккаунтов</span>
                                            <div>
                                                <button type="button" class="btn btn-sm btn-outline-secondary me-2" 
                                                        onclick="addSampleAccountsToEdit('editAccounts_${king}_${index}')">
                                                    <i class="bi bi-magic"></i> Пример
                                                </button>
                                                <button type="button" class="btn btn-sm btn-outline-secondary" 
                                                        onclick="clearEditAccounts('editAccounts_${king}_${index}')">
                                                    <i class="bi bi-trash"></i> Очистить
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="d-flex gap-2 mt-3">
                                    <button class="btn btn-success" 
                                            onclick="saveTokenFromCollapse('${king}', '${tokenObj.token}', 'editKing_${king}_${index}', 'editToken_${king}_${index}', 'editAccounts_${king}_${index}')">
                                        <i class="bi bi-check-circle"></i> Сохранить
                                    </button>
                                    <button class="btn btn-secondary" data-bs-toggle="collapse" data-bs-target="#${rowId}">
                                        <i class="bi bi-x-circle"></i> Отмена
                                    </button>
                                    <button class="btn btn-info" 
                                            onclick="updateAccountCount('editAccounts_${king}_${index}', 'accountCount_${king}_${index}')">
                                        <i class="bi bi-arrow-clockwise"></i> Обновить счетчик
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </td>
            `;
            tbody.appendChild(collapseTr);
        });
    }

  
    const addGroupRow = document.createElement('tr');
    addGroupRow.innerHTML = `
        <td colspan="7" class="text-center py-4">
            <div class="card border-dashed">
                <div class="card-body">
                    <h5 class="card-title text-muted">
                        <i class="bi bi-plus-lg"></i> Новая группа токенов
                    </h5>
                    <p class="card-text text-muted">Создайте новую группу с общим KING</p>
                    <button class="btn btn-primary btn-lg" onclick="showAddGroupModal()">
                        <i class="bi bi-plus-circle"></i> Создать группу
                    </button>
                </div>
            </div>
        </td>
    `;
    tbody.appendChild(addGroupRow);

    if (!hasData) {
        renderEmptyTable();
    }
}
function getProgressBarClass(percent) {
    if (percent >= 90) return 'bg-danger';
    if (percent >= 70) return 'bg-warning';
    if (percent >= 50) return 'bg-info';
    return 'bg-success';
}


function addAutoPopulateButton() {
    const header = document.querySelector('.d-flex.justify-content-between');
    if (header) {
        const button = document.createElement('button');
        button.className = 'btn btn-warning me-2';
        button.innerHTML = '<i class="bi bi-magic"></i> Автозаполнение';
        button.onclick = autoPopulateReserveTokens;
        header.querySelector('div').prepend(button);
    }
}

function autoPopulateReserveTokens() {
    Swal.fire({
        title: 'Автозаполнение резервных токенов',
        text: 'Создать резервные токены из основных аккаунтов?',
        icon: 'question',
        showCancelButton: true,
        confirmButtonText: 'Да, создать',
        cancelButtonText: 'Отмена'
    }).then((result) => {
        if (result.isConfirmed) {
            fetch('/api/auto_populate_reserve_tokens', {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    Swal.fire('Успех', data.message, 'success');
                    loadCombinedTokensTable();
                    loadReserveTokens();
                } else {
                    Swal.fire('Ошибка', data.error || 'Ошибка автозаполнения', 'error');
                }
            })
            .catch(error => {
                Swal.fire('Ошибка', 'Ошибка сети', 'error');
            });
        }
    });
}



function deleteReserveToken(king, token) {
    Swal.fire({
        title: 'Удалить резервный токен?',
        text: `Токен для KING "${king}" будет удален`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Да, удалить',
        cancelButtonText: 'Отмена'
    }).then((result) => {
        if (result.isConfirmed) {
            fetch('/api/user/reserve_tokens', {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ king: king, token: token })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    Swal.fire('Успех', 'Резервный токен удален', 'success');
                    loadCombinedTokensTable();
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
function addNewReserveTokenRow() {
    const tbody = document.querySelector('#tokensTable tbody');
    const newRow = document.createElement('tr');
    newRow.innerHTML = `
        <td contenteditable="true" class="editable-cell"></td>
        <td contenteditable="true" class="editable-cell"></td>
        <td contenteditable="true" class="editable-cell"></td>
        <td>-</td>
        <td>-</td>
        <td>-</td>
        <td>
            <button class="btn btn-sm btn-success" onclick="addReserveTokenFromRow(this)">
                <i class="bi bi-plus"></i> Добавить резерв
            </button>
        </td>
    `;
    tbody.appendChild(newRow);
}

function addReserveTokenFromRow(button) {
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
    
    fetch('/api/user/reserve_tokens', {
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
            Swal.fire('Успех', 'Резервный токен успешно добавлен', 'success');
            loadCombinedTokensTable();
            loadReserveTokens();
        } else {
            Swal.fire('Ошибка', data.error || 'Ошибка добавления резервного токена', 'error');
        }
    })
    .catch(error => {
        Swal.fire('Ошибка', 'Ошибка сети', 'error');
    });
}
function loadTokensTable() {
    console.log('Loading tokens table...');
    fetch('/api/user/reserve_tokens/table')
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
            
      
            const allTokensForKing = tokenList.map(t => t.token);
            
            console.log('Token:', tokenObj.token, 'King:', king, 'Accounts:', accounts.length);
            
            const requestsLimit = accounts.length > 0 ? accounts[0].requests_limit || 100 : 100;
            const requestsToday = accounts.length > 0 ? accounts[0].requests_today || 0 : 0;
            const requestsPercent = accounts.length > 0 ? accounts[0].requests_usage_percent || 0 : 0;
            
            const row = document.createElement('tr');
            row.innerHTML = `
                <td contenteditable="true" class="editable-cell">${king}</td>
                <td>
                    <select class="form-select form-select-sm token-select" onchange="updateTokenSelection(this, '${king}')">
                        ${allTokensForKing.map(token => `
                            <option value="${token}" ${token === tokenObj.token ? 'selected' : ''}>${token}</option>
                        `).join('')}
                        <option value="add_new">+ Добавить новый токен</option>
                    </select>
                </td>
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
                <p class="mt-2">Нет данных о токенах</p>
                <small>Добавьте токены через автозаполнение или вручную</small>
            </td>
        </tr>
    `;
}


function loadTokensForKing(king, callback) {
    if (!king) {
        callback([]);
        return;
    }
    
    fetch(`/api/reserve_tokens/${encodeURIComponent(king)}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                callback(data.tokens);
            } else {
                console.error('Error loading tokens for king:', data.error);
                callback([]);
            }
        })
        .catch(error => {
            console.error('Error loading tokens:', error);
            callback([]);
        });
}

function updateTokenDropdowns() {
    const kingCells = document.querySelectorAll('#tokensTable td:first-child.editable-cell');
    
    kingCells.forEach(cell => {
        const king = cell.textContent.trim();
        if (king) {
            const row = cell.closest('tr');
            const select = row.querySelector('.token-select');
            
            if (select) {
                loadTokensForKing(king, (tokens) => {
                 
                    const currentValue = select.value;
                    
              
                    select.innerHTML = tokens.map(token => `
                        <option value="${token}" ${token === currentValue ? 'selected' : ''}>${token}</option>
                    `).join('') + '<option value="add_new">+ Добавить новый токен</option>';
                });
            }
        }
    });
}

document.addEventListener('DOMContentLoaded', function() {
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'characterData' || mutation.type === 'childList') {
                const target = mutation.target;
                if (target.classList && target.classList.contains('editable-cell')) {
                    setTimeout(updateTokenDropdowns, 100);
                }
            }
        });
    });
    
    const config = { characterData: true, childList: true, subtree: true };
    observer.observe(document.getElementById('tokensTable'), config);
});

function addNewRow() {
    const tbody = document.querySelector('#tokensTable tbody');
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
    
    
    const finalKing = determineKingAutomatically(king, token);
    
    const account_ids = accountIds ? accountIds.split(',').map(id => id.trim()).filter(id => id) : [];
    
    fetch('/api/user/reserve_tokens', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
            king: finalKing, 
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

function addNewToken(data) {
    const account_ids = data.accounts ? data.accounts.split(',').map(id => id.trim()).filter(id => id) : [];
    
    fetch('/api/user/reserve_tokens', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
            king: data.king, 
            token: data.token,
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


function showAddTokenModal(king) {
    Swal.fire({
        title: 'Добавить новый токен',
        html: `
            <div class="mb-3">
                <label class="form-label">KING:</label>
                <input type="text" class="form-control" id="newTokenKing" value="${king}" readonly>
            </div>
            <div class="mb-3">
                <label class="form-label">Токен:</label>
                <textarea class="form-control" id="newTokenValue" rows="3" placeholder="Введите новый токен"></textarea>
            </div>
            <div class="mb-3">
                <label class="form-label">Аккаунты (через запятую):</label>
                <input type="text" class="form-control" id="newTokenAccounts" placeholder="act_123456789, act_987654321">
            </div>
        `,
        showCancelButton: true,
        confirmButtonText: 'Добавить',
        cancelButtonText: 'Отмена',
        preConfirm: () => {
            const token = document.getElementById('newTokenValue').value.trim();
            const accounts = document.getElementById('newTokenAccounts').value.trim();
            
            if (!token) {
                Swal.showValidationMessage('Введите токен');
                return false;
            }
            
            return { king, token, accounts };
        }
    }).then((result) => {
        if (result.isConfirmed) {
            addNewToken(result.value);
        }
    });
}

function updateTokenSelection(select, king) {
    if (select.value === 'add_new') {
      
        showAddTokenModal(king);
     
        setTimeout(() => {
            select.value = select.dataset.prevValue || '';
        }, 100);
    } else {
        select.dataset.prevValue = select.value;
    }
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
            fetch('/api/user/reserve_tokens', {
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
    
    fetch('/api/user/reserve_tokens')
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
            fetch('/api/reserve_tokens/delete', {
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
            fetch('/api/user/reserve_tokens', {
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

function determineKingAutomatically(kingInput, token) {
 
    if (kingInput && kingInput.trim() !== '') {
        return kingInput.trim();
    }
    
   
    if (token.includes('EA') || token.length > 100) {
        return 'Facebook_Long';
    } else if (token.includes('IG') || token.length > 50) {
        return 'Instagram';
    } else if (token.includes('TT') || token.length > 40) {
        return 'TikTok';
    } else {
        return 'Facebook_Default';
    }
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
