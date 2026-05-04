// Constants
const DATA_URL = 'output/all_activities.json';

// State
let allData = [];
let weeklyDataMap = new Map(); // Maps week -> array of activities
let aggregateChartInst = null;
let weeklyDistChartInst = null;
let weeklyHrChartInst = null;

async function loadData() {
    try {
        const response = await fetch(DATA_URL);
        if (!response.ok) throw new Error('Network response was not ok');
        allData = await response.json();
        
        processData();
        initDashboard();
    } catch (error) {
        console.error('Error loading data:', error);
        alert('Impossibile caricare i dati. Assicurati di eseguire un server locale nella cartella del progetto (es. python -m http.server)');
    }
}

function processData() {
    // Group all flat activities into weeks
    allData.forEach(act => {
        if (!act.week) return; // Skip if no week
        if (!weeklyDataMap.has(act.week)) {
            weeklyDataMap.set(act.week, { week: act.week, activities: [] });
        }
        weeklyDataMap.get(act.week).activities.push(act);
    });
}

function extractActivitySummary(act) {
    if (act.summary) {
        return {
            distanza: act.summary.distanza_km || act.summary.distanza || 0,
            fc_media: act.summary.fc_media_bpm || act.summary.fc_media || 0,
            fc_max: act.summary.fc_max_bpm || act.summary.fc_max || 0
        };
    }
    
    if (act.laps && act.laps.length > 0) {
        const riepilogo = act.laps.find(l => l.lap === 'Riepilogo' || l.intervallo === 'Riepilogo');
        if (riepilogo) {
            return {
                distanza: riepilogo.distanza_km || riepilogo.distanza || 0,
                fc_media: riepilogo.fc_media_bpm || riepilogo.fc_media || 0,
                fc_max: riepilogo.fc_max_bpm || riepilogo.fc_max || 0
            };
        }
    }
    
    return null;
}

function initDashboard() {
    // Process aggregate data
    const labels = [];
    const distances = [];
    const hrAvgs = [];

    // Array from map to iterate in order
    const weeksList = Array.from(weeklyDataMap.values());

    weeksList.forEach(weekData => {
        labels.push(weekData.week);
        
        let totalDist = 0;
        let totalHr = 0;
        let hrCount = 0;

        weekData.activities.forEach(act => {
            const summary = extractActivitySummary(act);
            if (summary) {
                if (summary.distanza) totalDist += summary.distanza;
                if (summary.fc_media) {
                    totalHr += summary.fc_media;
                    hrCount++;
                }
            }
        });

        distances.push(totalDist);
        hrAvgs.push(hrCount > 0 ? Math.round(totalHr / hrCount) : 0);
    });

    renderAggregateChart(labels, distances, hrAvgs);

    // Populate week selector
    const selector = document.getElementById('weekSelector');
    weeksList.forEach((weekData, index) => {
        const option = document.createElement('option');
        option.value = index; // Store index in the Array
        option.textContent = weekData.week;
        selector.appendChild(option);
    });

    selector.addEventListener('change', (e) => {
        const idx = parseInt(e.target.value);
        renderWeeklyCharts(weeksList[idx]);
    });

    // Initial render for weekly chart
    if (weeksList.length > 0) {
        renderWeeklyCharts(weeksList[0]);
    }
}

function renderAggregateChart(labels, distances, hrAvgs) {
    const ctx = document.getElementById('aggregateChart').getContext('2d');
    
    // Set default Chart.js colors
    Chart.defaults.color = '#94a3b8';
    Chart.defaults.font.family = 'Inter';

    aggregateChartInst = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    type: 'line',
                    label: 'FC Media (bpm)',
                    data: hrAvgs,
                    borderColor: '#ec4899',
                    backgroundColor: '#ec4899',
                    borderWidth: 3,
                    tension: 0.4,
                    yAxisID: 'y1',
                    pointBackgroundColor: '#0f172a',
                    pointBorderColor: '#ec4899',
                    pointRadius: 4,
                    pointHoverRadius: 6
                },
                {
                    type: 'bar',
                    label: 'Distanza Totale (km)',
                    data: distances,
                    backgroundColor: 'rgba(59, 130, 246, 0.8)',
                    borderColor: '#3b82f6',
                    borderWidth: 1,
                    borderRadius: 4,
                    yAxisID: 'y'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: '#f8fafc',
                        usePointStyle: true,
                        padding: 20
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleColor: '#f8fafc',
                    bodyColor: '#e2e8f0',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    padding: 12,
                    cornerRadius: 8
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: {
                        display: true,
                        text: 'Distanza (km)',
                        color: '#3b82f6'
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: {
                        display: true,
                        text: 'FC Media (bpm)',
                        color: '#ec4899'
                    },
                    grid: {
                        drawOnChartArea: false
                    }
                }
            }
        }
    });
}

function renderWeeklyCharts(weekData) {
    const labels = [];
    const distances = [];
    const hrAvg = [];
    const hrMax = [];

    weekData.activities.forEach(act => {
        // Use a short name for labels
        let shortName = act.name.replace(weekData.week + ' - ', '');
        if (shortName.length > 20) shortName = shortName.substring(0, 20) + '...';
        labels.push(shortName);

        const summary = extractActivitySummary(act);
        if (summary) {
            distances.push(summary.distanza || 0);
            hrAvg.push(summary.fc_media || 0);
            hrMax.push(summary.fc_max || 0);
        } else {
            distances.push(0);
            hrAvg.push(0);
            hrMax.push(0);
        }
    });

    renderWeeklyDistChart(labels, distances);
    renderWeeklyHrChart(labels, hrAvg, hrMax);
}

function renderWeeklyDistChart(labels, distances) {
    const ctx = document.getElementById('weeklyDistanceChart').getContext('2d');
    
    if (weeklyDistChartInst) {
        weeklyDistChartInst.destroy();
    }

    weeklyDistChartInst = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Distanza (km)',
                data: distances,
                backgroundColor: 'rgba(16, 185, 129, 0.8)',
                borderColor: '#10b981',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(255, 255, 255, 0.05)' }
                },
                x: {
                    grid: { display: false },
                    ticks: {
                        maxRotation: 45,
                        minRotation: 45
                    }
                }
            }
        }
    });
}

function renderWeeklyHrChart(labels, hrAvg, hrMax) {
    const ctx = document.getElementById('weeklyHrChart').getContext('2d');
    
    if (weeklyHrChartInst) {
        weeklyHrChartInst.destroy();
    }

    weeklyHrChartInst = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    type: 'line',
                    label: 'FC Max',
                    data: hrMax,
                    borderColor: '#f43f5e',
                    backgroundColor: '#f43f5e',
                    borderWidth: 2,
                    borderDash: [5, 5],
                    pointRadius: 4
                },
                {
                    type: 'bar',
                    label: 'FC Media',
                    data: hrAvg,
                    backgroundColor: 'rgba(236, 72, 153, 0.7)',
                    borderColor: '#ec4899',
                    borderWidth: 1,
                    borderRadius: 4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: '#f8fafc', usePointStyle: true }
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    min: 100, // typically HR doesn't drop below 100 during run
                    grid: { color: 'rgba(255, 255, 255, 0.05)' }
                },
                x: {
                    grid: { display: false },
                    ticks: {
                        maxRotation: 45,
                        minRotation: 45
                    }
                }
            }
        }
    });
}

// Start
document.addEventListener('DOMContentLoaded', loadData);
