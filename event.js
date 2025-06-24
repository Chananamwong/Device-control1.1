document.addEventListener('DOMContentLoaded', function() {
    const stagesContainer = document.getElementById('stages-container');
    const addStageBtn = document.getElementById('add-stage-btn');
    const saveScheduleBtn = document.getElementById('save-schedule-btn');
    const tabs = document.querySelectorAll('.tabs .tab-button');
    let activeScheduleType = 'soft_start'; // ค่าเริ่มต้นเมื่อเปิดหน้า

    // --- ฟังก์ชันสำหรับโหลดและแสดงผล Schedule จาก Server ---
    async function loadSchedules(scheduleType) {
        try {
            const response = await fetch(`/api/get_schedules/${scheduleType}`);
            const schedules = await response.json();
            
            stagesContainer.innerHTML = ''; // ล้าง Stage เก่าออกทั้งหมด

            if (schedules.length === 0) {
                stagesContainer.appendChild(createStageElement(null, 0));
            } else {
                schedules.forEach((stage, index) => {
                    const stageElement = createStageElement(stage, index);
                    stagesContainer.appendChild(stageElement);
                });
            }
            updateStageTitles();
        } catch (error) {
            console.error('Failed to load schedules:', error);
        }
    }

    // --- ฟังก์ชันสำหรับสร้าง HTML ของแต่ละ Stage ---
    function createStageElement(stageData, index) {
        const stageCard = document.createElement('div');
        stageCard.className = 'stage-card';
        stageCard.dataset.stageId = stageData ? stageData._id : `new-${Date.now()}`;
        
        const isEnabled = stageData ? stageData.is_enabled : true;
        const timeHour = stageData ? String(stageData.time_hour).padStart(2, '0') : '00';
        const timeMinute = stageData ? String(stageData.time_minute).padStart(2, '0') : '00';
        const devices = stageData ? stageData.devices : [];

        let deviceButtonsHTML = '';
        for (let i = 1; i <= 6; i++) {
            const isActive = devices.includes(i) ? 'active' : '';
            deviceButtonsHTML += `<button class="device-btn ${isActive}" data-ahu-id="${i}">AHU ${String(i).padStart(2, '0')}</button>`;
        }

        stageCard.innerHTML = `
            <div class="stage-header">
                <h3 class="stage-title">Stage 01</h3>
                <div class="stage-controls">
                    <button class="stage-btn stage-enable ${isEnabled ? 'active' : ''}">Enable</button>
                    <button class="stage-btn stage-disable ${!isEnabled ? 'active' : ''}">disable</button>
                    <button class="stage-btn stage-delete">Delete</button>
                </div>
            </div>
            <div class="stage-body">
                <div class="time-setter">
                    <label>Time</label>
                    <div class="time-inputs">
                        <input class="time-hour" type="number" value="${timeHour}" min="0" max="23">
                        <span>:</span>
                        <input class="time-minute" type="number" value="${timeMinute}" min="0" max="59">
                    </div>
                </div>
                <div class="device-setter">
                    <label>Device</label>
                    <div class="device-buttons">${deviceButtonsHTML}</div>
                </div>
            </div>`;
        return stageCard;
    }
    
    function updateStageTitles() {
        const allStages = stagesContainer.querySelectorAll('.stage-card');
        allStages.forEach((stage, index) => {
            const title = stage.querySelector('.stage-title');
            if (title) {
                title.textContent = `Stage ${String(index + 1).padStart(2, '0')}`;
            }
        });
    }

    // --- จัดการการคลิกแท็บ Soft Start / Soft Stop ---
    tabs.forEach(tab => {
        tab.addEventListener('click', function() {
            tabs.forEach(t => t.classList.remove('active'));
            this.classList.add('active');
            activeScheduleType = this.dataset.type;
            loadSchedules(activeScheduleType);
        });
    });

    // --- จัดการปุ่ม Save ---
    saveScheduleBtn.addEventListener('click', async function() {
        const allStages = stagesContainer.querySelectorAll('.stage-card');
        const stagesData = [];

        allStages.forEach((stage, index) => {
            const hour = parseInt(stage.querySelector('.time-hour').value, 10);
            const minute = parseInt(stage.querySelector('.time-minute').value, 10);
            const isEnabled = stage.querySelector('.stage-enable').classList.contains('active');
            
            const selectedDevices = [];
            stage.querySelectorAll('.device-btn.active').forEach(btn => {
                selectedDevices.push(parseInt(btn.dataset.ahuId, 10));
            });

            stagesData.push({
                stage_index: index + 1,
                is_enabled: isEnabled,
                time_hour: hour,
                time_minute: minute,
                devices: selectedDevices
            });
        });
        
        // *** แก้ไข Bug จุดที่ 2 ***
        // เปลี่ยนจาก 'soft_start' มาใช้ตัวแปร `activeScheduleType` ที่เปลี่ยนตามแท็บ
        const payload = {
            type: activeScheduleType,
            stages: stagesData
        };

        try {
            const response = await fetch('/api/save_schedule', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const result = await response.json();
            if (result.success) {
                alert('Schedule saved!');
                // ไม่ต้อง reload แต่ให้โหลดข้อมูลใหม่ตามแท็บปัจจุบันแทน
                loadSchedules(activeScheduleType);
            } else {
                alert('Error saving schedule: ' + result.error);
            }
        } catch (error) {
            console.error('Failed to save schedule:', error);
            alert('Failed to save schedule.');
        }
    });
    
    // *** เพิ่มโค้ดที่ขาดหายไปสำหรับปุ่ม Add (Bug จุดที่ 1) ***
    addStageBtn.addEventListener('click', function() {
        const newIndex = stagesContainer.querySelectorAll('.stage-card').length;
        stagesContainer.appendChild(createStageElement(null, newIndex));
        updateStageTitles();
    });

    // --- เติมโค้ดส่วนที่ขาดหายไป ---
    stagesContainer.addEventListener('click', function(event) {
        const target = event.target;

       // จัดการปุ่ม Delete (ฉบับแก้ไข)
        if (target.classList.contains('stage-delete')) {
            const stageCard = target.closest('.stage-card');
            const stageId = stageCard.dataset.stageId;

            // ถามเพื่อยืนยันการลบ
            if (confirm('Are you sure you want to delete this stage?')) {
                
                // กรณีเป็น Stage ที่เพิ่งกด Add และยังไม่เคย Save (ไม่มี ID ใน DB)
                // ให้ลบออกจากหน้าเว็บได้เลยโดยไม่ต้องเรียก API
                if (stageId.startsWith('new-')) {
                    stageCard.remove();
                    updateStageTitles();
                    return; // จบการทำงานในส่วนนี้
                }

                // กรณีเป็น Stage ที่มีข้อมูลใน DB แล้ว ให้เรียก API เพื่อลบ
                fetch(`/api/delete_schedule/${stageId}`, {
                    method: 'POST',
                })
                .then(response => response.json())
                .then(result => {
                    if (result.success) {
                        // เมื่อลบใน DB สำเร็จแล้ว ค่อยลบออกจากหน้าเว็บ
                        stageCard.remove();
                        updateStageTitles();
                        console.log(result.message);
                    } else {
                        alert('Error deleting stage: ' + result.error);
                    }
                })
                .catch(error => {
                    console.error('Failed to delete stage:', error);
                    alert('An error occurred while deleting the stage.');
                });
            }
        }

        // จัดการปุ่ม Enable/Disable
        if (target.classList.contains('stage-enable') || target.classList.contains('stage-disable')) {
            const controls = target.parentElement;
            controls.querySelector('.stage-enable').classList.remove('active');
            controls.querySelector('.stage-disable').classList.remove('active');
            target.classList.add('active');
        }

        // จัดการปุ่มเลือก Device (AHU)
        if (target.classList.contains('device-btn')) {
            // .toggle จะสลับการมี/ไม่มี class 'active' ให้อัตโนมัติ
            target.classList.toggle('active');
        }
    });

     function updateTime() {
        const timeDisplay = document.getElementById('time-display');
        if (timeDisplay) {
            const now = new Date();
            const timeString = now.toLocaleTimeString('en-GB');
            timeDisplay.textContent = `Time ${timeString}`;
        }
    }
    updateTime();
    setInterval(updateTime, 1000);
});