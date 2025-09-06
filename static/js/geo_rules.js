
document.addEventListener('DOMContentLoaded', function() {
    let hot;
    let geoRulesData = [];
    
 
    initGeoRulesTable();
    
  
    loadGeoRules();
    
 
    document.getElementById('saveGeoRules')?.addEventListener('click', saveGeoRules);
    document.getElementById('addGeoRule')?.addEventListener('click', addGeoRule);
    
    function initGeoRulesTable() {
        const container = document.getElementById('geoRulesTable');
        if (!container) return;
        
        hot = new Handsontable(container, {
            data: [],
            colHeaders: [
                'GEO', 'Max CPA', 'Min Spend', 'Max Leads Threshold', 
                'Extended Spend Threshold', 'Max uCPC', 'Max uCPC Spend'
            ],
            columns: [
                { data: 'geo', type: 'text', validator: validateGeoCode },
                { data: 'max_cpa', type: 'numeric', format: '0.00' },
                { data: 'min_spend', type: 'numeric', format: '0.00' },
                { data: 'max_leads_threshold', type: 'numeric', format: '0' },
                { data: 'extended_spend_threshold', type: 'numeric', format: '0.00' },
                { data: 'max_ucpc', type: 'numeric', format: '0.00' },
                { data: 'max_ucpc_spend', type: 'numeric', format: '0.00' }
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
            cells: function(row, col, prop) {
                const cellProperties = {};
                if (col === 0) { 
                    cellProperties.renderer = geoCodeRenderer;
                }
                return cellProperties;
            }
        });
    }
    
    function geoCodeRenderer(instance, td, row, col, prop, value, cellProperties) {
        Handsontable.renderers.TextRenderer.apply(this, arguments);
        if (value && value.length === 2) {
            td.style.fontWeight = 'bold';
            td.style.color = '#007bff';
        }
    }
    
    function validateGeoCode(value, callback) {
        if (!value || value.toString().trim() === '') {
            callback(false);
        } else {
            const geoCode = value.toString().trim().toUpperCase();
            const isValid = /^[A-Z]{2}$/.test(geoCode);
            callback(isValid);
        }
    }
    
    function loadGeoRules() {
        fetch('/api/geo_rules')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    geoRulesData = data.rules;
                    updateGeoRulesTable();
                } else {
                    console.error('Ошибка загрузки GEO правил:', data.error);
                }
            })
            .catch(error => {
                console.error('Ошибка загрузки GEO правил:', error);
            });
    }
    
    function updateGeoRulesTable() {
        if (hot) {
            hot.loadData(geoRulesData);
        }
    }
    
    function saveGeoRules() {
        if (!hot) return;
        
        const data = hot.getSourceData();
        const validData = data.filter(row => 
            row.geo && row.geo.toString().trim() !== '' &&
            !isNaN(row.max_cpa) && !isNaN(row.min_spend)
        );
        
        if (validData.length === 0) {
            Swal.fire('Внимание', 'Нет данных для сохранения', 'warning');
            return;
        }
        
        const saveBtn = document.getElementById('saveGeoRules');
        const originalText = saveBtn.innerHTML;
        
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Сохранение...';
        
        fetch('/api/geo_rules', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ rules: validData })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                Swal.fire('Успех', 'GEO правила сохранены', 'success');
                geoRulesData = validData;
            } else {
                Swal.fire('Ошибка', data.error || 'Ошибка сохранения', 'error');
            }
        })
        .catch(error => {
            Swal.fire('Ошибка', 'Ошибка сети: ' + error, 'error');
        })
        .finally(() => {
            saveBtn.disabled = false;
            saveBtn.innerHTML = originalText;
        });
    }
    
    function addGeoRule() {
        if (hot) {
            hot.alter('insert_row');
            const rowCount = hot.countRows();
            hot.selectCell(rowCount - 1, 0);
        }
    }
    
   
    const style = document.createElement('style');
    style.textContent = `
        .spin { animation: spin 1s linear infinite; }
        @keyframes spin { 100% { transform: rotate(360deg); } }
        .hot-container { margin-bottom: 1rem; }
    `;
    document.head.appendChild(style);
});