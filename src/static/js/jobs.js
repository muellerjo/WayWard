/**
 * Jobs Table Management
 * Wegewart-System
 * 
 * Benötigt PAGE_CONFIG im HTML-Template:
 * - PAGE_CONFIG.isOVorAdmin
 * - PAGE_CONFIG.currentUserId
 * - PAGE_CONFIG.currentUserOrtsteil
 * - PAGE_CONFIG.machines
 * - PAGE_CONFIG.wegewarten
 * - PAGE_CONFIG.urls
 */

// State
let originalData = {};
let editingRowId = null;

// ============================================
// Helper Functions
// ============================================

function buildMachineOptions(selectedId = null) {
    let html = '<option value="">Keine</option>';
    PAGE_CONFIG.machines.forEach(m => {
        const selected = m.id == selectedId ? 'selected' : '';
        html += `<option value="${m.id}" ${selected}>${m.name}</option>`;
    });
    return html;
}

function buildWegewartenOptions(selectedId = null) {
    let html = '';
    const defaultSelected = selectedId || PAGE_CONFIG.currentUserId;
    PAGE_CONFIG.wegewarten.forEach(ww => {
        const selected = ww.id == defaultSelected ? 'selected' : '';
        html += `<option value="${ww.id}" ${selected}>${ww.vorname} ${ww.name}</option>`;
    });
    return html;
}

function buildStatusOptions(selectedStatus = 'erfasst') {
    let html = '';
    const statuses = [
        { value: 'erfasst', label: 'Erfasst' },
        { value: 'freigegeben', label: 'Freigegeben' },
        { value: 'abgelehnt', label: 'Abgelehnt' }
    ];
    
    statuses.forEach(s => {
        // Nur Admin/Ortsvorsteher können alle Status setzen
        if (s.value !== 'erfasst' && !PAGE_CONFIG.isOVorAdmin) return;
        const selected = s.value === selectedStatus ? 'selected' : '';
        html += `<option value="${s.value}" ${selected}>${s.label}</option>`;
    });
    return html;
}

// ============================================
// Calculations
// ============================================

function calculateHours(startTime, endTime, pauseHours) {
    if (!startTime || !endTime) return 0;
    
    const [startH, startM] = startTime.split(':').map(Number);
    const [endH, endM] = endTime.split(':').map(Number);
    
    const totalMinutes = (endH * 60 + endM) - (startH * 60 + startM);
    const hours = totalMinutes / 60;
    const netHours = Math.max(0, hours - (pauseHours || 0));
    
    // Auf 0.5 runden
    return Math.round(netHours * 2) / 2;
}

function calculateHoursInRow(element) {
    const row = element.closest('tr');
    const startInput = row.querySelector('[data-field="time_start"]');
    const endInput = row.querySelector('[data-field="time_end"]');
    const pauseInput = row.querySelector('[data-field="pause_hours"]');
    const hoursInput = row.querySelector('[data-field="work_hours"]');
    
    if (startInput && endInput && hoursInput) {
        const hours = calculateHours(
            startInput.value,
            endInput.value,
            parseFloat(pauseInput?.value || 0)
        );
        hoursInput.value = hours.toFixed(1);
    }
}

// ============================================
// Row Management
// ============================================

function addNewRow() {
    const noDataRow = document.getElementById('noDataRow');
    if (noDataRow) noDataRow.remove();
    
    const tbody = document.getElementById('jobsTableBody');
    const newId = 'new-' + Date.now();
    const today = new Date().toISOString().split('T')[0];
    
    const checkboxCol = PAGE_CONFIG.isOVorAdmin ? '<td></td>' : '';
    
    let wegewartCols = '';
    if (PAGE_CONFIG.isOVorAdmin) {
        wegewartCols = `
            <td>
                <select class="form-select form-select-sm" data-field="user_id">
                    ${buildWegewartenOptions()}
                </select>
            </td>
            <td>
                <input type="text" class="form-control form-control-sm" 
                       value="${PAGE_CONFIG.currentUserOrtsteil}" readonly>
            </td>
        `;
    }
    
    const hiddenUserField = !PAGE_CONFIG.isOVorAdmin 
        ? `<input type="hidden" data-field="user_id" value="${PAGE_CONFIG.currentUserId}">` 
        : '';
    
    const newRow = `
        <tr id="row-${newId}" data-job-id="${newId}" class="table-info">
            ${checkboxCol}
            <td>
                <input type="date" class="form-control form-control-sm" 
                       value="${today}" data-field="date">
            </td>
            <td>
                <input type="time" class="form-control form-control-sm" 
                       value="" data-field="time_start" onchange="calculateHoursInRow(this)">
            </td>
            <td>
                <input type="time" class="form-control form-control-sm" 
                       value="" data-field="time_end" onchange="calculateHoursInRow(this)">
            </td>
            <td>
                <input type="number" step="0.5" min="0" class="form-control form-control-sm" 
                       value="0" data-field="pause_hours" onchange="calculateHoursInRow(this)">
            </td>
            <td>
                <input type="number" step="0.5" class="form-control form-control-sm" 
                       value="0" data-field="work_hours" readonly>
            </td>
            ${wegewartCols}
            ${hiddenUserField}
            <td>
                <input type="text" class="form-control form-control-sm" 
                       placeholder="Tätigkeit" data-field="work_comment">
            </td>
            <td>
                <select class="form-select form-select-sm" data-field="machine_id">
                    ${buildMachineOptions()}
                </select>
            </td>
            <td>
                <input type="number" step="0.5" min="0" class="form-control form-control-sm" 
                       value="0" data-field="machine_hours">
            </td>
            <td>
                <select class="form-select form-select-sm" data-field="status">
                    ${buildStatusOptions()}
                </select>
            </td>
            <td>
                <button class="btn btn-sm btn-success" onclick="saveNewRow('${newId}')" title="Speichern">
                    <i class="bi bi-check"></i>
                </button>
                <button class="btn btn-sm btn-secondary" onclick="cancelNewRow('${newId}')" title="Abbrechen">
                    <i class="bi bi-x"></i>
                </button>
            </td>
        </tr>
    `;
    
    tbody.insertAdjacentHTML('afterbegin', newRow);
}

function editRow(jobId) {
    if (editingRowId && editingRowId !== jobId) {
        alert('Bitte speichern oder abbrechen Sie die aktuelle Bearbeitung zuerst.');
        return;
    }
    
    const row = document.querySelector(`#row-${jobId}`);
    if (!row) return;
    
    const viewElements = row.querySelectorAll('.view-mode');
    const editElements = row.querySelectorAll('.edit-mode');
    
    // Originaldaten speichern für Cancel
    originalData[jobId] = {};
    editElements.forEach(el => {
        if (el.dataset.field) {
            originalData[jobId][el.dataset.field] = el.value;
        }
    });
    
    viewElements.forEach(el => el.style.display = 'none');
    editElements.forEach(el => el.style.display = 'block');
    
    editingRowId = jobId;
}

function cancelEdit(jobId) {
    const row = document.querySelector(`#row-${jobId}`);
    if (!row) return;
    
    const viewElements = row.querySelectorAll('.view-mode');
    const editElements = row.querySelectorAll('.edit-mode');
    
    // Originaldaten wiederherstellen
    if (originalData[jobId]) {
        editElements.forEach(el => {
            if (el.dataset.field && originalData[jobId][el.dataset.field] !== undefined) {
                el.value = originalData[jobId][el.dataset.field];
            }
        });
    }
    
    viewElements.forEach(el => el.style.display = 'block');
    editElements.forEach(el => el.style.display = 'none');
    
    editingRowId = null;
}

function saveRow(jobId) {
    const row = document.querySelector(`#row-${jobId}`);
    if (!row) return;
    
    const editElements = row.querySelectorAll('.edit-mode[data-field], .edit-mode [data-field]');
    
    const data = { job_id: jobId };
    editElements.forEach(el => {
        if (el.dataset.field) {
            data[el.dataset.field] = el.value;
        }
    });
    
    fetch(PAGE_CONFIG.urls.update, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            location.reload();
        } else {
            alert('Fehler beim Speichern: ' + result.message);
        }
    })
    .catch(error => alert('Fehler beim Speichern: ' + error));
}

function saveNewRow(tempId) {
    const row = document.querySelector(`#row-${tempId}`);
    if (!row) return;
    
    const inputs = row.querySelectorAll('[data-field]');
    
    const data = {};
    inputs.forEach(input => {
        data[input.dataset.field] = input.value;
    });
    
    // Validierung
    if (!data.date || !data.work_comment) {
        alert('Bitte füllen Sie Datum und Tätigkeit aus.');
        return;
    }
    
    if (!data.time_start || !data.time_end) {
        alert('Bitte geben Sie Start- und Endzeit ein.');
        return;
    }
    
    fetch(PAGE_CONFIG.urls.create, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            location.reload();
        } else {
            alert('Fehler beim Erstellen: ' + result.message);
        }
    })
    .catch(error => alert('Fehler beim Erstellen: ' + error));
}

function cancelNewRow(tempId) {
    const row = document.querySelector(`#row-${tempId}`);
    if (row) row.remove();
    
    const tbody = document.getElementById('jobsTableBody');
    if (tbody && tbody.children.length === 0) {
        const colspan = PAGE_CONFIG.isOVorAdmin ? '13' : '11';
        tbody.innerHTML = `
            <tr id="noDataRow">
                <td colspan="${colspan}" class="text-center text-muted">
                    Keine Arbeitseinsätze gefunden.
                </td>
            </tr>
        `;
    }
}

function deleteRow(jobId) {
    if (!confirm('Möchten Sie diesen Einsatz wirklich löschen?')) return;
    
    fetch(PAGE_CONFIG.urls.delete, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: jobId })
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            location.reload();
        } else {
            alert('Fehler beim Löschen: ' + result.message);
        }
    })
    .catch(error => alert('Fehler beim Löschen: ' + error));
}

// ============================================
// Batch Actions (Admin/Ortsvorsteher)
// ============================================

function toggleSelectAll() {
    const selectAll = document.getElementById('selectAll');
    if (!selectAll) return;
    
    const checkboxes = document.querySelectorAll('.job-checkbox');
    checkboxes.forEach(cb => cb.checked = selectAll.checked);
    updateSelectedCount();
}

function updateSelectedCount() {
    const checkboxes = document.querySelectorAll('.job-checkbox:checked');
    const count = checkboxes.length;
    
    const countEl = document.getElementById('selectedCount');
    const approveBtn = document.getElementById('approveBtn');
    const rejectBtn = document.getElementById('rejectBtn');
    
    if (countEl) countEl.textContent = count + ' ausgewählt';
    if (approveBtn) approveBtn.disabled = count === 0;
    if (rejectBtn) rejectBtn.disabled = count === 0;
}

function approveSelected() {
    const checkboxes = document.querySelectorAll('.job-checkbox:checked');
    const jobIds = Array.from(checkboxes).map(cb => cb.value);
    
    if (jobIds.length === 0) {
        alert('Bitte wählen Sie mindestens einen Einsatz aus.');
        return;
    }
    
    if (!confirm(`Möchten Sie ${jobIds.length} Einsatz/Einsätze wirklich freigeben?`)) return;
    
    fetch(PAGE_CONFIG.urls.approve, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_ids: jobIds })
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            location.reload();
        } else {
            alert('Fehler beim Freigeben: ' + result.message);
        }
    })
    .catch(error => alert('Fehler beim Freigeben: ' + error));
}

function rejectSelected() {
    const checkboxes = document.querySelectorAll('.job-checkbox:checked');
    const jobIds = Array.from(checkboxes).map(cb => cb.value);
    
    if (jobIds.length === 0) {
        alert('Bitte wählen Sie mindestens einen Einsatz aus.');
        return;
    }
    
    const reason = prompt('Grund für Ablehnung (optional):');
    if (reason === null) return; // User cancelled
    
    if (!confirm(`Möchten Sie ${jobIds.length} Einsatz/Einsätze wirklich ablehnen?`)) return;
    
    fetch(PAGE_CONFIG.urls.reject, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            job_ids: jobIds,
            rejection_reason: reason
        })
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            location.reload();
        } else {
            alert('Fehler beim Ablehnen: ' + result.message);
        }
    })
    .catch(error => alert('Fehler beim Ablehnen: ' + error));
}

// ============================================
// Initialize
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    // Initial count update wenn Batch-Actions vorhanden
    if (document.getElementById('selectedCount')) {
        updateSelectedCount();
    }
});
