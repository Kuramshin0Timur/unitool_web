document.addEventListener('DOMContentLoaded', function() {
    let hot;
    
    loadExistingAccounts();
    
    function loadExistingAccounts() {
        fetch('/api/accounts')
            .then(response => response.json())
            .then(data => {
                if (data.success && data.accounts && data.accounts.length > 0) {
                    const tableData = data.accounts.map(account => [
                        account.account_id || '',
                        account.token || ''
                    ]);
                    
                    tableData.push(['', '']);
                    
                    initHandsontable(tableData);
                } else {
                    initHandsontable([['', '']]);
                }
            })
            .catch(error => {
                console.error('Ошибка загрузки аккаунтов:', error);
                initHandsontable([['', '']]);
            });
    }
    
    function initHandsontable(initialData) {
        const container = document.getElementById('hot');
        if (!container) {
            console.error('Контейнер для таблицы не найден');
            return;
        }

        hot = new Handsontable(container, {
            data: initialData,
            colHeaders: ['ID аккаунта', 'Токен'],
            columns: [
                { 
                    type: 'text',
                    validator: function(value, callback) {
                        if (!value || value.toString().trim() === '') {
                            callback(true);
                        } else {
                            const cleanValue = value.toString().replace('act_', '');
                            const isValid = /^\d+$/.test(cleanValue);
                            callback(isValid);
                        }
                    }
                },
                { 
                    type: 'text',
                    validator: function(value, callback) {
                        if (!value || value.toString().trim() === '') {
                            callback(true);
                        } else {
                            const isValid = value.toString().includes('EAAG') || 
                                        value.toString().includes('EAAN') ||
                                        value.toString().includes('EAA');
                            callback(isValid);
                        }
                    }
                }
            ],
            rowHeaders: true,
            contextMenu: true,
            licenseKey: 'non-commercial-and-evaluation',
            width: '100%',
            height: 400,
            minSpareRows: 1,
            manualColumnResize: true,
            manualRowResize: true,
            columnSorting: true,
            filters: true,
            dropdownMenu: true,
            afterChange: function(changes, source) {
                if (source === 'edit') {
                    validateAndHighlightRows();
                }
            },
            cells: function(row, col, prop) {
                const cellProperties = {};
                const data = this.instance.getData();
                
                if (data[row] && data[row][col]) {
                    const value = data[row][col].toString();
                    
                    if (col === 0 && value && value !== '') {
                        const cleanValue = value.replace('act_', '');
                        if (!/^\d+$/.test(cleanValue)) {
                            cellProperties.className = 'invalid-cell';
                        }
                    }
                    
                    if (col === 1 && value && value !== '') {
                        if (!value.includes('EAAG') && !value.includes('EAAN')) {
                            cellProperties.className = 'invalid-cell';
                        }
                    }
                }
                
                return cellProperties;
            }
        });

        document.getElementById('addRowBtn')?.addEventListener('click', function() {
            hot.alter('insert_row');
            validateAndHighlightRows();
        });

        document.getElementById('clearBtn')?.addEventListener('click', function() {
            if (confirm('Очистить всю таблицу? Все данные будут удалены.')) {
                hot.loadData([['', '']]);
                validateAndHighlightRows();
            }
        });

        document.getElementById('saveData')?.addEventListener('click', function() {
            const data = hot.getData();
            
            const filteredData = data.filter(row => 
                row[0] && row[0].toString().trim() !== '' && 
                row[1] && row[1].toString().trim() !== ''
            );
            
            if (filteredData.length === 0) {
                alert('Нет данных для сохранения! Заполните хотя бы одну строку с ID аккаунта и Токеном.');
                return;
            }

            const saveBtn = document.getElementById('saveData');
            const originalText = saveBtn.innerHTML;
            saveBtn.disabled = true;
            saveBtn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Сохранение...';

            const accountsToSave = filteredData.map(row => ({
                account_id: row[0].toString().trim().replace('act_', ''),
                token: row[1].toString().trim()
            }));

            fetch('/api/save_and_sync', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ accounts: accountsToSave })
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    Swal.fire({
                        icon: 'success',
                        title: 'Успех!',
                        html: `Синхронизировано:<br>
                            <strong>${data.saved_accounts || 0}</strong> аккаунтов<br>
                            <strong>${data.total_campaigns || 0}</strong> кампаний<br>
                            <strong>${data.total_adsets || 0}</strong> адсетов`,
                        timer: 5000,
                        showConfirmButton: true
                    });
                    
                    hot.loadData([['', '']]);
                    validateAndHighlightRows();
                    
                    if (typeof window.campaignsTable !== 'undefined') {
                        setTimeout(() => window.campaignsTable.ajax.reload(null, false), 2000);
                    }
                    if (typeof loadAdsets === 'function') {
                        setTimeout(loadAdsets, 2000);
                    }
                    
                } else {
                    throw new Error(data.error || 'Неизвестная ошибка сервера');
                }
            })
            .catch(error => {
                Swal.fire({
                    icon: 'error',
                    title: 'Ошибка!',
                    html: `Не удалось сохранить данные:<br><strong>${error.message}</strong><br><br>
                        Проверьте:<br>
                        - Правильность ID аккаунта и токена<br>
                        - Доступность Facebook API<br>
                        - Соединение с интернетом`,
                    confirmButtonText: 'Понятно'
                });
            })
            .finally(() => {
                saveBtn.disabled = false;
                saveBtn.innerHTML = originalText;
            });
        });

        document.getElementById('testConnection')?.addEventListener('click', function() {
            const data = hot.getData();
            const filteredData = data.filter(row => 
                row[0] && row[0].toString().trim() !== '' && 
                row[1] && row[1].toString().trim() !== ''
            );
            
            if (filteredData.length === 0) {
                alert('Нет данных для тестирования! Заполните хотя бы одну строку.');
                return;
            }
            
            const testAccount = filteredData[0];
            const accountId = testAccount[0].toString().trim().replace('act_', '');
            const token = testAccount[1].toString().trim();
            
            const testBtn = document.getElementById('testConnection');
            const originalText = testBtn.innerHTML;
            testBtn.disabled = true;
            testBtn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Тестирование...';
            
            fetch('/api/test_facebook_connection', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    account_id: accountId,
                    access_token: token
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    Swal.fire({
                        icon: 'success',
                        title: 'Соединение установлено!',
                        html: `<strong>Аккаунт:</strong> ${data.account_name || 'N/A'}<br>
                               <strong>Статус:</strong> ${data.account_status || 'N/A'}`,
                        confirmButtonText: 'Отлично'
                    });
                } else {
                    throw new Error(data.error || 'Ошибка соединения');
                }
            })
            .catch(error => {
                Swal.fire({
                    icon: 'error',
                    title: 'Ошибка соединения',
                    text: error.message
                });
            })
            .finally(() => {
                testBtn.disabled = false;
                testBtn.innerHTML = originalText;
            });
        });

        const style = document.createElement('style');
        style.textContent = `
            .invalid-cell {
                background-color: #ffebee !important;
                border: 1px solid #f44336 !important;
            }
            
            .spin { 
                animation: spin 1s linear infinite; 
            }
            
            @keyframes spin { 
                100% { transform: rotate(360deg); } 
            }
            
            .handsontable .htInvalid {
                background-color: #ffebee !important;
            }
            
            #saveData:disabled, 
            #testConnection:disabled,
            #clearBtn:disabled,
            #addRowBtn:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }
        `;
        document.head.appendChild(style);

        validateAndHighlightRows();
    }

    function validateAndHighlightRows() {
        if (!hot) return;
        
        const data = hot.getData();
        hot.updateSettings({
            cells: function(row, col, prop) {
                const cellProperties = {};
                
                if (data[row] && data[row][col]) {
                    const value = data[row][col].toString();
                    
                    if (col === 0 && value && value !== '') {
                        const cleanValue = value.replace('act_', '');
                        if (!/^\d+$/.test(cleanValue)) {
                            cellProperties.className = 'invalid-cell';
                        }
                    }
                    
                    if (col === 1 && value && value !== '') {
                        if (!value.includes('EAAG') && !value.includes('EAAN')) {
                            cellProperties.className = 'invalid-cell';
                        }
                    }
                }
                
                return cellProperties;
            }
        });
    }

    document.getElementById('refreshBtn')?.addEventListener('click', function() {
        const btn = document.getElementById('refreshBtn');
        const originalText = btn.innerHTML;
        
        btn.disabled = true;
        btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Обновление...';
        
        loadExistingAccounts();
        
        setTimeout(() => {
            btn.disabled = false;
            btn.innerHTML = originalText;
            Swal.fire('Обновлено', 'Данные загружены из базы данных', 'success');
        }, 1000);
    });
});