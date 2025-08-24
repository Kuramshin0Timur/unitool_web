document.addEventListener('DOMContentLoaded', function() {
    let adsetsData = [];
    let selectedAdsets = new Set();
    
    // Инициализация DataTable с фиксированными заголовками
    initDataTable();
    
    // Загрузка данных
    loadAdsets();
    setupEventListeners();
    
function initDataTable() {
    if (!$.fn.DataTable) {
        console.error('DataTable не подключен');
        setTimeout(initDataTable, 100);
        return;
    }
    
    // Убедимся, что таблица уничтожена перед созданием новой
    if ($.fn.DataTable.isDataTable('#adsetsTable')) {
        window.adsetsTable.destroy();
        $('#adsetsTable').empty();
    }

    window.adsetsTable = $('#adsetsTable').DataTable({
        fixedHeader: {
            header: true,
            footer: false
        },
        order: [[5, 'desc']], // Сортировка по Spend по умолчанию
        columns: [
            { // 0: Чекбокс
                orderable: false,
                searchable: false,
                width: '30px'
            },
            { // 1: Название
                type: 'string',
                width: '250px',
                render: function(data, type, row) {
                    return '<div class="text-truncate" style="max-width: 250px" title="' + data + '">' + data + '</div>';
                }
            },
            { // 2: Статус
                orderable: true,
                searchable: true,
                width: '80px'
            },
            { // 3: uCPC
                type: 'num',
                width: '80px',
                render: function(data, type) {
                    return type === 'display' ? parseFloat(data || 0).toFixed(2) : data;
                }
            },
            { // 4: CPC
                type: 'num',
                width: '80px',
                render: function(data, type) {
                    return type === 'display' ? parseFloat(data || 0).toFixed(2) : data;
                }
            },
            { // 5: Spend
                type: 'num',
                width: '80px',
                render: function(data, type) {
                    return type === 'display' ? parseFloat(data || 0).toFixed(2) : data;
                }
            },
            { // 6: CPA
                type: 'num',
                width: '80px',
                render: function(data, type) {
                    return type === 'display' ? parseFloat(data || 0).toFixed(2) : data;
                }
            },
            { // 7: Leads
                type: 'num',
                width: '70px'
            },
            { // 8: GEO
                type: 'string',
                width: '60px'
            },
            { // 9: King
                type: 'string',
                width: '80px'
            },
            { // 10: Бюджет
                type: 'num',
                width: '80px',
                render: function(data, type) {
                    return type === 'display' ? parseFloat(data || 0).toFixed(2) : data;
                }
            },
            { // 11: Действия
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
        dom: '<"row"<"col-md-6"l><"col-md-6"f>>rt<"row"<"col-md-6"i><"col-md-6"p>>'
    });
}
    function setupEventListeners() {
    document.getElementById('pauseBtn')?.addEventListener('click', pauseSelectedAdsets);
    document.getElementById('resumeBtn')?.addEventListener('click', resumeSelectedAdsets);
    document.getElementById('setBudgetBtn')?.addEventListener('click', setBudgetForSelected);
    document.getElementById('autoBudgetBtn')?.addEventListener('click', runAutoBudget); // НОВАЯ КНОПКА
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
                .then(accountsResponse => {
                    if (accountsResponse.success && accountsResponse.accounts && accountsResponse.accounts.length > 0) {
                        // Отправляем все аккаунты на синхронизацию
                        return fetch('/api/save_and_sync', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({ 
                                accounts: accountsResponse.accounts.map(acc => ({
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
    
    window.adsetsTable.clear();
    
    if (!data || data.length === 0) {
        window.adsetsTable.draw();
        return;
    }
    
    data.forEach(adset => {
        const row = [
            createCheckboxCell(adset), // 0: Чекбокс
            adset.name || 'N/A', // 1: Название
            createStatusCell(adset.status), // 2: Статус
            adset.ucpc || 0, // 3: uCPC
            adset.cpc || 0, // 4: CPC из Facebook
            adset.spend || 0, // 5: Spend
            adset.cpa || 0, // 6: CPA
            adset.leads || 0, // 7: Leads
            adset.geo || 'N/A', // 8: GEO
            adset.king || 'N/A', // 9: King
            adset.budget || 0, // 10: Бюджет
            createActionsCell(adset) // 11: Действия
        ];
        
        window.adsetsTable.row.add(row);
    });
    
    window.adsetsTable.draw();
    updateSelectedCount();
}
// Обновим конфигурацию колонок
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
        width: '250px',
        render: function(data, type, row) {
            return '<div class="text-truncate" style="max-width: 250px" title="' + data + '">' + data + '</div>';
        }
    },
    {
        targets: 2, // Статус
        orderable: true,
        searchable: true,
        width: '80px'
    },
    {
        targets: [3, 4, 5, 6, 10], // Числовые колонки (uCPC, CPC, Spend, CPA, Budget)
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
]
function createAutoBudgetCell(value) {
    const isEnabled = Boolean(value);
    const colorClass = isEnabled ? 'text-success' : 'text-secondary';
    const icon = isEnabled ? 'bi-check-circle-fill' : 'bi-x-circle-fill';
    return `<i class="bi ${icon} ${colorClass}"></i>`;
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
    return `
        <div class="btn-group-sm">
            ${adset.status === 'ACTIVE' ? `
                <button class="btn btn-sm btn-danger pause-btn" 
                        onclick="pauseAdset('${adset.adset_id}', '${adset.token}', '${adset.name.replace(/'/g, "\\'")}')">
                    <i class="bi bi-pause-fill"></i>
                </button>
            ` : `
                <button class="btn btn-sm btn-success resume-btn" 
                        onclick="resumeAdset('${adset.adset_id}', '${adset.token}', '${adset.name.replace(/'/g, "\\'")}')">
                    <i class="bi bi-play-fill"></i>
                </button>
            `}
            <button class="btn btn-sm btn-info budget-settings-btn" 
                    onclick="openBudgetSettings('${adset.adset_id}', '${adset.name.replace(/'/g, "\\'")}')">
                <i class="bi bi-gear-fill"></i>
            </button>
        </div>
    `;
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
    
// В adsets.js обновите функции
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
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            addLogEntry(`AdSet «${name}» отключён`);
            loadAdsets();
            Swal.fire('Успех!', `AdSet «${name}» отключён`, 'success');
        } else {
            showError('Ошибка отключения AdSet', data.error);
        }
    })
    .catch(error => {
        showError('Ошибка отключения AdSet', error.message);
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
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            addLogEntry(`AdSet «${name}» включён`);
            loadAdsets();
            Swal.fire('Успех!', `AdSet «${name}» включён`, 'success');
        } else {
            showError('Ошибка включения AdSet', data.error);
        }
    })
    .catch(error => {
        showError('Ошибка включения AdSet', error.message);
    })
    .finally(() => {
        hideLoading();
    });
};
// В adsets.js добавьте функцию установки бюджета



// В adsets.js добавьте функцию загрузки логов
function loadAutoControlLogs() {
    const logContent = document.getElementById('logContent');
    if (!logContent) return;
    
    fetch('/api/auto_control/logs')
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.success && data.logs) {
            logContent.innerHTML = '';
            data.logs.forEach(log => {
                addLogEntry(log.message, log.level);
            });
        }
    })
    .catch(error => {
        console.error('Ошибка загрузки логов:', error);
    });
}

// Обновите функцию addLogEntry для поддержки разных уровней

// Загружаем логи при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    loadAutoControlLogs();
    
    // Обновляем логи каждые 30 секунд
    setInterval(loadAutoControlLogs, 30000);
});
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
        // Фильтр по статусу (колонка 2)
        if (statusFilter !== 'all') {
            window.adsetsTable.column(2).search(statusFilter).draw();
        } else {
            window.adsetsTable.column(2).search('').draw();
        }
        
        // Фильтр по названию (колонка 1)
        window.adsetsTable.column(1).search(nameSearch).draw();
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
        cancelButtonText: 'Отмена',
        confirmButtonColor: '#0d6efd'
    }).then((result) => {
        if (result.isConfirmed) {
            const promises = [];
            const errors = [];
            const successes = [];
            
            selectedAdsets.forEach(adsetId => {
                const adset = adsetsData.find(a => a.adset_id === adsetId);
                if (adset) {
                    const promise = fetch('/api/adset/budget', {
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
                        } else {
                            successes.push(adset.name);
                        }
                        return data;
                    })
                    .catch(error => {
                        errors.push(`${adset.name}: ${error.message}`);
                    });
                    
                    promises.push(promise);
                }
            });
            
            Promise.all(promises)
                .then(() => {
                    if (errors.length > 0) {
                        showError('Бюджет не установлен для некоторых AdSets', 
                                 errors.join('<br>'));
                    }
                    
                    if (successes.length > 0) {
                        Swal.fire(
                            'Успешно!',
                            `Бюджет установлен для ${successes.length} AdSets`,
                            'success'
                        );
                        addLogEntry(`Бюджет установлен для ${successes.length} AdSets`);
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
const columnConfig = [
  { index: 1, name: 'Название', visible: true, width: 300 },
  { index: 2, name: 'Статус', visible: true, width: 80 },
  { index: 3, name: 'uCPC', visible: true, width: 80 },
  { index: 4, name: 'CPC', visible: true, width: 80 },
  { index: 5, name: 'Spend', visible: true, width: 80 },
  { index: 6, name: 'CPA', visible: true, width: 80 },
  { index: 7, name: 'Leads', visible: true, width: 70 },
  { index: 8, name: 'GEO', visible: true, width: 60 },
  { index: 9, name: 'King', visible: true, width: 80 },
  { index: 10, name: 'Бюджет', visible: true, width: 80 },
  { index: 11, name: 'Действия', visible: true, width: 120 }
];

document.getElementById('columnManagerBtn').addEventListener('click', () => {
  const tbody = document.getElementById('columnSettingsBody');
  loadAutoControlLogs();
  tbody.innerHTML = '';
  columnConfig.forEach(col => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${col.name}</td>
      <td><input type="checkbox" data-index="${col.index}" ${col.visible ? 'checked' : ''}></td>
      <td><input type="number" value="${col.width}" data-width="${col.index}" style="width: 80px;"></td>
    `;
    tbody.appendChild(row);
  });
  new bootstrap.Modal(document.getElementById('columnManagerModal')).show();
});

document.getElementById('applyColumnSettings').addEventListener('click', () => {
  columnConfig.forEach(col => {
    const checkbox = document.querySelector(`input[data-index="${col.index}"]`);
    const widthInput = document.querySelector(`input[data-width="${col.index}"]`);
    const visible = checkbox.checked;
    const width = parseInt(widthInput.value);

    window.adsetsTable.column(col.index).visible(visible);
    window.adsetsTable.column(col.index).nodes().to$().css('width', `${width}px`);

    col.visible = visible;
    col.width = width;
  });

  bootstrap.Modal.getInstance(document.getElementById('columnManagerModal')).hide();
});

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
function addLogEntry(message, level = 'info') {
    const now = new Date();
    const timeString = now.toLocaleTimeString();

    const logEntry = document.createElement('div');
    logEntry.className = `log-entry log-${level}`;
    
    // Добавляем иконки для разных уровней
    let icon = '';
    switch(level) {
        case 'error':
            icon = '❌';
            break;
        case 'success':
            icon = '✅';
            break;
        case 'warning':
            icon = '⚠️';
            break;
        default:
            icon = 'ℹ️';
    }
    
    logEntry.innerHTML = `<span class="text-muted">[${timeString}]</span> ${icon} ${message}`;

    const logContent = document.getElementById('logContent');
    if (logContent) {
        logContent.prepend(logEntry);
        
        // Ограничиваем количество записей
        if (logContent.children.length > 100) {
            logContent.removeChild(logContent.lastChild);
        }
        
        logContent.scrollTop = 0;
    }
}

fetch(`/api/auto_control/logs?ts=${Date.now()}`)

    
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
            createStatusCell(adset.status), // 2: Статус
            adset.ucpc ? parseFloat(adset.ucpc).toFixed(2) : '0.00', // 3: uCPC
            adset.cpc ? parseFloat(adset.cpc).toFixed(2) : '0.00', // 4: CPC из Facebook
            adset.spend ? parseFloat(adset.spend).toFixed(2) : '0.00', // 5: Spend
            adset.cpa ? parseFloat(adset.cpa).toFixed(2) : '0.00', // 6: CPA
            adset.leads || 0, // 7: Leads
            adset.geo || 'N/A', // 8: GEO
            adset.king || 'N/A', // 9: King
            adset.budget ? parseFloat(adset.budget).toFixed(2) : '0.00', // 10: Бюджет
            createActionsCell(adset) // 11: Действия
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

function openBudgetSettings(adsetId, adsetName) {
    // Показываем загрузку
    $('#budgetSettingsModal').modal('show');
    $('#budgetSettingsTitle').text(`Настройки бюджета: ${adsetName}`);
    $('#budgetAdsetId').val(adsetId);
    
    // Загружаем текущие настройки
    fetch(`/api/adset/budget_settings?adset_id=${adsetId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const settings = data.settings;
                $('#autoBudgetIncrease').prop('checked', settings.auto_budget_increase);
                $('#autoBudgetDecrease').prop('checked', settings.auto_budget_decrease);
                $('#maxBudget').val(settings.max_budget);
                $('#minBudget').val(settings.min_budget);
                $('#budgetIncreaseStep').val(settings.budget_increase_step);
                $('#budgetDecreaseStep').val(settings.budget_decrease_step);
            } else {
                showError('Ошибка загрузки настроек', data.error);
            }
        })
        .catch(error => {
            showError('Ошибка загрузки настроек', error);
        });
}

function saveBudgetSettings() {
    const adsetId = $('#budgetAdsetId').val();
    const settings = {
        auto_budget_increase: $('#autoBudgetIncrease').prop('checked'),
        auto_budget_decrease: $('#autoBudgetDecrease').prop('checked'),
        max_budget: parseFloat($('#maxBudget').val()) || 0,
        min_budget: parseFloat($('#minBudget').val()) || 0,
        budget_increase_step: parseFloat($('#budgetIncreaseStep').val()) || 1.2,
        budget_decrease_step: parseFloat($('#budgetDecreaseStep').val()) || 0.8
    };
    
    fetch('/api/adset/budget_settings', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            adset_id: adsetId,
            ...settings
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            $('#budgetSettingsModal').modal('hide');
            Swal.fire('Успех!', 'Настройки бюджета сохранены', 'success');
            addLogEntry(`Настройки бюджета сохранены для адсета ${adsetId}`);
        } else {
            showError('Ошибка сохранения настроек', data.error);
        }
    })
    .catch(error => {
        showError('Ошибка сохранения настроек', error);
    });
}
function runAutoBudget() {
    const runBtn = document.getElementById('autoBudgetBtn');
    const originalText = runBtn.innerHTML;
    
    runBtn.disabled = true;
    runBtn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Выполнение...';
    
    fetch('/api/auto_budget/run', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire('Успех!', data.message, 'success');
            addLogEntry(data.message);
            setTimeout(loadAdsets, 2000); // Обновляем таблицу
        } else {
            showError('Ошибка авто-бюджета', data.error);
        }
    })
    .catch(error => {
        showError('Ошибка авто-бюджета', error);
    })
    .finally(() => {
        runBtn.disabled = false;
        runBtn.innerHTML = originalText;
    });
}


// Добавляем кнопку авто-бюджета в UI
function addAutoBudgetButton() {
    const buttonHtml = `
        <button id="autoBudgetBtn" class="btn btn-warning" onclick="runAutoBudget()">
            <i class="bi bi-currency-dollar"></i> Авто-бюджет
        </button>
    `;
    
    // Добавляем кнопку рядом с другими кнопками действий
    const actionButtons = document.querySelector('.action-buttons');
    if (actionButtons) {
        actionButtons.insertAdjacentHTML('beforeend', buttonHtml);
    }
}

// Обновляем функцию createActionsCell для добавления кнопки настроек бюджета
function createActionsCell(adset) {
    return `
        <div class="btn-group-sm">
            ${adset.status === 'ACTIVE' ? `
                <button class="btn btn-sm btn-danger pause-btn" 
                        onclick="pauseAdset('${adset.adset_id}', '${adset.token}', '${adset.name.replace(/'/g, "\\'")}')">
                    <i class="bi bi-pause-fill"></i>
                </button>
            ` : `
                <button class="btn btn-sm btn-success resume-btn" 
                        onclick="resumeAdset('${adset.adset_id}', '${adset.token}', '${adset.name.replace(/'/g, "\\'")}')">
                    <i class="bi bi-play-fill"></i>
                </button>
            `}
            <button class="btn btn-sm btn-info budget-settings-btn" 
                    onclick="openBudgetSettings('${adset.adset_id}', '${adset.name.replace(/'/g, "\\'")}')">
                <i class="bi bi-gear-fill"></i>
            </button>
        </div>
    `;
}

// Добавляем модальное окно для настроек бюджета в HTML
function addBudgetSettingsModal() {
    const modalHtml = `
    <div class="modal fade" id="budgetSettingsModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="budgetSettingsTitle">Настройки авто-бюджета</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <input type="hidden" id="budgetAdsetId">
                    
                    <div class="mb-3">
                        <div class="form-check form-switch">
                            <input class="form-check-input" type="checkbox" id="autoBudgetIncrease">
                            <label class="form-check-label" for="autoBudgetIncrease">
                                Авто-увеличение бюджета
                            </label>
                        </div>
                    </div>
                    
                    <div class="mb-3">
                        <div class="form-check form-switch">
                            <input class="form-check-input" type="checkbox" id="autoBudgetDecrease">
                            <label class="form-check-label" for="autoBudgetDecrease">
                                Авто-уменьшение бюджета
                            </label>
                        </div>
                    </div>
                    
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label for="maxBudget" class="form-label">Макс. бюджет ($)</label>
                            <input type="number" class="form-control" id="maxBudget" step="0.01" min="0">
                        </div>
                        <div class="col-md-6 mb-3">
                            <label for="minBudget" class="form-label">Мин. бюджет ($)</label>
                            <input type="number" class="form-control" id="minBudget" step="0.01" min="0">
                        </div>
                    </div>
                    
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label for="budgetIncreaseStep" class="form-label">Шаг увеличения</label>
                            <input type="number" class="form-control" id="budgetIncreaseStep" step="0.1" min="1.0" value="1.2">
                        </div>
                        <div class="col-md-6 mb-3">
                            <label for="budgetDecreaseStep" class="form-label">Шаг уменьшения</label>
                            <input type="number" class="form-control" id="budgetDecreaseStep" step="0.1" max="1.0" value="0.8">
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Отмена</button>
                    <button type="button" class="btn btn-primary" onclick="saveBudgetSettings()">Сохранить</button>
                </div>
            </div>
        </div>
    </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Добавляем модальное окно
    addBudgetSettingsModal();
    
    // Добавляем кнопку авто-бюджета
    addAutoBudgetButton();
    
    // Добавляем обработчик для клавиши Enter в модальном окне
    $('#budgetSettingsModal').on('keypress', function(e) {
        if (e.which === 13) {
            saveBudgetSettings();
        }
    });
});
// Стили для логов
const logStyles = document.createElement('style');
logStyles.textContent = `
    .log-container {
        max-height: 300px;
        overflow-y: auto;
        font-family: 'Courier New', monospace;
        font-size: 0.85rem;
        background-color: #f8f9fa;
        border-radius: 0.375rem;
        padding: 1rem;
        margin-top: 1rem;
    }
    
    .log-entry {
        padding: 0.5rem 0;
        border-bottom: 1px solid #e9ecef;
        line-height: 1.4;
    }
    
    .log-entry:last-child {
        border-bottom: none;
    }
    
    .log-error {
        color: #dc3545;
        font-weight: 500;
    }
    
    .log-success {
        color: #198754;
        font-weight: 500;
    }
    
    .log-warning {
        color: #ffc107;
        font-weight: 500;
    }
    
    .log-info {
        color: #0dcaf0;
    }
    
    .log-time {
        color: #6c757d;
        font-size: 0.75rem;
        margin-right: 0.5rem;
    }
    
    /* Стили для кнопок действий в таблице */
    .btn-group-sm {
        display: flex;
        gap: 0.25rem;
    }
    
    .btn-group-sm .btn {
        padding: 0.25rem 0.5rem;
        font-size: 0.75rem;
    }
`;
document.head.appendChild(logStyles);
const budgetStyles = document.createElement('style');
budgetStyles.textContent = `
    .budget-settings-btn {
        color: #fff;
        background-color: #0dcaf0;
        border-color: #0dcaf0;
    }

    .budget-settings-btn:hover {
        background-color: #31d2f2;
        border-color: #25cff2;
    }

    .btn-group-sm {
        display: flex;
        gap: 0.25rem;
    }

    .btn-group-sm .btn {
        padding: 0.25rem 0.5rem;
        font-size: 0.75rem;
        border-radius: 0.375rem;
    }

    .text-success {
        color: #198754 !important;
    }

    .text-secondary {
        color: #6c757d !important;
    }

    #autoBudgetBtn {
        transition: all 0.3s ease;
    }

    #autoBudgetBtn:hover {
        transform: translateY(-2px);
        box-shadow: 0 0.25rem 0.5rem rgba(0, 0, 0, 0.15);
    }

    .action-buttons {
        display: flex;
        gap: 0.5rem;
        flex-wrap: wrap;
    }
`;
document.head.appendChild(budgetStyles);