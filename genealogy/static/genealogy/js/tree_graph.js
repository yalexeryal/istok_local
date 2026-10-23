// === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
let cy = null;
let currentData = null;
let currentLayout = 'hierarchy';
let currentCenterPersonId = null;
let dagreAvailable = false;

// === ALPINE.JS ДЛЯ УПРАВЛЕНИЯ ВИДОМ, ФИЛЬТРАМИ И ТАБЛИЦЕЙ ===
document.addEventListener('alpine:init', () => {
    Alpine.data('personTable', () => ({
        view: 'hierarchy',
        scope: 'relatives',
        filteredPersonIds: new Set(),
        search: '',
        filterGender: '',
        filterAlive: '',
        sortKey: 'last_name',
        sortAsc: true,
        persons: PERSONS_DATA,

        init() {
            window.treeDataManager = this;

            this.$watch('view', (newVal) => {
                if ((newVal === 'hierarchy' || newVal === 'graph') && typeof window.renderGraph === 'function') {
                    currentLayout = newVal;
                    const loadingEl = document.getElementById('cy-loading');
                    if (loadingEl) loadingEl.style.display = 'flex';
                    window.renderGraph();
                } else if (newVal === 'ancestors' && typeof window.renderAncestorsFan === 'function') {
                    window.renderAncestorsFan();
                }
            });
            this.loadData();
        },

        async loadData(centerPersonId = null) {
            const loadingEl = document.getElementById('cy-loading');
            if (loadingEl) {
                loadingEl.style.display = 'flex';
                loadingEl.innerHTML = `<div class="text-center"><div class="text-4xl mb-2 animate-spin">🌳</div><p class="text-gray-500">Загрузка дерева...</p></div>`;
            }

            try {
                let url = `/api/tree/${TREE_PK}/hierarchy/?scope=${this.scope}`;
                if (centerPersonId) url += `&center_person=${centerPersonId}`;

                const response = await fetch(url);
                if (!response.ok) throw new Error(`HTTP ошибка: ${response.status}`);

                currentData = await response.json();
                currentCenterPersonId = currentData.center_person ? String(currentData.center_person) : null;
                this.filteredPersonIds = new Set(currentData.nodes.map(n => String(n.id)));

                if (!currentData.nodes || currentData.nodes.length === 0) {
                    if (loadingEl) {
                        loadingEl.innerHTML = `<div class="text-center text-gray-500"><div class="text-4xl mb-2">📭</div><p>Персоны не найдены</p></div>`;
                        loadingEl.querySelector('.animate-spin').style.display = 'none';
                    }
                    return;
                }

                if (this.view === 'hierarchy' || this.view === 'graph') {
                    window.renderGraph();
                }
            } catch (error) {
                console.error("Ошибка загрузки:", error);
                if (loadingEl) {
                    loadingEl.innerHTML = `<div class="text-center text-red-500"><div class="text-4xl mb-2">⚠️</div><p>Не удалось загрузить данные. Проверьте консоль (F12).</p></div>`;
                    loadingEl.querySelector('.animate-spin')?.remove();
                }
            }
        },

        get filteredPersons() {
            let result = this.persons.filter(p => this.filteredPersonIds.has(String(p.id)));
            result = result.filter(p => {
                const matchesSearch = p.full_name.toLowerCase().includes(this.search.toLowerCase());
                const matchesGender = this.filterGender === '' || p.gender === this.filterGender;
                let matchesAlive = true;
                if (this.filterAlive === 'alive') matchesAlive = p.is_alive === true;
                else if (this.filterAlive === 'deceased') matchesAlive = p.is_alive === false;
                return matchesSearch && matchesGender && matchesAlive;
            });
            result.sort((a, b) => {
                let valA = a[this.sortKey] || '';
                let valB = b[this.sortKey] || '';
                if (valA < valB) return this.sortAsc ? -1 : 1;
                if (valA > valB) return this.sortAsc ? 1 : -1;
                return 0;
            });
            return result;
        },

        switchView(newView) {
            this.view = newView;
        },

        sort(field) {
            if (this.sortKey === field) {
                this.sortAsc = !this.sortAsc;
            } else {
                this.sortKey = field;
                this.sortAsc = true;
            }
        },

        resetFilters() {
            this.search = '';
            this.filterGender = '';
            this.filterAlive = '';
        }
    }));
});

function getAgeWord(age) {
    const lastTwo = age % 100;
    const lastOne = age % 10;
    if (lastTwo >= 11 && lastTwo <= 14) return 'лет';
    if (lastOne === 1) return 'год';
    if (lastOne >= 2 && lastOne <= 4) return 'года';
    return 'лет';
}

function formatDate(dateStr, isApprox) {
    if (!dateStr || dateStr === "null" || dateStr === "") return "?";
    const date = new Date(dateStr);
    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const year = date.getFullYear();
    const prefix = isApprox ? '~' : '';
    return `${prefix}${day}.${month}.${year}`;
}

function calculateAge(birthDate, deathDate) {
    if (!birthDate || birthDate === "null" || birthDate === "") return null;
    const birth = new Date(birthDate);
    const end = (deathDate && deathDate !== "null" && deathDate !== "") ? new Date(deathDate) : new Date();
    let age = end.getFullYear() - birth.getFullYear();
    const monthDiff = end.getMonth() - birth.getMonth();
    if (monthDiff < 0 || (monthDiff === 0 && end.getDate() < birth.getDate())) age--;
    return age;
}

function prepareElements(data) {
    if (!data || !data.nodes) return [];
    const nodes = data.nodes.map(n => {
        const isDead = n.death_date && n.death_date !== "null" && n.death_date !== "";
        let line1 = n.last_name || "";
        if (n.maiden_name && n.maiden_name !== "null" && String(n.maiden_name).trim() !== "") {
            line1 += ` (${n.maiden_name})`;
        }
        let line2 = [n.first_name, n.middle_name].filter(p => p && p !== "null" && String(p).trim() !== "").join(' ');
        if (!line2) line2 = n.label || "Не указано";

        const birthFormatted = formatDate(n.birth_date, n.is_birth_date_approx);
        const deathFormatted = isDead ? formatDate(n.death_date, n.is_death_date_approx) : "";
        const age = calculateAge(n.birth_date, n.death_date);

        let line3 = "";
        if (birthFormatted !== "?" || deathFormatted) {
            line3 = birthFormatted;
            if (deathFormatted) line3 += ` - ${deathFormatted}`;
            if (age !== null) line3 += ` • ${age} ${getAgeWord(age)}`;
        } else {
            line3 = "?";
        }

        return {
            data: {
                id: String(n.id),
                label: `${line1}\n${line2}\n${line3}`,
                gender: n.gender || "unknown",
                death_date: n.death_date
            },
            classes: isDead ? 'dead' : ''
        };
    });

    const edges = (data.links || []).map((l, idx) => {
        const edgeType = (l.type || '').toLowerCase().replace(/-/g, '_').replace(/ /g, '_');

        let ruLabel = 'Связь';
        if (edgeType === 'biological_parent') ruLabel = 'Родитель';
        else if (edgeType === 'adoptive_parent') ruLabel = 'Приемный род.';
        else if (edgeType === 'spouse') ruLabel = 'Супруг(а)';
        else if (edgeType === 'step_parent') ruLabel = 'Отчим/Мачеха';

        return {
            data: {
                id: `e${idx}`,
                source: String(l.source),
                target: String(l.target),
                type: edgeType,
                label: ruLabel
            }
        };
    });
    return [...nodes, ...edges];
}

function renderGraph() {
    if (!currentData) return;
    if (cy) cy.destroy();

    const cyContainer = document.getElementById('cy');
    const loadingEl = document.getElementById('cy-loading');

    const isMobile = window.innerWidth < 768;
    const nodeWidth = isMobile ? 120 : 160;
    const nodeHeight = isMobile ? 80 : 100;
    const fontSize = isMobile ? '9px' : '11px';
    const textMaxWidth = isMobile ? '110px' : '150px';

    let layoutOptions = (currentLayout === 'hierarchy' && dagreAvailable) ? {
        name: 'dagre',
        rankDir: 'TB',
        nodeSep: 30,
        rankSep: 60,
        edgeSep: 15,
        spacingFactor: 1.1,
        fit: false,
        padding: 30
    } : {
        name: 'cose',
        animate: false,
        nodeDimensionsIncludeLabels: true,
        idealEdgeLength: 80,
        nodeOverlap: 15,
        padding: 20,
        fit: false
    };

    cy = cytoscape({
        container: cyContainer,
        elements: prepareElements(currentData),
        style: [
            {
                selector: 'node',
                style: {
                    'label': 'data(label)',
                    'text-wrap': 'wrap',
                    'text-max-width': textMaxWidth,
                    'text-valign': 'center',
                    'text-halign': 'center',
                    'font-size': fontSize,
                    'font-weight': 'bold',
                    'color': '#1f2937',
                    'background-color': '#dbeafe',
                    'border-width': 2,
                    'border-color': '#3b82f6',
                    'width': nodeWidth,
                    'height': nodeHeight,
                    'shape': 'round-rectangle',
                    'padding': '8px'
                }
            },
            { selector: 'node[gender = "male"]', style: { 'background-color': '#dbeafe', 'border-color': '#3b82f6' } },
            { selector: 'node[gender = "female"]', style: { 'background-color': '#fce7f3', 'border-color': '#ec4899' } },
            { selector: 'node[gender = "unknown"]', style: { 'background-color': '#f3f4f6', 'border-color': '#9ca3af' } },
            { selector: 'node[gender = "male"].dead', style: { 'background-color': '#bfdbfe', 'border-color': '#000000', 'border-width': 3, 'text-opacity': 0.7 } },
            { selector: 'node[gender = "female"].dead', style: { 'background-color': '#fbcfe8', 'border-color': '#000000', 'border-width': 3, 'text-opacity': 0.7 } },
            { selector: 'node[gender = "unknown"].dead', style: { 'background-color': '#e5e7eb', 'border-color': '#000000', 'border-width': 3, 'text-opacity': 0.7 } },
            {
                selector: currentCenterPersonId ? `node[id = '${currentCenterPersonId}']` : 'node[id = "___none___"]',
                style: { 'border-width': 4, 'border-color': '#eab308', 'background-color': '#fef9c3' }
            },
            {
                selector: 'edge',
                style: {
                    'width': 1.5,
                    'line-color': '#9ca3af',
                    'target-arrow-color': '#9ca3af',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier',
                    'label': 'data(label)',
                    'font-size': '10px',
                    'font-weight': 'bold',
                    'color': '#4b5563',
                    'text-background-color': '#ffffff',
                    'text-background-opacity': 0.9,
                    'text-background-padding': '3px',
                    'text-background-shape': 'roundrectangle',
                    'text-margin-y': -8
                }
            },
            {
                selector: 'edge[type="biological_parent"]',
                style: {
                    'width': 2.5,
                    'line-color': '#3b82f6',
                    'target-arrow-color': '#3b82f6',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier'
                }
            },
            {
                selector: 'edge[type="adoptive_parent"]',
                style: {
                    'width': 2.5,
                    'line-color': '#3b82f6',
                    'line-style': 'dashed',
                    'target-arrow-color': '#3b82f6',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier'
                }
            },
            {
                selector: 'edge[type="spouse"]',
                style: {
                    'width': 3,
                    'line-color': '#a855f7',
                    'line-style': 'solid',
                    'target-arrow-shape': 'none',
                    'source-arrow-shape': 'none',
                    'curve-style': 'bezier'
                }
            },
            {
                selector: 'edge[type="step_parent"]',
                style: {
                    'width': 1.5,
                    'line-color': '#9ca3af',
                    'line-style': 'dotted',
                    'target-arrow-color': '#9ca3af',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier'
                }
            }
        ],
        minZoom: 0.2,
        maxZoom: 3,
        wheelSensitivity: 0.5
    });

    window.cy = cy;

    const layout = cy.layout(layoutOptions);
    layout.on('layoutstop', function () {
        cy.fit(null, 50);
        if (loadingEl) loadingEl.style.display = 'none';
    });
    layout.run();

    cy.on('tap', 'node', function (evt) {
        showPersonSidebar(evt.target.id(), evt.target.data());
    });
}

async function renderAncestorsFan() {
    const fanContainer = document.getElementById('ancestors-fan');
    try {
        const url = `/api/tree/${TREE_PK}/ancestors/?center_person=${currentCenterPersonId || ''}`;
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ошибка: ${response.status}`);
        const data = await response.json();
        if (!data.generations || data.generations.length === 0) {
            fanContainer.innerHTML = `<div class="text-center text-gray-500"><div class="text-4xl mb-2">📭</div><p>Предки не найдены</p></div>`;
            return;
        }
        renderFanSVG(data, fanContainer);
    } catch (error) {
        fanContainer.innerHTML = `<div class="text-center text-red-500"><div class="text-4xl mb-2">️</div><p>Не удалось загрузить предков</p></div>`;
    }
}

function renderFanSVG(data, container) {
    const width = container.clientWidth;
    const height = container.clientHeight;
    const centerX = width / 2;
    const centerY = height;
    const maxRadius = Math.min(width, height) * 0.9;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', width);
    svg.setAttribute('height', height);
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);

    const generations = data.generations;
    const numGenerations = generations.length;

    for (let gen = 0; gen < numGenerations; gen++) {
        const innerRadius = (gen / numGenerations) * maxRadius;
        const outerRadius = ((gen + 1) / numGenerations) * maxRadius;
        const persons = generations[gen];
        const numPersons = persons.length;
        if (numPersons === 0) continue;

        const angleStep = Math.PI / numPersons;
        for (let i = 0; i < numPersons; i++) {
            const person = persons[i];
            const startAngle = Math.PI + (i * angleStep);
            const endAngle = startAngle + angleStep;
            const path = createArcPath(centerX, centerY, innerRadius, outerRadius, startAngle, endAngle);

            const pathElement = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            pathElement.setAttribute('d', path);

            let fillColor = '#dbeafe', strokeColor = '#3b82f6';
            if (person.gender === 'female') { fillColor = '#fce7f3'; strokeColor = '#ec4899'; }
            else if (person.gender === 'unknown') { fillColor = '#f3f4f6'; strokeColor = '#9ca3af'; }

            if (gen === 0) { fillColor = '#fef9c3'; strokeColor = '#eab308'; }
            if (person.death_date && person.death_date !== "null" && person.death_date !== "") {
                fillColor = '#e5e7eb'; strokeColor = '#000000';
            }

            pathElement.setAttribute('fill', fillColor);
            pathElement.setAttribute('stroke', strokeColor);
            pathElement.setAttribute('stroke-width', '2');
            pathElement.setAttribute('cursor', 'pointer');

            pathElement.addEventListener('click', () => showPersonSidebar(person.id, person));
            pathElement.addEventListener('mouseenter', () => pathElement.setAttribute('stroke-width', '4'));
            pathElement.addEventListener('mouseleave', () => pathElement.setAttribute('stroke-width', '2'));
            svg.appendChild(pathElement);

            const midAngle = (startAngle + endAngle) / 2;
            const textRadius = (innerRadius + outerRadius) / 2;
            const textX = centerX + textRadius * Math.cos(midAngle);
            const textY = centerY + textRadius * Math.sin(midAngle);

            const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            text.setAttribute('x', textX);
            text.setAttribute('y', textY);
            text.setAttribute('text-anchor', 'middle');
            text.setAttribute('dominant-baseline', 'middle');
            text.setAttribute('font-size', gen === 0 ? '14' : '11');
            text.setAttribute('font-weight', 'bold');
            text.setAttribute('fill', '#1f2937');
            text.setAttribute('pointer-events', 'none');

            const maxChars = gen === 0 ? 30 : 20;
            const displayName = person.label.length > maxChars ? person.label.substring(0, maxChars) + '...' : person.label;
            text.textContent = displayName + (person.death_date && person.death_date !== "null" ? ' †' : '');
            svg.appendChild(text);
        }
    }
    container.innerHTML = '';
    container.appendChild(svg);
}

function createArcPath(cx, cy, innerRadius, outerRadius, startAngle, endAngle) {
    const x1 = cx + outerRadius * Math.cos(startAngle);
    const y1 = cy + outerRadius * Math.sin(startAngle);
    const x2 = cx + outerRadius * Math.cos(endAngle);
    const y2 = cy + outerRadius * Math.sin(endAngle);
    const x3 = cx + innerRadius * Math.cos(endAngle);
    const y3 = cy + innerRadius * Math.sin(endAngle);
    const x4 = cx + innerRadius * Math.cos(startAngle);
    const y4 = cy + innerRadius * Math.sin(startAngle);
    const largeArcFlag = endAngle - startAngle > Math.PI ? 1 : 0;
    return `M ${x1} ${y1} A ${outerRadius} ${outerRadius} 0 ${largeArcFlag} 1 ${x2} ${y2} L ${x3} ${y3} A ${innerRadius} ${innerRadius} 0 ${largeArcFlag} 0 ${x4} ${y4} Z`;
}

function showPersonSidebar(personId, data) {
    const isDead = data.death_date && data.death_date !== "null" && data.death_date !== "";
    const isCenter = personId === currentCenterPersonId;
    const sidebar = document.getElementById('person-sidebar');
    const sidebarContent = document.getElementById('sidebar-content');
    const loadingEl = document.getElementById('cy-loading');

    const fmtDate = (dateStr) => {
        if (!dateStr || dateStr === "null") return null;
        return new Date(dateStr).toLocaleDateString('ru-RU', {day: 'numeric', month: 'long', year: 'numeric'});
    };

    let ageText = '';
    if (data.birth_date && data.birth_date !== "null") {
        const birth = new Date(data.birth_date);
        const end = isDead && data.death_date ? new Date(data.death_date) : new Date();
        let age = end.getFullYear() - birth.getFullYear();
        const m = end.getMonth() - birth.getMonth();
        if (m < 0 || (m === 0 && end.getDate() < birth.getDate())) age--;
        ageText = `${age} ${isDead ? '(на момент смерти)' : '(жив(а))'}`;
    }

    sidebarContent.innerHTML = `
        <div class="space-y-4">
            <div class="flex justify-center">
                ${data.photo_url ? `<img src="${data.photo_url}" alt="${data.label}" class="w-32 h-32 object-cover rounded-lg border-2 ${isDead ? 'border-gray-400 grayscale' : 'border-gray-300'}">` : `<div class="w-32 h-32 bg-gray-100 rounded-lg flex items-center justify-center border-2 border-gray-300"><span class="text-6xl text-gray-400">👤</span></div>`}
            </div>
            <div class="text-center">
                <h2 class="text-2xl font-bold text-gray-900">${data.label}</h2>
                ${isDead ? '<div class="text-sm text-gray-500 mt-1">✝ Умер(ла)</div>' : ''}
                ${isCenter ? '<div class="inline-block mt-2 px-3 py-1 bg-yellow-100 text-yellow-800 text-xs font-semibold rounded-full border border-yellow-300">⭐ Центральная персона</div>' : ''}
            </div>
            <div class="bg-gray-50 rounded-lg p-4 space-y-2 text-sm">
                <div class="flex justify-between"><span class="text-gray-500">Пол:</span><span class="font-medium text-gray-900">${data.gender === 'male' ? 'Мужской' : data.gender === 'female' ? 'Женский' : 'Не указан'}</span></div>
                ${fmtDate(data.birth_date) ? `<div class="flex justify-between"><span class="text-gray-500">Дата рождения:</span><span class="font-medium text-gray-900">${fmtDate(data.birth_date)}</span></div>` : ''}
                ${fmtDate(data.death_date) ? `<div class="flex justify-between"><span class="text-gray-500">Дата смерти:</span><span class="font-medium text-gray-900">${fmtDate(data.death_date)}</span></div>` : ''}
                ${ageText ? `<div class="flex justify-between"><span class="text-gray-500">Возраст:</span><span class="font-medium text-gray-900">${ageText}</span></div>` : ''}
            </div>
            <div class="space-y-2 pt-2">
                ${!isCenter ? `<button id="btn-make-center" class="w-full px-4 py-2.5 bg-yellow-500 text-white rounded-md hover:bg-yellow-600 transition font-medium flex items-center justify-center gap-2"><span>⭐</span><span>Сделать центральной фигурой</span></button>` : ''}
                <a href="/person/${personId}/" class="block w-full px-4 py-2.5 bg-blue-600 text-white text-center rounded-md hover:bg-blue-700 transition font-medium">📋 Открыть полную карточку</a>
            </div>
            <div class="text-xs text-gray-500 italic text-center pt-2 border-t border-gray-200">Кликните по другой персоне в графе, чтобы увидеть её карточку</div>
        </div>
    `;
    sidebar.classList.remove('translate-x-full');

    const btnMakeCenter = document.getElementById('btn-make-center');
    if (btnMakeCenter) {
        const newBtn = btnMakeCenter.cloneNode(true);
        btnMakeCenter.parentNode.replaceChild(newBtn, btnMakeCenter);

        newBtn.addEventListener('click', function () {
            sidebar.classList.add('translate-x-full');
            if (loadingEl) {
                loadingEl.style.display = 'flex';
                loadingEl.innerHTML = `<div class="text-center"><div class="text-4xl mb-2 animate-spin">🌳</div><p class="text-gray-500">Перестроение дерева...</p></div>`;
            }

            if (window.treeDataManager && typeof window.treeDataManager.loadData === 'function') {
                window.treeDataManager.loadData(personId);
            } else {
                console.error("Не удалось найти компонент управления деревом");
                if (loadingEl) loadingEl.style.display = 'none';
            }
        });
    }
}

function zoomInCy() {
    if (window.cy) window.cy.zoom(window.cy.zoom() * 1.3);
}

function zoomOutCy() {
    if (window.cy) window.cy.zoom(window.cy.zoom() / 1.3);
}

function fitCy() {
    if (window.cy) {
        window.cy.resize();
        window.cy.fit(window.cy.elements(), 50);
        window.cy.center();
    }
}

window.addEventListener('load', function () {
    if (typeof cytoscape === 'undefined') return;
    dagreAvailable = typeof dagre !== 'undefined' && typeof cytoscapeDagre !== 'undefined';
    if (dagreAvailable) cytoscape.use(cytoscapeDagre);

    const sidebar = document.getElementById('person-sidebar');
    const sidebarClose = document.getElementById('sidebar-close');
    sidebarClose.addEventListener('click', () => sidebar.classList.add('translate-x-full'));
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !sidebar.classList.contains('translate-x-full')) sidebar.classList.add('translate-x-full');
    });
});

// === ВИДЖЕТ БЛИЖАЙШИХ СОБЫТИЙ ===
document.addEventListener('DOMContentLoaded', function () {
    fetch(`/api/tree/${TREE_PK}/upcoming-events/`)
        .then(response => response.json())
        .then(data => {
            if (data.events && data.events.length > 0) {
                const list = document.getElementById('events-list');
                list.innerHTML = '';
                data.events.forEach(event => {
                    const word = getAgeWord(event.years);
                    const item = document.createElement('a');
                    item.href = `/person/${event.person_id}/`;
                    item.className = "flex items-start gap-3 p-2 rounded-md hover:bg-gray-50 transition cursor-pointer block no-underline";
                    item.innerHTML = `
                        <div class="text-2xl mt-0.5">${event.emoji}</div>
                        <div class="flex-1 min-w-0">
                            <div class="text-sm font-semibold text-gray-900 truncate">${event.date} — ${event.years} ${word}</div>
                            <div class="text-xs text-gray-600 truncate" title="${event.person_name}">${event.person_name}</div>
                        </div>
                    `;
                    list.appendChild(item);
                });
                document.getElementById('upcoming-events-widget').classList.remove('hidden');
            }
        })
        .catch(error => console.error('Ошибка загрузки событий:', error));
});