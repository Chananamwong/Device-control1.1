import time
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify, request, redirect, url_for
from flask_pymongo import PyMongo
from pymodbus.client import ModbusTcpClient
from bson.objectid import ObjectId

# --- Configuration ---
PLC_IP_ADDRESS = '192.168.0.2'
PLC_PORT = 502

app = Flask(__name__)
app.config["MONGO_URI"] = "mongodb://localhost:27017/ahu_database"
mongo = PyMongo(app)

# --- Modbus Functions ---
def write_ahu_command(client, address):
    if address == 0: return False
    try:
        client.write_coil(address - 1, True)
        time.sleep(0.2)
        client.write_coil(address - 1, False)
        print(f"Successfully sent command to address {address}")
        return True
    except Exception as e:
        print(f"Error writing command to address {address}: {e}")
        return False

def write_ahu_temperature(client, address, temperature):
    """
    เขียนค่าอุณหภูมิ (integer) ไปยัง Holding Register ของ Modbus
    """
    if address == 0: return False
    try:
        # LOGO! อาจจะต้องรับค่าเป็น Integer เราจึงต้องแปลงค่าก่อน
        # address - 1 เพราะ pymodbus เริ่มนับที่ 0 แต่ LOGO! อาจแสดงผลเริ่มที่ 1
        # VW100 ใน LOGO! คือ address 99 ใน pymodbus
        register_address = address - 1
        client.write_register(register_address, int(temperature))
        print(f"Successfully sent temperature {temperature} to register address {register_address}")
        return True
    except Exception as e:
        print(f"Error writing temperature to address {address}: {e}")
        return False
    
def read_ahu_status(client, address):
    # ... (ฟังก์ชันนี้เหมือนเดิม) ...
    if address == 0: return False
    try:
        rr = client.read_coils(address - 1, count=1)
        if not rr.isError():
            return rr.bits[0]
        print(f"Modbus read COIL error for address {address}: {rr}")
        return False
    except Exception as e:
        print(f"Exception while reading status at address {address}: {e}")
        return False

def read_ahu_temperature(client, address):
    """
    อ่านค่าอุณหภูมิ (integer) จาก Holding Register ของ Modbus
    """
    if address == 0: return None # คืนค่า None หากไม่มีการตั้งค่า Address
    try:
        register_address = address - 1
        rr = client.read_holding_registers(register_address, count=1)
        if not rr.isError():
            # ค่าที่ได้อาจจะเป็นค่าที่คูณ 10 ไว้ เราจึงต้องหาร 10.0 เพื่อให้ได้ทศนิยม
            temperature = rr.registers[0] / 10.0
            return temperature
        print(f"Modbus read REGISTER error for address {address}: {rr}")
        return None
    except Exception as e:
        print(f"Exception while reading temperature at address {address}: {e}")
        return None
    
# --- Backend Scheduler Logic (ส่วนที่เพิ่มใหม่ทั้งหมด) ---
def scheduler_service():
    """
    ฟังก์ชันนี้จะทำงานใน background thread เพื่อคอยตรวจสอบตารางเวลา
    และส่งคำสั่ง Modbus เมื่อถึงเวลาที่กำหนด (อัปเดตให้รองรับ Soft Stop)
    """
    print("Scheduler service started.")
    while True:
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute

        with app.app_context():
            active_schedules = mongo.db.schedules.find({
                "is_enabled": True,
                "time_hour": current_hour,
                "time_minute": current_minute
            })

            for schedule in active_schedules:
                print(f"--- Triggering Schedule: {schedule['stage_type']} - Stage {schedule['stage_index']} ---")
                
                address_key = ''
                # --- เพิ่มเงื่อนไขสำหรับ Soft Stop ---
                if schedule['stage_type'] == 'soft_start':
                    address_key = 'scheduled_on_m'
                elif schedule['stage_type'] == 'soft_stop':
                    address_key = 'scheduled_off_m' # ใช้ Address สำหรับตั้งเวลาปิด
                
                if not address_key:
                    continue

                client = ModbusTcpClient(PLC_IP_ADDRESS, port=PLC_PORT)
                if client.connect():
                    for ahu_id in schedule['devices']:
                        settings = mongo.db.settings.find_one({'_id': ahu_id})
                        if settings:
                            address_to_write = settings.get(address_key, 0)
                            print(f"  > Firing command for AHU {ahu_id} at address {address_to_write} for {schedule['stage_type']}")
                            write_ahu_command(client, address_to_write)
                    client.close()
                else:
                    print(f"  > Could not connect to PLC to trigger schedule.")

        time.sleep(60)

# --- Web Routes ---
@app.route('/')
def index():
    return render_template('Device control.html')

@app.route('/schedule')
def schedule():
    schedules_cursor = mongo.db.schedules.find({'stage_type': 'soft_start'}).sort('stage_index')
    schedules_list = list(schedules_cursor)
    return render_template('Event_start.html', schedules=schedules_list)

# API ใหม่สำหรับโหลดข้อมูลตามประเภท (Soft Start/Soft Stop)
@app.route('/api/get_schedules/<schedule_type>')
def api_get_schedules(schedule_type):
    schedules_cursor = mongo.db.schedules.find({'stage_type': schedule_type}).sort('stage_index')
    schedules_list = []
    for doc in schedules_cursor:
        doc['_id'] = str(doc['_id']) # แปลง ObjectId เป็น string เพื่อให้ JSON ทำงานได้
        schedules_list.append(doc)
    return jsonify(schedules_list)

@app.route('/api/save_schedule', methods=['POST'])
def api_save_schedule():
    """ (ฉบับแก้ไข) ฟังก์ชันบันทึกข้อมูล """
    data = request.get_json()
    schedule_type = data.get('type')
    stages = data.get('stages')

    if not schedule_type or stages is None:
        return jsonify({'success': False, 'error': 'Missing data'}), 400

    # เพิ่ม 'stage_type' เข้าไปในทุกๆ document ของ stage
    for stage in stages:
        stage['stage_type'] = schedule_type

    mongo.db.schedules.delete_many({'stage_type': schedule_type})
    if stages:
        mongo.db.schedules.insert_many(stages)

    return jsonify({'success': True, 'message': 'Schedule saved successfully!'})

@app.route('/api/delete_schedule/<stage_id>', methods=['POST'])
def api_delete_schedule(stage_id):
    """
    API สำหรับลบ Stage ทีละรายการออกจากฐานข้อมูล
    """
    try:
        # แปลง stage_id ที่รับมา (ซึ่งเป็น string) ให้เป็น ObjectId
        # แล้วสั่งลบ document ที่มี _id ตรงกัน
        result = mongo.db.schedules.delete_one({'_id': ObjectId(stage_id)})

        if result.deleted_count > 0:
            print(f"Successfully deleted stage with ID: {stage_id}")
            return jsonify({'success': True, 'message': 'Stage deleted.'})
        else:
            return jsonify({'success': False, 'error': 'Stage not found.'}), 404

    except Exception as e:
        print(f"Error deleting stage {stage_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/settings', methods=['POST', 'GET'])
def settings():
    if request.method == 'POST':
        for i in range(1, 7):
            setting_data = {
                '_id': i,
                'on_address_m': int(request.form.get(f'on_address_m_{i}', 0)),
                'off_address_m': int(request.form.get(f'off_address_m_{i}', 0)),
                'output_address_q': int(request.form.get(f'output_address_q_{i}', 0)),
                'scheduled_on_m': int(request.form.get(f'scheduled_on_m_{i}', 0)),
                'scheduled_off_m': int(request.form.get(f'scheduled_off_m_{i}', 0)),
                'temp_address_vw': int(request.form.get(f'temp_address_vw_{i}', 0)),
            }
            mongo.db.settings.update_one({'_id': i}, {'$set': setting_data}, upsert=True)
        return redirect(url_for('settings'))
    
    # --- ส่วนของ GET request ที่แก้ไขแล้ว ---
    all_settings_cursor = mongo.db.settings.find().sort('_id')
    settings_list = list(all_settings_cursor)
    
    # ถ้าข้อมูลยังไม่ครบ 6 ให้สร้างข้อมูลเริ่มต้นให้ครบ
    if len(settings_list) < 6:
        existing_ids = {s['_id'] for s in settings_list}
        for i in range(1, 7):
            if i not in existing_ids:
                # สร้าง document เริ่มต้นให้ครบทุก field
                mongo.db.settings.insert_one({
                    '_id': i, 
                    'on_address_m': 0, 
                    'off_address_m': 0, 
                    'output_address_q': 0,
                    'scheduled_on_m': 0, 
                    'scheduled_off_m': 0,
                    'temp_address_vw': 0
                })
        # หลังจากสร้างแล้ว ให้ดึงข้อมูลทั้งหมดอีกครั้ง
        settings_list = list(mongo.db.settings.find().sort('_id'))

    # ย้าย return มาไว้ข้างนอกเพื่อให้ทำงานทุกครั้ง
    return render_template('settings.html', settings=settings_list)

# --- API Endpoints ---
@app.route('/api/ahu_status')
def api_get_ahu_status():
    client = ModbusTcpClient(PLC_IP_ADDRESS, port=PLC_PORT)
    if not client.connect():
        return jsonify({"error": "Cannot connect to PLC"}), 500
    
    all_settings = list(mongo.db.settings.find().sort('_id'))
    status_data = {}

    for setting in all_settings:
        ahu_id = setting['_id']
        
        # อ่านสถานะ ON/OFF (เหมือนเดิม)
        q_address = setting.get('output_address_q', 0)
        is_on_status = read_ahu_status(client, q_address)
        
        # --- ส่วนที่เพิ่มเข้ามา: อ่านค่าอุณหภูมิ ---
        vw_address = setting.get('temp_address_vw', 0)
        temperature_value = read_ahu_temperature(client, vw_address)
        
        # รวมข้อมูลทั้งสองอย่างส่งกลับไป
        status_data[f"ahu_{ahu_id}"] = {
            'is_on': is_on_status,
            'temperature': temperature_value
        }
        
    client.close()
    return jsonify(status_data)

@app.route('/api/control_ahu/<int:ahu_id>/<string:action>', methods=['POST'])
def api_control_ahu(ahu_id, action):
    # ... (ฟังก์ชันนี้เหมือนเดิม) ...
    if action not in ['on', 'off']:
        return jsonify({"success": False, "error": "Invalid action"}), 400
    setting = mongo.db.settings.find_one({'_id': ahu_id})
    if not setting:
        return jsonify({"success": False, "error": "Setting not found"}), 404
    address_to_write = 0
    if action == 'on':
        address_to_write = setting.get('on_address_m', 0)
    else: # action == 'off'
        address_to_write = setting.get('off_address_m', 0)
    if address_to_write == 0:
        return jsonify({"success": False, "error": f"{action.capitalize()} address not configured"}), 400
    client = ModbusTcpClient(PLC_IP_ADDRESS, port=PLC_PORT)
    if not client.connect():
        return jsonify({"success": False, "error": "Cannot connect to PLC"}), 500
    success = write_ahu_command(client, address_to_write)
    client.close()
    if success:
        return jsonify({"success": True, "message": f"Sent {action} command to AHU {ahu_id}"})
    else:
        return jsonify({"success": False, "error": "Failed to send command"}), 500

@app.route('/api/set_temperature/<int:ahu_id>', methods=['POST'])
def api_set_temperature(ahu_id):
    """
    API สำหรับตั้งค่าอุณหภูมิของ AHU
    """
    data = request.get_json()
    temperature = data.get('temperature')

    if temperature is None:
        return jsonify({"success": False, "error": "Missing temperature value"}), 400

    setting = mongo.db.settings.find_one({'_id': ahu_id})
    if not setting:
        return jsonify({"success": False, "error": "Setting not found"}), 404

    address_to_write = setting.get('temp_address_vw', 0)
    if address_to_write == 0:
        return jsonify({"success": False, "error": "Temperature address not configured"}), 400

    client = ModbusTcpClient(PLC_IP_ADDRESS, port=PLC_PORT)
    if not client.connect():
        return jsonify({"success": False, "error": "Cannot connect to PLC"}), 500

    # สมมติว่าเราส่งค่าอุณหภูมิ x 10 เพื่อให้เป็นจำนวนเต็ม (เช่น 25.5°C -> 255)
    # หาก PLC ของคุณจัดการทศนิยมได้ ก็ไม่ต้องคูณ
    value_to_send = int(float(temperature) * 10)

    success = write_ahu_temperature(client, address_to_write, value_to_send)
    client.close()

    if success:
        return jsonify({"success": True, "message": f"Sent temperature {temperature}°C to AHU {ahu_id}"})
    else:
        return jsonify({"success": False, "error": "Failed to send temperature command"}), 500
    
if __name__ == '__main__':
    # --- Start the scheduler service in a separate thread ---
    scheduler_thread = threading.Thread(target=scheduler_service, daemon=True)
    scheduler_thread.start()
    
    # --- Run the Flask web server ---
    app.run(debug=True, host='0.0.0.0', port=5000)