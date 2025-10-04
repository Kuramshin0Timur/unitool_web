document.addEventListener('DOMContentLoaded', function() {
    const importForm = document.getElementById('facebookImportForm');
    const testBtn = document.getElementById('testFacebookConnection');
    const importBtn = document.getElementById('importFacebookData');
    
    if (testBtn) {
        testBtn.addEventListener('click', testFacebookConnection);
    }
    
    if (importBtn) {
        importBtn.addEventListener('click', importFacebookData);
    }
    
    function testFacebookConnection() {
        const accountId = document.getElementById('facebookAccountId').value;
        const accessToken = document.getElementById('facebookAccessToken').value;
        
        if (!accountId || !accessToken) {
            Swal.fire('Ошибка', 'Заполните все поля', 'error');
            return;
        }
        
        // Проверяем формат account_id
        if (!accountId.startsWith('act_')) {
            Swal.fire('Ошибка', 'Account ID должен начинаться с "act_"', 'error');
            return;
        }
        
        showLoading(testBtn, 'Тестирование...');
        
        fetch('/api/test_facebook_connection', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                account_id: accountId,
                access_token: accessToken
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                Swal.fire({
                    title: 'Успех!',
                    html: `
                        <p>${data.message}</p>
                        <p><strong>Аккаунт:</strong> ${data.account_name}</p>
                        <p><strong>Статус:</strong> ${data.account_status}</p>
                    `,
                    icon: 'success'
                });
            } else {
                Swal.fire('Ошибка', data.error, 'error');
            }
        })
        .catch(error => {
            Swal.fire('Ошибка', 'Ошибка сети: ' + error, 'error');
        })
        .finally(() => {
            hideLoading(testBtn, 'Тестировать соединение');
        });
    }
    
    function importFacebookData() {
        const accountId = document.getElementById('facebookAccountId').value;
        const accessToken = document.getElementById('facebookAccessToken').value;
        
        if (!accountId || !accessToken) {
            Swal.fire('Ошибка', 'Заполните все поля', 'error');
            return;
        }
        
        Swal.fire({
            title: 'Вы уверены?',
            text: 'Это импортирует все кампании и адсеты из выбранного аккаунта',
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Да, импортировать',
            cancelButtonText: 'Отмена'
        }).then((result) => {
            if (result.isConfirmed) {
                showLoading(importBtn, 'Импорт...');
                
                fetch('/api/fetch_facebook_data', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        account_id: accountId,
                        access_token: accessToken
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        Swal.fire(
                            'Успех!',
                            data.message,
                            'success'
                        ).then(() => {
                            // Обновляем таблицы
                            if (typeof window.campaignsTable !== 'undefined') {
                                window.campaignsTable.ajax.reload();
                            }
                            if (typeof loadAdsets === 'function') {
                                loadAdsets();
                            }
                        });
                    } else {
                        Swal.fire('Ошибка', data.error, 'error');
                    }
                })
                .catch(error => {
                    Swal.fire('Ошибка', 'Ошибка сети: ' + error, 'error');
                })
                .finally(() => {
                    hideLoading(importBtn, 'Импортировать данные');
                });
            }
        });
    }
    
    function showLoading(button, text) {
        button.disabled = true;
        button.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${text}`;
    }
    
    function hideLoading(button, text) {
        button.disabled = false;
        button.innerHTML = text;
    }
});