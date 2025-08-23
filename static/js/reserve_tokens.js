document.addEventListener('DOMContentLoaded', function() {
    // Загрузка токенов при открытии страницы
    loadReserveTokens();
    
    // Обработчик формы добавления токена
    document.getElementById('addTokenForm').addEventListener('submit', function(e) {
        e.preventDefault();
        
        const king = document.getElementById('kingInput').value.trim();
        const token = document.getElementById('tokenInput').value.trim();
        
        if (!king || !token) {
            Swal.fire('Ошибка', 'Заполните все поля', 'error');
            return;
        }
        
        addReserveToken(king, token);
    });
});

// Загрузка резервных токенов
function loadReserveTokens() {
    fetch('/api/reserve_tokens')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                renderTokensTable(data.tokens);
            } else {
                Swal.fire('Ошибка', data.error || 'Ошибка загрузки токенов', 'error');
            }
        })
        .catch(error => {
            console.error('Ошибка загрузки токенов:', error);
            Swal.fire('Ошибка', 'Ошибка сети', 'error');
        });
}

// Отображение токенов в таблице
function renderTokensTable(tokens) {
    const tbody = document.getElementById('tokensTable');
    
    if (!tokens || Object.keys(tokens).length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" class="text-center text-muted py-4">
                    <i class="bi bi-inbox fs-1"></i>
                    <p class="mt-2">Нет резервных токенов</p>
                    <small>Добавьте токены через форму выше</small>
                </td>
            </tr>
        `;
        return;
    }
    
    let html = '';
    let tokenCount = 0;
    
    for (const [king, tokenList] of Object.entries(tokens)) {
        tokenList.forEach(tokenObj => {
            tokenCount++;
            html += `
                <tr>
                    <td><span class="badge bg-primary">${king}</span></td>
                    <td>
                        <div class="token-preview">
                            ${tokenObj.token.substring(0, 20)}...
                            <button class="btn btn-sm btn-outline-secondary ms-2" 
                                    onclick="copyToClipboard('${tokenObj.token}')">
                                <i class="bi bi-copy"></i>
                            </button>
                        </div>
                    </td>
                    <td>${new Date(tokenObj.created_at).toLocaleDateString()}</td>
                    <td>
                        <button class="btn btn-sm btn-danger" 
                                onclick="deleteToken('${king}', '${tokenObj.token}')">
                            <i class="bi bi-trash"></i> Удалить
                        </button>
                    </td>
                </tr>
            `;
        });
    }
    
    tbody.innerHTML = html;
    
    // Обновляем заголовок с количеством
    const header = document.querySelector('.card-header h5');
    if (header) {
        header.innerHTML = `<i class="bi bi-list"></i> Список резервных токенов (${tokenCount})`;
    }
}

// Добавление резервного токена
function addReserveToken(king, token) {
    const btn = document.querySelector('#addTokenForm button[type="submit"]');
    const originalText = btn.innerHTML;
    
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Добавление...';
    
    fetch('/api/reserve_tokens', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ king, token })
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

// Удаление резервного токена
function deleteToken(king, token) {
    Swal.fire({
        title: 'Вы уверены?',
        text: `Удалить токен для KING "${king}"?`,
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
                body: JSON.stringify({ king, token })
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

// Копирование токена в буфер обмена
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        Swal.fire({
            icon: 'success',
            title: 'Скопировано!',
            text: 'Токен скопирован в буфер обмена',
            timer: 1500,
            showConfirmButton: false
        });
    }).catch(err => {
        Swal.fire('Ошибка', 'Не удалось скопировать токен', 'error');
    });
}

// Стиль для анимации спиннера
const style = document.createElement('style');
style.textContent = `
    .spin { animation: spin 1s linear infinite; }
    @keyframes spin { 100% { transform: rotate(360deg); } }
    .token-preview { display: flex; align-items: center; }
`;
document.head.appendChild(style);