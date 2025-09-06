$(document).ready(function() {
    $('#importFacebookBtn').click(function() {
        const accountId = $('#facebookAccountId').val();
        const accessToken = $('#facebookAccessToken').val();
        
        if (!accountId || !accessToken) {
            addLog('Заполните Account ID и Access Token', 'error');
            return;
        }
        
        showLoading($('#importFacebookBtn'), 'Импорт...');
        
        $.ajax({
            url: '/api/manual_import_bulk',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                accounts: [[accountId, accessToken]]
            }),
            success: function(response) {
                if (response.success) {
                    addLog(`Успешно импортировано: ${response.total_campaigns} кампаний, ${response.total_adsets} адсетов`);
                    Swal.fire('Успех!', response.message, 'success');
                    
                    if (typeof window.campaignsTable !== 'undefined') {
                        window.campaignsTable.ajax.reload();
                    }
                    if (typeof loadAdsets === 'function') {
                        loadAdsets();
                    }
                } else {
                    addLog('Ошибка импорта: ' + response.error, 'error');
                    Swal.fire('Ошибка!', response.error, 'error');
                }
            },
            error: function(xhr) {
                addLog('Ошибка запроса: ' + xhr.statusText, 'error');
                Swal.fire('Ошибка!', 'Ошибка сети: ' + xhr.statusText, 'error');
            },
            complete: function() {
                hideLoading($('#importFacebookBtn'), 'Импорт из Facebook');
            }
        });
    });

    $('#testFacebookBtn').click(function() {
        const accountId = $('#facebookAccountId').val();
        const accessToken = $('#facebookAccessToken').val();
        
        if (!accountId || !accessToken) {
            addLog('Заполните Account ID и Access Token', 'error');
            return;
        }
        
        showLoading($('#testFacebookBtn'), 'Тестирование...');
        
        $.ajax({
            url: '/api/test_facebook_connection',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                account_id: accountId,
                access_token: accessToken
            }),
            success: function(response) {
                if (response.success) {
                    addLog('Соединение с Facebook успешно установлено');
                    Swal.fire('Успех!', response.message, 'success');
                } else {
                    addLog('Ошибка соединения: ' + response.error, 'error');
                    Swal.fire('Ошибка!', response.error, 'error');
                }
            },
            error: function(xhr) {
                addLog('Ошибка запроса: ' + xhr.statusText, 'error');
                Swal.fire('Ошибка!', 'Ошибка сети: ' + xhr.statusText, 'error');
            },
            complete: function() {
                hideLoading($('#testFacebookBtn'), 'Тестировать соединение');
            }
        });
    });

    function showLoading(button, text) {
        button.prop('disabled', true);
        button.html(`<span class="spinner-border spinner-border-sm" role="status"></span> ${text}`);
    }
    
    function hideLoading(button, text) {
        button.prop('disabled', false);
        button.text(text);
    }
    
    function addLog(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const logClass = type === 'error' ? 'text-danger' : 'text-success';
        const logEntry = `<div class="log-entry ${logClass}">[${timestamp}] ${message}</div>`;
        $('#logContent').prepend(logEntry);
        $('#logContent').scrollTop(0);
    }
});

document.addEventListener('DOMContentLoaded', function() {
    const container = document.getElementById('hot');
    if (!container) {
        console.error('Контейнер для таблицы не найден');
        return;
    }

    const hot = new Handsontable(container, {
        data: [['', '']], 
        colHeaders: ['ID аккаунта', 'Токен'],
        columns: [
            { type: 'text' }, // ID аккаунта
            { type: 'text' }  // Токен
        ],
        rowHeaders: true,
        contextMenu: true,
        licenseKey: 'non-commercial-and-evaluation',
        width: '100%',
        height: 400,
        minSpareRows: 1,
        afterChange: function(changes, source) {
            if (source === 'edit') {
                console.log('Изменения:', changes);
            }
        }
    });

    document.getElementById('addRowBtn')?.addEventListener('click', function() {
        hot.alter('insert_row');
    });

    document.getElementById('saveData')?.addEventListener('click', function() {
        hot.validateCells(() => {});
        hot.render();

        const data = hot.getSourceData();
        console.log('Данные для сохранения:', data);
        
        const filteredData = data.filter(row => 
            row && row[0] !== null && row[0] !== "" &&
            row[1] !== null && row[1] !== ""
        );

        console.log(`Строк для отправки: ${filteredData.length}`, filteredData);

        if (filteredData.length === 0) {
            alert('Нет данных для сохранения!');
            return;
        }

        const saveBtn = document.getElementById('saveData');
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Импорт...';

        const payload = filteredData.map(row => ({
            account_id: row[0],
            token: row[1]
        }));

        fetch('/api/manual_import_bulk', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ accounts: payload })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(`Импортировано: ${data.total_campaigns} кампаний, ${data.total_adsets} адсетов`);
                hot.loadData([...filteredData, ['', '']]); // Обновляем таблицу
            } else {
                alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
            }
        })
        .catch(error => {
            alert('Ошибка сети: ' + error);
        })
        .finally(() => {
            saveBtn.disabled = false;
            saveBtn.innerHTML = '<i class="bi bi-save"></i> Сохранить';
        });

    });

    const style = document.createElement('style');
    style.textContent = `
        .spin { animation: spin 1s linear infinite; }
        @keyframes spin { 
            100% { transform: rotate(360deg); } 
        }
    `;
    document.head.appendChild(style);
});
