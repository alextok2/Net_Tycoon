// static/js/office.js

document.addEventListener('DOMContentLoaded', () => {
    // --- УПРАВЛЕНИЕ ОКНАМИ ---
    const inboxModal = document.getElementById('inboxModal');
    const workbenchModal = document.getElementById('workbenchModal');

    window.openInbox = () => { inboxModal.style.display = 'flex'; showEmailList(); };
    window.closeInbox = () => { inboxModal.style.display = 'none'; };
    window.closeWorkbench = () => { workbenchModal.style.display = 'none'; };

    // --- ЛОГИКА ПОЧТЫ ---
    window.openEmail = (labId) => {
        // Скрываем список, показываем детали
        document.getElementById('email-list').style.display = 'none';
        
        // Скрываем все детальные блоки
        document.querySelectorAll('.email-detail-view').forEach(el => el.style.display = 'none');
        
        // Показываем нужный
        const detailView = document.getElementById(`email-detail-${labId}`);
        if(detailView) {
            detailView.style.display = 'flex';
        }
    };

    window.showEmailList = () => {
        document.querySelectorAll('.email-detail-view').forEach(el => el.style.display = 'none');
        document.getElementById('email-list').style.display = 'block';
    };

    // --- ЛОГИКА ВЕРСТАКА ---
    let powerOn = false;
    let consoleOn = false;

    window.openWorkbench = () => {
        workbenchModal.style.display = 'flex';
        // Сброс
        powerOn = false; consoleOn = false;
        document.getElementById('led-pwr').setAttribute('fill', '#333');
        document.getElementById('btn-terminal').style.display = 'none';
        document.getElementById('cable-power').style.transform = 'translate(0,0)';
        document.getElementById('cable-console').style.transform = 'translate(0,0)';
        updateWbStatus();
    };

    window.connectPower = () => {
        if(powerOn) return;
        document.getElementById('cable-power').style.transform = 'translate(0, -250px)';
        setTimeout(() => {
            powerOn = true;
            document.getElementById('led-pwr').setAttribute('fill', '#2ecc71');
            document.getElementById('fan').style.animation = "spin 0.5s linear infinite";
            updateWbStatus();
        }, 500);
    };

    window.connectConsole = () => {
        if(consoleOn) return;
        document.getElementById('cable-console').style.transform = 'translate(-40px, -270px)';
        setTimeout(() => {
            consoleOn = true;
            updateWbStatus();
        }, 500);
    };

    function updateWbStatus() {
        const txt = `PWR: ${powerOn ? 'ON' : 'OFF'} | CONSOLE: ${consoleOn ? 'CONNECTED' : '--'}`;
        document.getElementById('wb-status').innerText = txt;
        if(powerOn && consoleOn) {
            document.getElementById('btn-terminal').style.display = 'block';
        }
    }
});