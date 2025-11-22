document.addEventListener('DOMContentLoaded', () => {

    // --- DATA LOADING ---
    const getDjangoData = (id) => {
        const el = document.getElementById(id);
        try {
            return el ? JSON.parse(el.textContent) : null;
        } catch (e) {
            console.error("Error parsing JSON for", id, e);
            return null;
        }
    };

    const SESSION_ID = getDjangoData("session-id");
    const hostnamesMap = getDjangoData("hostnames-data") || {};
    const initialLogs = getDjangoData("initial-logs-data") || [];
    let currentDevice = getDjangoData("current-device-id") || "R1";

    // --- DOM ELEMENTS ---
    const inputEl = document.getElementById('cmd-input');
    const inputLineContainer = document.getElementById('active-input-line');
    const outputEl = document.getElementById('terminal-output');
    const promptEl = document.getElementById('prompt');
    const wrapper = document.getElementById('terminal-wrapper');

    // Если критические элементы не найдены, останавливаемся (чтобы не сыпать ошибками)
    if (!inputEl || !inputLineContainer || !outputEl) {
        console.error("Terminal DOM elements missing!");
        return;
    }

    // --- STATE ---
    let commandHistory = [];
    let historyIndex = -1;

    // --- DICTIONARIES ---
    const VOCAB_COMMON = ["show", "running-config", "interface", "ip", "address", "brief", "configure", "terminal", "enable", "exit", "end", "no", "shutdown", "description", "hostname", "write", "copy", "do", "line", "vty", "console", "login", "password", "FastEthernet0/0", "FastEthernet0/1", "service", "password-encryption"];
    const VOCAB_ROUTER = ["crypto", "isakmp", "policy", "encryption", "authentication", "group", "pre-share", "key", "transform-set", "esp-aes", "esp-sha-hmac", "access-list", "permit", "udp", "tcp", "host", "any", "match", "set", "peer", "map"];
    const VOCAB_SWITCH = ["vlan", "name", "switchport", "mode", "access", "trunk", "native", "allowed", "spanning-tree", "port-security"];
    let activeVocabulary = [...VOCAB_COMMON, ...VOCAB_ROUTER];

    // --- CORE FUNCTIONS ---

    function scrollToBottom() { 
        wrapper.scrollTop = wrapper.scrollHeight; 
    }

    function updateMirror() {
        const val = inputEl.value;
        const cursorPos = inputEl.selectionStart;

        // Очищаем контейнер: удаляем всё, что идет ПОСЛЕ элемента promptEl
        // Это защищает сам promptEl от удаления
        while (promptEl.nextSibling) {
            inputLineContainer.removeChild(promptEl.nextSibling);
        }

        const beforeCursor = val.slice(0, cursorPos);
        const atCursor = val.slice(cursorPos, cursorPos + 1);
        const afterCursor = val.slice(cursorPos + 1);

        // 1. Текст до курсора
        const spanBefore = document.createElement('span');
        spanBefore.textContent = beforeCursor;
        inputLineContainer.appendChild(spanBefore);

        // 2. Курсор
        const cursorSpan = document.createElement('span');
        cursorSpan.className = 'cursor';
        if (atCursor) {
            cursorSpan.textContent = atCursor;
            cursorSpan.classList.add('cursor-block');
        } else {
            cursorSpan.innerHTML = '&nbsp;';
        }
        inputLineContainer.appendChild(cursorSpan);

        // 3. Текст после курсора
        if (afterCursor) {
            const spanAfter = document.createElement('span');
            spanAfter.textContent = afterCursor;
            inputLineContainer.appendChild(spanAfter);
        }
        scrollToBottom();
    }


    function appendOutput(text, isCmd = false, customPrompt = null) {
        const div = document.createElement('div');
        div.className = 'log-line';
        if (isCmd) {
            const p = customPrompt || promptEl.textContent;
            div.textContent = `${p} ${text}`;
            div.style.fontWeight = 'bold';
        } else {
            div.textContent = text.replace(/^\n+|\n+$/g, '');
            if (!div.textContent && text.length > 0) div.innerHTML = '&nbsp;';
        }
        
        // !!! ИСПРАВЛЕНИЕ: Вставляем перед строкой ввода, а не перед ее родителем !!!
        outputEl.insertBefore(div, inputLineContainer); 
        
        scrollToBottom();
    }

    function renderLogs(logs) {
        document.querySelectorAll('.log-line').forEach(el => el.remove());
        if (Array.isArray(logs)) {
            logs.forEach(entry => {
                if (entry.type === 'cmd') appendOutput(entry.text, true, entry.prompt);
                else appendOutput(entry.text, false);
            });
        }
        scrollToBottom();
    }

    function updateDeviceLabels(deviceId, newLabel) {
        const tab = document.getElementById(`tab-${deviceId}`);
        if (tab) tab.textContent = newLabel;
        const labelNode = document.getElementById(`label-${deviceId}`);
        if (labelNode) labelNode.textContent = newLabel;
    }

    // Экспорт функций в глобальную область для onclick в HTML
    window.lab = {
        switchInfoTab: (t) => {
            document.querySelectorAll('.info-tab').forEach(e => e.classList.remove('active'));
            document.querySelectorAll('.content-area').forEach(e => e.classList.add('hidden'));
            document.querySelector(`.info-tab[onclick="lab.switchInfoTab('${t}')"]`).classList.add('active');
            document.getElementById(`tab-${t}`).classList.remove('hidden');
        },

        switchDevice: async (targetDeviceName) => {
            if (targetDeviceName === currentDevice) return;

            document.querySelectorAll('.device-tab').forEach(t => t.classList.remove('active'));
            const activeTab = document.getElementById(`tab-${targetDeviceName}`);
            if (activeTab) activeTab.classList.add('active');

            document.querySelectorAll('.node-wrapper').forEach(node => node.classList.remove('active-node'));
            const activeNode = document.getElementById(`node-${targetDeviceName}`);
            if (activeNode) activeNode.classList.add('active-node');

            try {
                const res = await fetch(`/api/lab/${SESSION_ID}/switch/${targetDeviceName}/`);
                const data = await res.json();

                if (data.status === 'ok') {
                    currentDevice = targetDeviceName;
                    promptEl.textContent = data.prompt;
                    renderLogs(data.logs);

                    inputEl.value = '';
                    updateMirror();
                    inputEl.focus();

                    if (data.device_type === 'switch') activeVocabulary = [...VOCAB_COMMON, ...VOCAB_SWITCH];
                    else activeVocabulary = [...VOCAB_COMMON, ...VOCAB_ROUTER];
                } else {
                    alert("Error: " + data.message);
                }
            } catch (e) { console.error(e); }
        }
    };

    async function sendCommand(cmd, isHelp) {
        inputEl.disabled = true;
        appendOutput(cmd + (isHelp ? '?' : ''), true);

        if (!isHelp) {
            inputEl.value = '';
            updateMirror();
            if (cmd.trim()) {
                if (commandHistory[commandHistory.length - 1] !== cmd) commandHistory.push(cmd);
                historyIndex = -1;
            }
        }

        try {
            const res = await fetch(`/api/lab/${SESSION_ID}/command/`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: isHelp ? cmd + '?' : cmd })
            });
            const data = await res.json();

            if (data.output) appendOutput(data.output);
            promptEl.textContent = data.prompt;
            if (data.new_hostname) updateDeviceLabels(currentDevice, data.new_hostname);
            
            if (data.completed) {
                const status = document.getElementById('lab-status');
                if(status) { status.textContent = "DONE ✅"; status.style.color = "green"; }
            }
        } catch (e) { appendOutput(`% Error: ${e.message}`); }
        finally {
            inputEl.disabled = false;
            inputEl.focus();
            scrollToBottom();
        }
    }

    // --- EVENT LISTENERS ---

    ['input', 'keyup', 'click', 'focus'].forEach(evt => {
        inputEl.addEventListener(evt, () => setTimeout(updateMirror, 0));
    });

    wrapper.addEventListener('click', () => {
        if (window.getSelection().toString().length === 0) { inputEl.focus(); wrapper.classList.remove('blur'); }
    });
    inputEl.addEventListener('blur', () => wrapper.classList.add('blur'));

    inputEl.addEventListener('keydown', function (e) {
        setTimeout(updateMirror, 0);

        if (e.key === '?') { e.preventDefault(); sendCommand(this.value, true); return; }

        if (e.key === 'Tab') {
            e.preventDefault();
            const val = this.value; if (!val) return;
            const parts = val.split(' ');
            const last = parts[parts.length - 1]; if (!last) return;

            const matches = activeVocabulary.filter(c => c.toLowerCase().startsWith(last.toLowerCase()));
            if (matches.length === 0) return;

            if (matches.length === 1) {
                parts[parts.length - 1] = matches[0];
                this.value = parts.join(' ') + ' ';
            } else {
                let common = matches[0];
                for (let i = 1; i < matches.length; i++) {
                    while (!matches[i].toLowerCase().startsWith(common.toLowerCase())) common = common.substring(0, common.length - 1);
                }
                if (common.length > last.length) parts[parts.length - 1] = common;
            }
            this.value = parts.join(' ');
            return;
        }

        if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (commandHistory.length > 0) {
                if (historyIndex === -1) historyIndex = commandHistory.length - 1;
                else if (historyIndex > 0) historyIndex--;
                this.value = commandHistory[historyIndex];
            }
            return;
        }
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (historyIndex > -1) {
                if (historyIndex < commandHistory.length - 1) {
                    historyIndex++;
                    this.value = commandHistory[historyIndex];
                } else {
                    historyIndex = -1;
                    this.value = '';
                }
            }
            return;
        }

        if (e.key === 'Enter') {
            sendCommand(this.value, false);
        }
    });

    // --- INITIALIZATION ---
    function init() {
        // Labels
        for (const [devId, hostname] of Object.entries(hostnamesMap)) {
            updateDeviceLabels(devId, hostname);
        }
        // Active Node
        const startNode = document.getElementById(`node-${currentDevice}`);
        if (startNode) startNode.classList.add('active-node');
        
        // Logs
        renderLogs(initialLogs);
        
        // Focus
        inputEl.focus();
        updateMirror();
    }

    // Run
    init();

});