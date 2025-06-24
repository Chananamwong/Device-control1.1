// static/js/app.js
document.addEventListener('DOMContentLoaded', function() {

    const API_STATUS_URL = '/api/ahu_status';
    // URL ใหม่สำหรับส่งคำสั่ง
    const API_CONTROL_URL = '/api/control_ahu/'; 
    const POLLING_RATE_MS = 2000;
    const API_SET_TEMP_URL = '/api/set_temperature/';
    
    function updateAHUCard(ahuId, isOn) {
        const card = document.getElementById(`ahu-${ahuId}`);
        if (card) {
            if (isOn) {
                card.classList.add('is-on');
            } else {
                card.classList.remove('is-on');
            }
        }
        
    }

    async function handleTempControlButtonClick(event) {
        const button = event.currentTarget;
        const ahuId = button.dataset.ahuId;
        const action = button.dataset.action; // 'increase' or 'decrease'

        const tempDisplay = document.getElementById(`temp-display-${ahuId}`);
        if (!tempDisplay) return;

        // ดึงค่าอุณหภูมิปัจจุบัน (เอาเฉพาะตัวเลข)
        let currentTemp = parseFloat(tempDisplay.textContent);

        // เพิ่มหรือลดค่า
        let newTemp = (action === 'increase') ? currentTemp + 0.5 : currentTemp - 0.5;
        
        // อัปเดตหน้าเว็บทันทีเพื่อการตอบสนองที่ดี
        tempDisplay.textContent = newTemp.toFixed(1) + '°C';

        // ส่งคำสั่งไปที่ Backend
        try {
            const response = await fetch(`${API_SET_TEMP_URL}${ahuId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ temperature: newTemp.toFixed(1) })
            });

            const result = await response.json();

            if (result.success) {
                console.log(result.message);
            } else {
                console.error(`Error setting temp for AHU ${ahuId}:`, result.error);
                // (Optional) หากล้มเหลว อาจจะเปลี่ยนค่ากลับเป็นค่าเดิม
                tempDisplay.textContent = currentTemp.toFixed(1) + '°C';
                alert(`Failed to set temperature: ${result.error}`);
            }

        } catch (error) {
            console.error('Network error while setting temperature:', error);
            tempDisplay.textContent = currentTemp.toFixed(1) + '°C';
            alert('An error occurred. Could not set temperature.');
        }
    }

    async function fetchAndUpdateAllStatuses() {
        try {
            const response = await fetch(API_STATUS_URL);
            if (!response.ok) {
                console.error('Failed to fetch status from server.');
                return;
            }
            const data = await response.json();
            
            if (data.error) {
                 console.error('API Error:', data.error);
                 return;
            }

            for (const key in data) {
                const ahuId = key.split('_')[1];
                const status = data[key];
                updateAHUCard(ahuId, status.is_on);
            }
        } catch (error) {
            console.error('Error polling for status:', error);
        }
    }

    // --- Function ใหม่สำหรับจัดการปุ่ม ON/OFF ---
    async function handleControlButtonClick(event) {
        const button = event.currentTarget;
        const ahuId = button.dataset.ahuId;
        const action = button.dataset.action; // 'on' or 'off'

        try {
            // เรียก API ใหม่ตาม action ที่กด
            const response = await fetch(`${API_CONTROL_URL}${ahuId}/${action}`, {
                method: 'POST',
            });
            const result = await response.json();

            if (result.success) {
                console.log(`Command '${action}' sent for AHU ${ahuId}`);
                // รอสักครู่แล้วดึงสถานะใหม่เพื่อให้ PLC มีเวลาทำงาน
                setTimeout(fetchAndUpdateAllStatuses, 500);
            } else {
                alert(`Error: ${result.error}`);
            }
        } catch (error) {
            console.error(`Error sending '${action}' command:`, error);
            alert('An error occurred. Could not send command.');
        }
    }

    // --- Time Display ---
    function updateTime() {
        const timeDisplay = document.getElementById('time-display');
        if (timeDisplay) {
            const now = new Date();
            const timeString = now.toLocaleTimeString('en-GB');
            timeDisplay.textContent = `Time ${timeString}`;
        }
    }

    // --- Setup ---
    // Attach event listeners to all power buttons
    document.querySelectorAll('.control-button').forEach(button => {
        button.addEventListener('click', handleControlButtonClick);
    });

    document.querySelectorAll('.temp-control-btn').forEach(button => {
        button.addEventListener('click', handleTempControlButtonClick);
    });

    fetchAndUpdateAllStatuses();
    setInterval(fetchAndUpdateAllStatuses, POLLING_RATE_MS);

    // Start time display
    updateTime();
    setInterval(updateTime, 1000);
});