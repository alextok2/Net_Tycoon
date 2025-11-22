document.addEventListener('DOMContentLoaded', () => {
    
    // --- DATA & STATE ---
    let devices = [];
    let criteriaList = [];
    let editingCritIndex = -1;

    // DOM Elements (Django Form Fields)
    const inputTopo = document.getElementById('id_topology_data');
    const inputAllowed = document.getElementById('id_allowed_devices');
    const inputCrit = document.getElementById('id_success_criteria');

    // --- UTILS ---
    function safeParse(input) {
        if (!input) return null;
        if (typeof input === 'object') return input;
        try {
            let result = JSON.parse(input);
            if (typeof result === 'string') {
                try { return JSON.parse(result); } catch (e) { return result; }
            }
            return result;
        } catch (e) {
            console.error("JSON Parse Error:", e);
            return {};
        }
    }

    // --- INITIALIZATION ---
    function initData() {
        const rawTopo = inputTopo.value;
        const rawCrit = inputCrit.value;

        try {
            const topoObj = safeParse(rawTopo) || { nodes: [] };
            devices = topoObj.nodes || [];
            
            const critObj = safeParse(rawCrit) || {};
            
            // Flatten Criteria Tree -> List
            for (const [devId, reqs] of Object.entries(critObj)) {
                if (reqs.hostname) {
                    criteriaList.push({ dev: devId, type: 'hostname', val: reqs.hostname });
                }
                if (reqs.config_checks && Array.isArray(reqs.config_checks)) {
                    reqs.config_checks.forEach(check => {
                        const path = check.path || [];
                        if (path.includes("description")) {
                            criteriaList.push({ dev: devId, type: 'desc', iface: path[1], val: check.value });
                        } else if (path.includes("ip_address")) {
                            criteriaList.push({ dev: devId, type: 'ip', iface: path[1], val: check.value });
                        }
                    });
                }
            }
        } catch(e) { 
            console.error("Init error", e); 
        }
        
        renderDevices();
        renderCriteria();
        updateInterfaceList(); // Init interface list based on first device
    }

    // --- RENDERING ---

    function renderDevices() {
        const tbody = document.querySelector('#devicesTable tbody');
        const select = document.getElementById('critDevice');
        
        tbody.innerHTML = '';
        select.innerHTML = '';
        
        devices.forEach((d, idx) => {
            // Table Row
            const row = `<tr>
                <td>${d.id}</td>
                <td>${d.type || 'router'}</td>
                <td>${d.ip || ''}</td>
                <td><button type="button" class="btn-del" onclick="window.labEditor.delDevice(${idx})">X</button></td>
            </tr>`;
            tbody.innerHTML += row;
            
            // Select Option
            const opt = document.createElement('option');
            opt.value = d.id;
            opt.textContent = d.id;
            select.appendChild(opt);
        });
    }

    function renderCriteria() {
        const tbody = document.querySelector('#criteriaTable tbody');
        tbody.innerHTML = '';
        
        criteriaList.forEach((c, idx) => {
            let paramName = c.type;
            let detail = '-';
            if (c.type === 'desc') { paramName = 'Description'; detail = c.iface; }
            if (c.type === 'ip') { paramName = 'IP Address'; detail = c.iface; }
            if (c.type === 'hostname') { paramName = 'Hostname'; }
            
            const bgStyle = (idx === editingCritIndex) ? 'background-color: #fff3cd;' : '';

            const row = `<tr style="${bgStyle}">
                <td>${c.dev}</td>
                <td>${paramName}</td>
                <td>${detail}</td>
                <td><strong>${c.val}</strong></td>
                <td>
                    <button type="button" class="btn-edit" onclick="window.labEditor.editCriteria(${idx})" title="Edit">✎</button>
                    <button type="button" class="btn-del" onclick="window.labEditor.delCriteria(${idx})" title="Delete">X</button>
                </td>
            </tr>`;
            tbody.innerHTML += row;
        });
    }

    // --- ACTIONS (Exported to window.labEditor) ---

    const actions = {
        addDevice: () => {
            const id = document.getElementById('newDevName').value.trim();
            const type = document.getElementById('newDevType').value;
            const ip = document.getElementById('newDevIp').value.trim();
            
            if(!id) return alert("Введите имя");
            if(devices.find(d => d.id === id)) return alert("Имя занято");
            
            devices.push({ id, type, ip });
            document.getElementById('newDevName').value = '';
            renderDevices();
            updateInterfaceList();
        },

        delDevice: (idx) => {
            devices.splice(idx, 1);
            renderDevices();
            updateInterfaceList();
        },

        toggleCritInputs: () => {
            const type = document.getElementById('critType').value;
            const ifaceSelect = document.getElementById('critIfaceSelect');
            if (type === 'hostname') ifaceSelect.style.display = 'none';
            else {
                ifaceSelect.style.display = 'block';
                actions.updateInterfaceList();
            }
        },

        updateInterfaceList: () => {
            const devId = document.getElementById('critDevice').value;
            const select = document.getElementById('critIfaceSelect');
            select.innerHTML = '';
            
            const device = devices.find(d => d.id === devId);
            const type = device ? (device.type || 'router') : 'router';
            
            let ports = [];
            if (type === 'router') {
                ports = ['FastEthernet0/0', 'FastEthernet0/1', 'Serial0/0/0'];
            } else {
                for (let i = 1; i <= 24; i++) ports.push(`FastEthernet0/${i}`);
                ports.push('GigabitEthernet1/1', 'GigabitEthernet1/2');
            }
            
            ports.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p; opt.textContent = p; select.appendChild(opt);
            });
        },

        addOrUpdateCriteria: () => {
            const dev = document.getElementById('critDevice').value;
            if (!dev) return alert("Нет устройств");
            
            const type = document.getElementById('critType').value;
            const val = document.getElementById('critValue').value.trim();
            const iface = document.getElementById('critIfaceSelect').value;
            
            if (!val) return alert("Введите значение");
            if (type !== 'hostname' && !iface) return alert("Выберите интерфейс");

            const newItem = { dev, type, val, iface };

            if (editingCritIndex === -1) {
                criteriaList.push(newItem);
                document.getElementById('critValue').value = ''; // Clear on add
            } else {
                criteriaList[editingCritIndex] = newItem;
                actions.resetCritForm();
            }
            renderCriteria();
        },

        editCriteria: (idx) => {
            const item = criteriaList[idx];
            document.getElementById('critDevice').value = item.dev;
            actions.updateInterfaceList();
            
            document.getElementById('critType').value = item.type;
            actions.toggleCritInputs();
            
            if (item.iface) document.getElementById('critIfaceSelect').value = item.iface;
            document.getElementById('critValue').value = item.val;

            editingCritIndex = idx;
            const btn = document.getElementById('btnAddCrit');
            btn.textContent = "💾 Сохранить";
            btn.style.backgroundColor = "#007bff";
            document.getElementById('btnCancelCrit').style.display = "inline-block";
            renderCriteria();
        },

        resetCritForm: () => {
            document.getElementById('critValue').value = '';
            editingCritIndex = -1;
            const btn = document.getElementById('btnAddCrit');
            btn.textContent = "+ Добавить";
            btn.style.backgroundColor = "#28a745";
            document.getElementById('btnCancelCrit').style.display = "none";
            renderCriteria();
        },

        delCriteria: (idx) => {
            if (idx === editingCritIndex) actions.resetCritForm();
            criteriaList.splice(idx, 1);
            if (idx < editingCritIndex && editingCritIndex !== -1) editingCritIndex--;
            renderCriteria();
        },

        submitBuilder: () => {
            const topology = { nodes: devices };
            const allowed = devices.map(d => d.id);

            const criteriaObj = {};
            devices.forEach(d => criteriaObj[d.id] = {});

            criteriaList.forEach(c => {
                if (!criteriaObj[c.dev]) criteriaObj[c.dev] = {};
                if (c.type === 'hostname') {
                    criteriaObj[c.dev]['hostname'] = c.val;
                } else {
                    if (!criteriaObj[c.dev]['config_checks']) criteriaObj[c.dev]['config_checks'] = [];
                    let path = [];
                    if (c.type === 'desc') path = ["interfaces", c.iface, "description"];
                    if (c.type === 'ip') path = ["interfaces", c.iface, "ip_address"];
                    
                    criteriaObj[c.dev]['config_checks'].push({ path: path, value: c.val });
                }
            });

            inputTopo.value = JSON.stringify(topology);
            inputAllowed.value = JSON.stringify(allowed);
            inputCrit.value = JSON.stringify(criteriaObj);

            document.getElementById('labForm').submit();
        }
    };

    // Expose actions to global scope for HTML onclick
    window.labEditor = actions;

    // Start
    initData();
});