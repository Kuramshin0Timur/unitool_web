document.addEventListener('DOMContentLoaded', function() {
    let adsetsData = [];
    let selectedAdsets = new Set();
    
    // Инициализация DataTable с фиксированными заголовками
    initDataTable();
    
    // Загрузка данных
    loadAdsets();
    setupEventListeners();
    
    function initDataTable() {
        // Убедимся, что таблица существует
        if (!$.fn.DataTable) {
            console.error('DataTable не подключен');
            setTimeout(initDataTable, 100);
            return;
        }
        
        window.adsetsTable = $('#adsetsTable').DataTable({
            fixedHeader: {
                header: true,
                footer: false
            },
            order: [[4, 'desc']], // Сортировка по Spend по умолчанию
            columnDefs: [
                {
                    targets: 0, // Колонка с checkbox
                    orderable: false,
                    searchable: false,
                    width: '30px'
                },
                {
                    targets: 1, // Название
                    type: 'string',
                    width: '200px', // Фиксированная ширина для длинных названий
                    render: function(data, type, row) {
                return '<div class="text-truncate" style="max-width: 200px" title="' + data + '">' + data + '</div>';
            }
                },
                {
                    targets: 2, // Статус
                    orderable: true,
                    searchable: true,
                    width: '80px'
                },
                {
                        targets: [3, 4, 5, 6, 10], // Числовые колонки
                        type: 'num',
                        render: function(data, type) {
                            if (type === 'display') {
                                return typeof data === 'number' ? data.toFixed(2) : data;
                            }
                            return data;
                        }
                },
                {
                    targets: 7, // Leads
                    type: 'num',
                    width: '70px'
                },
                {
                    targets: 8, // GEO
                    type: 'string',
                    width: '60px'
                },
                {
                    targets: 9, // King
                    type: 'string',
                    width: '80px'
                },
                {
                    targets: 11, // Колонка действий
                    orderable: false,
                    searchable: false,
                    width: '120px'
                }
            ],
            language: {
                emptyTable: "Нет данных об адсетах",
                loadingRecords: "Загрузка...",
                zeroRecords: "Совпадений не найдено",
                info: "Показано с _START_ по _END_ из _TOTAL_ записей",
                infoEmpty: "Показано 0 записей",
                infoFiltered: "(отфильтровано из _MAX_ записей)",
                lengthMenu: "Показать _MENU_ записей",
                search: "Поиск:",
                paginate: {
                    first: "Первая",
                    last: "Последняя",
                    next: "→",
                    previous: "←"
                }
            },
            pageLength: 50,
            responsive: true,
            autoWidth: false,
            dom: '<"row"<"col-md-6"l><"col-md-6"f>>rt<"row"<"col-md-6"i><"col-md-6"p>>',
            initComplete: function() {
                // Добавляем класс для стилизации
                this.api().tables().header().to$().addClass('fixed-header');
            }
        });
    }

    function setupEventListeners() {
        document.getElementById('pauseBtn')?.addEventListener('click', pauseSelectedAdsets);
        document.getElementById('resumeBtn')?.addEventListener('click', resumeSelectedAdsets);
        document.getElementById('setBudgetBtn')?.addEventListener('click', setBudgetForSelected);
        document.getElementById('statusFilter')?.addEventListener('change', filterAdsets);
        document.getElementById('nameSearch')?.addEventListener('input', filterAdsets);
        document.getElementById('autoControlBtn')?.addEventListener('click', runAutoControl);
        document.getElementById('syncAllBtn')?.addEventListener('click', syncAllData);
        document.getElementById('refreshBtn')?.addEventListener('click', loadAdsets);
        
        // Выделить все
        document.getElementById('selectAll')?.addEventListener('change', function() {
            const checkboxes = document.querySelectorAll('#adsetsTable tbody input[type="checkbox"]');
            checkboxes.forEach(checkbox => {
                checkbox.checked = this.checked;
                const adsetId = checkbox.dataset.id;
                if (this.checked) {
                    selectedAdsets.add(adsetId);
                } else {
                    selectedAdsets.delete(adsetId);
                }
            });
            updateSelectedCount();
        });
    }
    // В adsets.js обновите функцию syncAllData
function syncAllData() {
    Swal.fire({
        title: 'Обновить все данные?',
        text: 'Это синхронизирует все аккаунты из базы данных с Facebook и Keitaro',
        icon: 'question',
        showCancelButton: true,
        confirmButtonText: 'Да, обновить',
        cancelButtonText: 'Отмена',
        confirmButtonColor: '#0d6efd'
    }).then((result) => {
        if (result.isConfirmed) {
            const syncBtn = document.getElementById('syncAllBtn');
            const originalText = syncBtn.innerHTML;
            
            syncBtn.disabled = true;
            syncBtn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Синхронизация...';
            
            // Получаем все аккаунты из базы
            fetch('/api/accounts')
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(accountsData => {
                    if (accountsData.success && accountsData.accounts && accountsData.accounts.length > 0) {
                        // Отправляем все аккаунты на синхронизацию
                        return fetch('/api/save_and_sync', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({ 
                                accounts: accountsData.accounts.map(acc => ({
                                    account_id: acc.account_id,
                                    token: acc.token
                                }))
                            })
                        });
                    } else {
                        throw new Error('Нет аккаунтов для синхронизации');
                    }
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
                                <strong>${data.total_adsets || 0}</strong> адсетов<br>
                                <strong>${data.keitaro_records || 0}</strong> записей из Keitaro`,
                            timer: 5000,
                            showConfirmButton: true
                        });
                        
                        // Обновляем таблицу адсетов после небольшой задержки
                        setTimeout(() => {
                            loadAdsets();
                            // Также обновляем таблицу кампаний если она есть
                            if (typeof window.campaignsTable !== 'undefined') {
                                window.campaignsTable.ajax.reload();
                            }
                        }, 2000);
                        
                    } else {
                        throw new Error(data.error || 'Ошибка синхронизации');
                    }
                })
                .catch(error => {
                    console.error('Ошибка синхронизации:', error);
                    Swal.fire({
                        icon: 'error',
                        title: 'Ошибка!',
                        html: `Не удалось выполнить синхронизацию:<br><strong>${error.message}</strong><br><br>
                            Проверьте:<br>
                            - Подключение к интернету<br>
                            - Доступность Facebook API<br>
                            - Корректность токенов доступа`,
                        confirmButtonText: 'Понятно'
                    });
                })
                .finally(() => {
                    syncBtn.disabled = false;
                    syncBtn.innerHTML = originalText;
                });
        }
    });
}

// Также добавьте глобальную функцию для доступа из HTML
window.syncAllData = syncAllData;
    function loadAdsets() {
        console.log('Загрузка адсетов...');
        showLoading();
        
        fetch('/api/adsets')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    adsetsData = data.data || [];
                    renderAdsets(adsetsData);
                    addLogEntry('Список адсетов обновлён');
                    
                    if (adsetsData.length === 0) {
                        showInfo('Нет данных', 'Адсеты не найдены. Импортируйте данные сначала.');
                    }
                } else {
                    showError('Ошибка загрузки адсетов', data.error || 'Неизвестная ошибка');
                }
            })
            .catch(error => {
                console.error('Ошибка загрузки адсетов:', error);
                showError('Ошибка загрузки адсетов', error.message);
            })
            .finally(() => {
                hideLoading();
            });
    }
    
function renderAdsets(data) {
    if (!window.adsetsTable) {
        console.error('DataTable не инициализирован');
        return;
    }
    
    // Очищаем таблицу
    window.adsetsTable.clear();
    
    if (!data || data.length === 0) {
        window.adsetsTable.draw();
        return;
    }
    
    // Добавляем данные с правильным порядком колонок
    data.forEach(adset => {
        const row = [
            createCheckboxCell(adset), // 0: Чекбокс
            adset.name || 'N/A', // 1: Название
            createStatusCell(adset.status), // 2: Статус
            adset.ucpc ? parseFloat(adset.ucpc) : 0, // 3: uCPC
            adset.cpc ? parseFloat(adset.cpc) : 0, // 4: CPC
            adset.spend ? parseFloat(adset.spend) : 0, // 5: Spend
            adset.cpa ? parseFloat(adset.cpa) : 0, // 6: CPA
            adset.leads || 0, // 7: Leads
            adset.geo || 'N/A', // 8: GEO
            adset.king || 'N/A', // 9: King
            adset.budget ? parseFloat(adset.budget) : 0, // 10: Бюджет
            createActionsCell(adset) // 11: Действия
        ];
        
        window.adsetsTable.row.add(row);
    });
    
    window.adsetsTable.draw();
    updateSelectedCount();
}
    function createCheckboxCell(adset) {
        return `
            <input type="checkbox" class="form-check-input adset-checkbox" 
                   data-id="${adset.adset_id}" 
                   onchange="toggleAdsetSelection('${adset.adset_id}', this.checked)">
        `;
    }
    
    function createStatusCell(status) {
        const statusClass = status === 'ACTIVE' ? 'bg-success' : 'bg-secondary';
        return `<span class="badge ${statusClass}">${status}</span>`;
    }
    
    function createActionsCell(adset) {
        if (adset.status === 'ACTIVE') {
            return `
                <button class="btn btn-sm btn-danger pause-btn" 
                        onclick="pauseAdset('${adset.adset_id}', '${adset.token}', '${adset.name.replace(/'/g, "\\'")}')">
                    <i class="bi bi-pause-fill"></i> Отключить
                </button>
            `;
        } else {
            return `
                <button class="btn btn-sm btn-success resume-btn" 
                        onclick="resumeAdset('${adset.adset_id}', '${adset.token}', '${adset.name.replace(/'/g, "\\'")}')">
                    <i class="bi bi-play-fill"></i> Включить
                </button>
            `;
        }
    }
    
    // Глобальные функции для обработки событий
    window.toggleAdsetSelection = function(adsetId, isChecked) {
        if (isChecked) {
            selectedAdsets.add(adsetId);
        } else {
            selectedAdsets.delete(adsetId);
        }
        updateSelectedCount();
        
        // Обновляем checkbox "Выбрать все"
        const allCheckboxes = document.querySelectorAll('.adset-checkbox');
        const selectAll = document.getElementById('selectAll');
        if (selectAll) {
            selectAll.checked = allCheckboxes.length === selectedAdsets.size;
        }
    };
    
    window.pauseAdset = function(adsetId, token, name) {
        showLoading();
        fetch('/api/adset/pause', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                adset_id: adsetId,
                token: token,
                name: name
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                addLogEntry(`AdSet «${name}» отключён`);
                loadAdsets();
            } else {
                showError('Ошибка отключения AdSet', data.error);
            }
        })
        .catch(error => {
            showError('Ошибка отключения AdSet', error);
        })
        .finally(() => {
            hideLoading();
        });
    };
    
    window.resumeAdset = function(adsetId, token, name) {
        showLoading();
        fetch('/api/adset/resume', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                adset_id: adsetId,
                token: token,
                name: name
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                addLogEntry(`AdSet «${name}» включён`);
                loadAdsets();
            } else {
                showError('Ошибка включения AdSet', data.error);
            }
        })
        .catch(error => {
            showError('Ошибка включения AdSet', error);
        })
        .finally(() => {
            hideLoading();
        });
    };
    
    function updateSelectedCount() {
        const countElement = document.getElementById('selectedCount');
        if (countElement) {
            countElement.textContent = `Выбрано: ${selectedAdsets.size}`;
        }
    }
    function filterAdsets() {
        const statusFilter = document.getElementById('statusFilter')?.value || 'all';
        const nameSearch = document.getElementById('nameSearch')?.value.toLowerCase() || '';
        
        if (window.adsetsTable) {
            // Фильтр по статусу
            if (statusFilter !== 'all') {
                window.adsetsTable.column(10).search(statusFilter).draw(); // Колонка статуса
            } else {
                window.adsetsTable.column(10).search('').draw();
            }
            
            // Фильтр по названию
            window.adsetsTable.column(1).search(nameSearch).draw(); // Колонка названия
        }
    }
    // Пауза для выбранных адсетов
    function pauseSelectedAdsets() {
        if (selectedAdsets.size === 0) {
            showWarning('Не выбрано ни одного AdSet');
            return;
        }
        
        Swal.fire({
            title: 'Вы уверены?',
            text: `Вы собираетесь отключить ${selectedAdsets.size} AdSets`,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Да, отключить',
            cancelButtonText: 'Отмена'
        }).then((result) => {
            if (result.isConfirmed) {
                const promises = [];
                const errors = [];
                
                selectedAdsets.forEach(adsetId => {
                    const adset = adsetsData.find(a => a.adset_id === adsetId);
                    if (adset) {
                        promises.push(
                            fetch('/api/adset/pause', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                },
                                body: JSON.stringify({
                                    adset_id: adset.adset_id,
                                    token: adset.token,
                                    name: adset.name
                                })
                            })
                            .then(response => response.json())
                            .then(data => {
                                if (!data.success) {
                                    errors.push(`${adset.name}: ${data.error}`);
                                }
                                return data;
                            })
                        );
                    }
                });
                
                Promise.all(promises)
                    .then(() => {
                        if (errors.length > 0) {
                            showError('Некоторые AdSets не были отключены', errors.join('<br>'));
                        } else {
                            Swal.fire(
                                'Успешно!',
                                `Отключено ${selectedAdsets.size} AdSets`,
                                'success'
                            );
                            addLogEntry(`Отключено ${selectedAdsets.size} AdSets`);
                        }
                        loadAdsets();
                        selectedAdsets.clear();
                        updateSelectedCount();
                    })
                    .catch(error => {
                        showError('Ошибка отключения AdSets', error);
                    });
            }
        });
    }
    
    // Включение выбранных адсетов
    function resumeSelectedAdsets() {
        if (selectedAdsets.size === 0) {
            showWarning('Не выбрано ни одного AdSet');
            return;
        }
        
        Swal.fire({
            title: 'Вы уверены?',
            text: `Вы собираетесь включить ${selectedAdsets.size} AdSets`,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Да, включить',
            cancelButtonText: 'Отмена'
        }).then((result) => {
            if (result.isConfirmed) {
                const promises = [];
                const errors = [];
                
                selectedAdsets.forEach(adsetId => {
                    const adset = adsetsData.find(a => a.adset_id === adsetId);
                    if (adset) {
                        promises.push(
                            fetch('/api/adset/resume', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                },
                                body: JSON.stringify({
                                    adset_id: adset.adset_id,
                                    token: adset.token,
                                    name: adset.name
                                })
                            })
                            .then(response => response.json())
                            .then(data => {
                                if (!data.success) {
                                    errors.push(`${adset.name}: ${data.error}`);
                                }
                                return data;
                            })
                        );
                    }
                });
                
                Promise.all(promises)
                    .then(() => {
                        if (errors.length > 0) {
                            showError('Некоторые AdSets не были включены', errors.join('<br>'));
                        } else {
                            Swal.fire(
                                'Успешно!',
                                `Включено ${selectedAdsets.size} AdSets`,
                                'success'
                            );
                            addLogEntry(`Включено ${selectedAdsets.size} AdSets`);
                        }
                        loadAdsets();
                        selectedAdsets.clear();
                        updateSelectedCount();
                    })
                    .catch(error => {
                        showError('Ошибка включения AdSets', error);
                    });
            }
        });
    }
    
    // Установка бюджета для выбранных адсетов
    function setBudgetForSelected() {
        if (selectedAdsets.size === 0) {
            showWarning('Не выбрано ни одного AdSet');
            return;
        }
        
        const budgetInput = document.getElementById('budgetInput');
        if (!budgetInput) {
            showWarning('Поле бюджета не найдено');
            return;
        }
        
        const budget = parseFloat(budgetInput.value);
        if (isNaN(budget) || budget <= 0) {
            showWarning('Укажите корректный бюджет');
            return;
        }
        
        Swal.fire({
            title: 'Вы уверены?',
            text: `Установить бюджет $${budget.toFixed(2)} для ${selectedAdsets.size} AdSets?`,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Да, установить',
            cancelButtonText: 'Отмена'
        }).then((result) => {
            if (result.isConfirmed) {
                const promises = [];
                const errors = [];
                
                selectedAdsets.forEach(adsetId => {
                    const adset = adsetsData.find(a => a.adset_id === adsetId);
                    if (adset) {
                        promises.push(
                            fetch('/api/adset/budget', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                },
                                body: JSON.stringify({
                                    adset_id: adset.adset_id,
                                    token: adset.token,
                                    name: adset.name,
                                    budget: budget
                                })
                            })
                            .then(response => response.json())
                            .then(data => {
                                if (!data.success) {
                                    errors.push(`${adset.name}: ${data.error}`);
                                }
                                return data;
                            })
                        );
                    }
                });
                
                Promise.all(promises)
                    .then(() => {
                        if (errors.length > 0) {
                            showError('Бюджет не установлен для некоторых AdSets', errors.join('<br>'));
                        } else {
                            Swal.fire(
                                'Успешно!',
                                `Бюджет установлен для ${selectedAdsets.size} AdSets`,
                                'success'
                            );
                            addLogEntry(`Бюджет установлен для ${selectedAdsets.size} AdSets`);
                        }
                        loadAdsets();
                        selectedAdsets.clear();
                        updateSelectedCount();
                    })
                    .catch(error => {
                        showError('Ошибка установки бюджета', error);
                    });
            }
        });
    }
    
    // Пауза для одного адсета
    function pauseAdset(adsetId, token, name) {
        showLoading();
        fetch('/api/adset/pause', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                adset_id: adsetId,
                token: token,
                name: name
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                addLogEntry(`AdSet «${name}» отключён`);
                loadAdsets();
            } else {
                showError('Ошибка отключения AdSet', data.error);
            }
        })
        .catch(error => {
            showError('Ошибка отключения AdSet', error);
        })
        .finally(() => {
            hideLoading();
        });
    }
    
    // Включение одного адсета
    function resumeAdset(adsetId, token, name) {
        showLoading();
        fetch('/api/adset/resume', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                adset_id: adsetId,
                token: token,
                name: name
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                addLogEntry(`AdSet «${name}» включён`);
                loadAdsets();
            } else {
                showError('Ошибка включения AdSet', data.error);
            }
        })
        .catch(error => {
            showError('Ошибка включения AdSet', error);
        })
        .finally(() => {
            hideLoading();
        });
    }
    
  
    function runAutoControl() {
        const runBtn = document.getElementById('autoControlBtn');
        const originalText = runBtn.innerHTML;
        
        runBtn.disabled = true;
        runBtn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Выполнение...';
        
        // Запускаем и автоконтроль и автообновление вместе
        fetch('/api/auto_refresh', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                action: 'start',
                interval: 5  // Интервал по умолчанию
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                addLog('✅ Автоконтроль и автообновление запущены', 'success');
                // Обновляем UI чтобы показать, что система запущена
                updateAutoControlUI(true);
            } else {
                addLog('❌ Ошибка запуска: ' + (data.error || 'Неизвестная ошибка'), 'error');
            }
        })
        .catch(error => {
            addLog('❌ Ошибка сети: ' + error.message, 'error');
        })
        .finally(() => {
            runBtn.disabled = false;
            runBtn.innerHTML = originalText;
        });
    }

    // Добавьте функцию для обновления UI автоконтроля
    function updateAutoControlUI(isRunning) {
        const autoControlBtn = document.getElementById('autoControlBtn');
        if (autoControlBtn) {
            if (isRunning) {
                autoControlBtn.classList.remove('btn-primary');
                autoControlBtn.classList.add('btn-success');
                autoControlBtn.innerHTML = '<i class="bi bi-play-fill"></i> Система запущена';
            } else {
                autoControlBtn.classList.remove('btn-success');
                autoControlBtn.classList.add('btn-primary');
                autoControlBtn.innerHTML = '<i class="bi bi-play-fill"></i> Запустить автоконтроль';
            }
        }
    }

    // Добавьте проверку статуса при загрузке страницы
    document.addEventListener('DOMContentLoaded', function() {
        // Проверяем статус системы при загрузке
        checkAutoSystemStatus();
    });

    function checkAutoSystemStatus() {
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
            if (data.success && data.status.running) {
                updateAutoControlUI(true);
                addLog('✅ Система автоконтроля и автообновления запущена', 'success');
            }
        })
        .catch(error => {
            console.error('Ошибка проверки статуса системы:', error);
        });
    }
    // Добавление записи в лог
    function addLogEntry(message) {
        const now = new Date();
        const timeString = now.toLocaleTimeString();
        const logEntry = document.createElement('div');
        logEntry.className = 'log-entry';
        logEntry.innerHTML = `<span class="text-muted">[${timeString}]</span> ${message}`;
        
        const logContent = document.getElementById('logContent');
        if (logContent) {
            logContent.prepend(logEntry);
            logContent.scrollTop = 0;
        }
    }
    
    // Вспомогательные функции
    function showLoading() {
        const refreshBtn = document.getElementById('refreshBtn');
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Загрузка...';
        }
    }
    
    function hideLoading() {
        const refreshBtn = document.getElementById('refreshBtn');
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = '<i class="bi bi-arrow-repeat"></i> Обновить';
        }
    }
    
    function showError(title, message) {
        console.error(title, message);
        Swal.fire({
            title: title,
            html: typeof message === 'string' ? message : JSON.stringify(message),
            icon: 'error'
        });
        addLogEntry(`Ошибка: ${title} - ${typeof message === 'string' ? message : JSON.stringify(message)}`);
    }
    
    function showWarning(message) {
        Swal.fire({
            title: 'Внимание',
            text: message,
            icon: 'warning'
        });
    }
    
    function showInfo(title, message) {
        Swal.fire({
            title: title,
            text: message,
            icon: 'info'
        });
    }
    const tableStyles = document.createElement('style');
tableStyles.textContent = `
    .fixed-header {
        position: sticky;
        top: 0;
        background: white;
        z-index: 1000;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .dataTables_wrapper {
        position: relative;
    }
    
    #adsetsTable {
        width: 100% !important;
        margin-bottom: 1rem;
    }
    
    #adsetsTable th {
        background-color: #f8f9fa;
        border-bottom: 2px solid #dee2e6;
        padding: 12px 8px;
        font-weight: 600;
        color: #495057;
        vertical-align: middle;
    }
    
    #adsetsTable td {
        padding: 8px;
        vertical-align: middle;
    }
    
    #adsetsTable tr:hover {
        background-color: #f8f9fa;
    }
    
    .adset-checkbox {
        margin: 0;
        cursor: pointer;
    }
    
    /* Стили для числовых колонок */
    #adsetsTable td.text-end {
        text-align: right !important;
        font-family: 'Courier New', monospace;
        font-weight: 500;
    }
    
    /* Стили для статуса */
    .badge {
        font-size: 0.75em;
        padding: 0.4em 0.6em;
    }
    
    /* Кнопки действий */
    .btn-sm {
        padding: 0.25rem 0.5rem;
        font-size: 0.75rem;
    }
    
    /* Адаптивность */
    @media (max-width: 768px) {
        #adsetsTable {
            font-size: 0.875rem;
        }
        
        #adsetsTable th,
        #adsetsTable td {
            padding: 6px 4px;
        }
        
        .btn-sm {
            padding: 0.2rem 0.4rem;
            font-size: 0.7rem;
        }
    }
`;
document.head.appendChild(tableStyles);
// В функции renderAdsets обновите создание строк:
function renderAdsets(data) {
    if (!window.adsetsTable) {
        console.error('DataTable не инициализирован');
        return;
    }
    
    window.adsetsTable.clear();
    
    if (!data || data.length === 0) {
        window.adsetsTable.draw();
        return;
    }
    
    data.forEach(adset => {
        const row = [
            createCheckboxCell(adset), // 0: Чекбокс
            adset.name || 'N/A', // 1: Название
            createStatusCell(adset.status), // 2: Статус (ПЕРЕМЕЩЕНО НАВЕРХ)
            // adset.adset_id || 'N/A', // 3: ID адсета (СКРЫТО)
            adset.ucpc ? parseFloat(adset.ucpc) : 0,
            adset.cpc ? parseFloat(adset.cpc) : 0, // 4: CPC
            adset.spend ? parseFloat(adset.spend) : 0,
            adset.cpa ? parseFloat(adset.cpa) : 0,
            adset.leads || 0,
            adset.geo || 'N/A',
            adset.king || 'N/A',
            adset.budget ? parseFloat(adset.budget) : 0,
            createActionsCell(adset)
        ];
        
        window.adsetsTable.row.add(row);
    });
    
    window.adsetsTable.draw();
    updateSelectedCount();
}
// Добавьте функцию для отображения цен с долларами
function formatCurrency(value) {
    return `$${parseFloat(value).toFixed(2)}`;
}

// Обновите колонки с рендерингом для отображения
columnDefs: [
    {
        targets: [3, 4, 5, 9], // uCPC, Spend, CPA, Бюджет
        type: 'num',
        render: function(data, type) {
            if (type === 'display') {
                return formatCurrency(data);
            }
            return data;
        }
    },
    {
        targets: 6, // Leads
        type: 'num',
        render: function(data, type) {
            if (type === 'display') {
                return data.toString();
            }
            return data;
        }
    }
]
});