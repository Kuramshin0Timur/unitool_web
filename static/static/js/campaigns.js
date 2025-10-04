// campaigns.js - исправленная версия
$(document).ready(function() {
    window.campaignsTable = $('#campaignsTable').DataTable({
        ajax: {
            url: '/api/campaigns',
            dataSrc: function(json) {
                console.log('Campaigns API response:', json);
                // Преобразуем данные из формата БД в формат для таблицы
                if (json.data && Array.isArray(json.data)) {
                    return json.data.map(campaign => ({
                        id: campaign.id,
                        king: campaign.king,
                        name: campaign.name,
                        status: campaign.status,
                        campaign_id: campaign.campaign_id,
                        account_id: campaign.account_id,
                        token: campaign.token
                    }));
                }
                return [];
            }
        },
        columns: [
            { data: 'king', title: 'KING' },
            { data: 'name', title: 'Название' },
            { 
                data: 'status',
                title: 'Статус',
                render: function(data) {
                    return `<span class="badge ${data === 'ACTIVE' ? 'bg-success' : 'bg-danger'}">${data}</span>`;
                }
            },
            { data: 'account_id', title: 'ID аккаунта' },
            {
                data: null,
                title: 'Действия',
                render: function(data, type, row) {
                    return `
                        <button class="btn btn-sm btn-outline-info sync-btn" 
                                data-account="${row.account_id}" 
                                data-token="${row.token}">
                            <i class="bi bi-arrow-repeat"></i> Синхронизировать
                        </button>
                        <button class="btn btn-sm btn-outline-danger delete-btn ms-1" 
                                data-id="${row.campaign_id}">
                            <i class="bi bi-trash"></i> Удалить
                        </button>
                    `;
                }
            }
        ],
        language: {
            emptyTable: "Нет данных о кампаниях",
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
        order: [[1, 'asc']], // Сортировка по названию
        pageLength: 25,
        responsive: true
    });

    // Обработчик для кнопки синхронизации
    $('#campaignsTable').on('click', '.sync-btn', function() {
        const account_id = $(this).data('account');
        const token = $(this).data('token');
        
        $(this).prop('disabled', true).html('<i class="bi bi-arrow-repeat spin"></i> Синхронизация...');
        
        $.ajax({
            url: '/api/sync_account',
            method: 'POST',
            data: { account_id, token },
            success: function(response) {
                if (response.success) {
                    window.campaignsTable.ajax.reload();
                    Swal.fire('Успех!', response.message, 'success');
                } else {
                    Swal.fire('Ошибка!', response.error, 'error');
                }
            },
            error: function() {
                Swal.fire('Ошибка!', 'Ошибка сети', 'error');
            },
            complete: function() {
                $(this).prop('disabled', false).html('<i class="bi bi-arrow-repeat"></i> Синхронизировать');
            }
        });
    });

    // Обработчик для кнопки удаления
    $('#campaignsTable').on('click', '.delete-btn', function() {
        const campaignId = $(this).data('id');
        const row = $(this).closest('tr');
        const campaignName = row.find('td:eq(1)').text();
        
        Swal.fire({
            title: 'Удалить кампанию?',
            text: `Вы уверены, что хотите удалить кампанию "${campaignName}"?`,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Да, удалить',
            cancelButtonText: 'Отмена'
        }).then((result) => {
            if (result.isConfirmed) {
                $.ajax({
                    url: `/api/campaign/${campaignId}`,
                    method: 'DELETE',
                    success: function(response) {
                        if (response.success) {
                            window.campaignsTable.row(row).remove().draw();
                            Swal.fire('Удалено!', 'Кампания успешно удалена', 'success');
                        } else {
                            Swal.fire('Ошибка!', response.error, 'error');
                        }
                    },
                    error: function() {
                        Swal.fire('Ошибка!', 'Ошибка сети', 'error');
                    }
                });
            }
        });
    });

    // Кнопка принудительного обновления
    $('#refreshCampaigns').click(function() {
        window.campaignsTable.ajax.reload();
        Swal.fire('Обновление', 'Данные кампаний обновляются', 'info');
    });

    // Автоматическое обновление каждые 5 минут
    setInterval(function() {
        window.campaignsTable.ajax.reload(null, false);
    }, 300000);
});
// Добавьте этот код в конец файла campaigns.js
// Глобальный поиск
$('#globalSearch').on('keyup', function() {
    window.campaignsTable.search(this.value).draw();
});

$('#clearSearch').on('click', function() {
    $('#globalSearch').val('');
    window.campaignsTable.search('').draw();
});