from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import threading
import time
import sys
import os
import cv2
import numpy as np
import random

# Add the directory containing your main.py to Python path
sys.path.append('/home/Isha/ISHA/Code')

app = Flask(__name__)
CORS(app)

# Global reference to your fire detection system
fire_system = None
# Track last manual command time
last_manual_command_time = None
manual_timeout = 60  # 1 minute in seconds

def initialize_fire_system():
    """Initialize the FireDetectionSystem in a separate thread"""
    global fire_system
    try:
        # Import and create your fire detection system
        from main import FireDetectionSystem
        fire_system = FireDetectionSystem()
        print("FireDetectionSystem initialized successfully")
        
        # Start the system in a separate thread
        system_thread = threading.Thread(target=fire_system.run)
        system_thread.daemon = True
        system_thread.start()
        print("FireDetectionSystem thread started")
        
    except Exception as e:
        print(f"Error initializing FireDetectionSystem: {e}")
        print("Using mock system for testing")
        fire_system = MockFireSystem()

def check_manual_timeout():
    """Background thread to check for manual mode timeout"""
    while True:
        time.sleep(10)  # Check every 10 seconds
        try:
            global last_manual_command_time, fire_system
            if (fire_system and 
                fire_system.manual_mode and 
                last_manual_command_time and 
                (time.time() - last_manual_command_time) > manual_timeout):
                
                # Switch back to auto mode
                fire_system.manual_mode = False
                last_manual_command_time = None
                print("Switched to auto mode due to inactivity")
        except Exception as e:
            print(f"Error in manual timeout check: {e}")

class MockFireSystem:
    """Mock system for testing when real system fails"""
    def __init__(self):
        self.temperature = 25.0
        self.humidity = 50.0
        self.fire_detected = False
        self.gas_detected = False
        self.vibration_count = 0
        self.pump_active = False
        self.manual_mode = False
        self.pan_angle = 90
        self.tilt_angle = 90
        self.picam2 = None
    
    def read_dht22(self):
        # Simulate realistic sensor readings with some variation
        self.temperature = 20 + random.uniform(0, 15)
        self.humidity = 40 + random.uniform(0, 30)
        
        # Occasionally simulate fire detection
        if random.random() > 0.95:  # 5% chance
            self.fire_detected = True
            self.temperature = 80 + random.uniform(0, 20)  # High temp during fire
        else:
            self.fire_detected = False
            
        # Occasionally simulate gas detection
        self.gas_detected = random.random() > 0.98  # 2% chance
        
        # Simulate vibration
        self.vibration_count = random.randint(0, 2)
        
        return self.temperature, self.humidity
    
    def manual_servo_control(self, key):
        """Mock servo control"""
        if key == ord('w'):
            self.tilt_angle = min(180, self.tilt_angle + 5)
        elif key == ord('s'):
            self.tilt_angle = max(0, self.tilt_angle - 5)
        elif key == ord('a'):
            self.pan_angle = max(0, self.pan_angle - 5)
        elif key == ord('d'):
            self.pan_angle = min(180, self.pan_angle + 5)
        elif key == ord('c'):
            self.pan_angle = 90
            self.tilt_angle = 90
        print(f"Mock servo control - Pan: {self.pan_angle}, Tilt: {self.tilt_angle}")
    
    def set_pump_state(self, state):
        """Control the water pump"""
        self.pump_active = state
        print(f"Pump state set to: {'ON' if state else 'OFF'}")
        return True

# Initialize the system
print("Initializing Fire Detection System...")
initialize_fire_system()

# Start the manual timeout checker
timeout_thread = threading.Thread(target=check_manual_timeout)
timeout_thread.daemon = True
timeout_thread.start()
print("Manual timeout checker started")

@app.route('/sensors', methods=['GET'])
def get_sensors():
    """Get current sensor data"""
    try:
        if fire_system:
            # Always read fresh sensor data
            temp, humidity = fire_system.read_dht22()
            
            # If DHT22 returns None, use mock data
            if temp is None or humidity is None:
                print("DHT22 returned None, using mock data")
                if hasattr(fire_system, 'temperature') and hasattr(fire_system, 'humidity'):
                    temp = fire_system.temperature
                    humidity = fire_system.humidity
                else:
                    temp = 25.0
                    humidity = 50.0
            
            print(f"Sensor data - Temp: {temp}, Humidity: {humidity}")
            
            return jsonify({
                'temperature': float(temp),
                'humidity': float(humidity),
                'fireDetected': getattr(fire_system, 'fire_detected', False),
                'gasDetected': getattr(fire_system, 'gas_detected', False),
                'vibrationCount': getattr(fire_system, 'vibration_count', 0),
                'pumpActive': getattr(fire_system, 'pump_active', False)
            })
        else:
            print("Fire system not initialized, returning mock data")
            return jsonify({
                'temperature': 25.0,
                'humidity': 50.0,
                'fireDetected': False,
                'gasDetected': False,
                'vibrationCount': 0,
                'pumpActive': False
            })
    except Exception as e:
        print(f"Error reading sensors: {e}")
        # Return default values on error
        return jsonify({
            'temperature': 25.0,
            'humidity': 50.0,
            'fireDetected': False,
            'gasDetected': False,
            'vibrationCount': 0,
            'pumpActive': False
        })

@app.route('/camera/mode', methods=['POST'])
def set_camera_mode():
    """Set camera to manual or auto mode"""
    try:
        global last_manual_command_time
        manual_mode = request.args.get('manual', 'false').lower() == 'true'
        if fire_system:
            fire_system.manual_mode = manual_mode
            if manual_mode:
                last_manual_command_time = time.time()  # Reset timer when switching to manual
            else:
                last_manual_command_time = None
            mode = "MANUAL" if manual_mode else "AUTO"
            print(f"Camera mode set to: {mode}")
            return jsonify({'status': 'success', 'mode': mode})
        else:
            return jsonify({'error': 'System not initialized'}), 500
    except Exception as e:
        print(f"Error setting camera mode: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/camera/control', methods=['POST'])
def control_camera():
    """Control camera movement"""
    try:
        global last_manual_command_time
        command = request.args.get('command', '').lower()
        if fire_system and fire_system.manual_mode:
            # Update last command time
            last_manual_command_time = time.time()
            
            key_map = {
                'up': ord('w'),
                'down': ord('s'), 
                'left': ord('a'),
                'right': ord('d'),
                'center': ord('c')
            }
            
            if command in key_map:
                fire_system.manual_servo_control(key_map[command])
                
                print(f"Camera moved: {command} -> Pan: {fire_system.pan_angle}, Tilt: {fire_system.tilt_angle}")
                return jsonify({
                    'status': 'success', 
                    'command': command,
                    'pan_angle': fire_system.pan_angle,
                    'tilt_angle': fire_system.tilt_angle
                })
            else:
                return jsonify({'error': f'Invalid command: {command}'}), 400
        else:
            return jsonify({'error': 'System not in manual mode or not initialized'}), 400
    except Exception as e:
        print(f"Error controlling camera: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/pump/control', methods=['POST'])
def control_pump():
    """Control the water pump"""
    try:
        state = request.args.get('state', '').lower()
        if state not in ['on', 'off']:
            return jsonify({'error': 'Invalid state. Use "on" or "off"'}), 400

        if fire_system:
            # Use the actual pump control method if available, otherwise use mock
            if hasattr(fire_system, 'set_pump_state'):
                success = fire_system.set_pump_state(state == 'on')
            else:
                # Fallback to direct attribute setting
                fire_system.pump_active = (state == 'on')
                success = True
                
            if success:
                return jsonify({
                    'status': 'success', 
                    'pump_active': fire_system.pump_active
                })
            else:
                return jsonify({'error': 'Failed to control pump'}), 500
        else:
            return jsonify({'error': 'System not initialized'}), 500
    except Exception as e:
        print(f"Error controlling pump: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/system/status', methods=['GET'])
def get_system_status():
    """Get overall system status"""
    try:
        if fire_system:
            return jsonify({
                'initialized': True,
                'manual_mode': fire_system.manual_mode,
                'pan_angle': getattr(fire_system, 'pan_angle', 90),
                'tilt_angle': getattr(fire_system, 'tilt_angle', 90),
                'fire_detected': getattr(fire_system, 'fire_detected', False),
                'pump_active': getattr(fire_system, 'pump_active', False)
            })
        else:
            return jsonify({'initialized': False})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def generate_frames():
    """Generate frames from the camera for streaming"""
    while True:
        try:
            if fire_system and hasattr(fire_system, 'picam2') and fire_system.picam2:
                frame = fire_system.picam2.capture_array()
                frame = cv2.flip(frame, -1)
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                frame = buffer.tobytes()
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                # Create a test pattern with sensor info
                black_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                
                # Add text with sensor status
                if fire_system:
                    temp = getattr(fire_system, 'temperature', 0)
                    humidity = getattr(fire_system, 'humidity', 0)
                    pump_status = "ON" if getattr(fire_system, 'pump_active', False) else "OFF"
                    status_text = f"Temp: {temp:.1f}C, Humidity: {humidity:.1f}%"
                    pump_text = f"Pump: {pump_status}"
                else:
                    status_text = "System not initialized"
                    pump_text = "Pump: OFF"
                
                cv2.putText(black_frame, status_text, (50, 220), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                cv2.putText(black_frame, pump_text, (50, 250), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                cv2.putText(black_frame, "Camera Feed Placeholder", (50, 280), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                ret, buffer = cv2.imencode('.jpg', black_frame)
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                time.sleep(0.1)
                
        except Exception as e:
            print(f"Error generating frame: {e}")
            time.sleep(0.1)

@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    return Response(generate_frames(), 
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/test')
def test():
    """Test endpoint"""
    return jsonify({
        'status': 'Server is running',
        'fire_system_initialized': fire_system is not None,
        'timestamp': time.time()
    })

if __name__ == '__main__':
    print("Starting Fire Detection Server on http://0.0.0.0:5000")
    print("Endpoints:")
    print("  GET  /sensors - Get sensor data")
    print("  POST /camera/mode?manual=true|false - Set camera mode")
    print("  POST /camera/control?command=up|down|left|right|center - Control camera")
    print("  POST /pump/control?state=on|off - Control water pump")
    print("  GET  /system/status - Get system status")
    print("  GET  /video_feed - Video stream")
    print("  GET  /test - Test endpoint")
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)