
// Calculate hours helper
function calculateHours(startTime, endTime, pauseHours) {
    if (!startTime || !endTime) return 0;
    
    const [startH, startM] = startTime.split(':').map(Number);
    const [endH, endM] = endTime.split(':').map(Number);
    
    const totalMinutes = (endH * 60 + endM) - (startH * 60 + startM);
    const hours = totalMinutes / 60;
    const netHours = Math.max(0, hours - (pauseHours || 0));
    
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