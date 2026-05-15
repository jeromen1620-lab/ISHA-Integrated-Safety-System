import time
import threading
from gpiozero import DigitalInputDevice, DigitalOutputDevice, Buzzer
import adafruit_dht
import board
import busio
from adafruit_pca9685 import PCA9685
from adafruit_motor import servo
import cv2
import numpy as np
from picamera2 import Picamera2
from ultralytics import YOLO
import torch

# GPIO Pin Definitions
DHT_PIN = board.D4  # GPIO 4, Physical Pin 7
GAS_SENSOR_PIN = 7  # GPIO 7, Physical Pin 26
VIBRATION_PIN = 17  # GPIO 17, Physical Pin 11
BUZZER_PIN = 27     # GPIO 27, Physical Pin 13
PUMP_RELAY_PIN = 22 # GPIO 22, Physical Pin 15

class FireDetectionSystem:
    def __init__(self):
        # Initialize state variables FIRST
        self.vibration_count = 0
        self.last_vibration_time = 0
        self.vibration_lock = threading.Lock()
        
        self.fire_detected = False
        self.fire_detection_time = 0
        self.pump_on_time = 0
        self.pump_active = False
        
        # Manual control
        self.manual_mode = False
        self.servo_step = 5  # Degrees to move per key press
        
        # Camera settings - DEFINED BEFORE setup_camera()
        self.frame_width = 640
        self.frame_height = 480
        
        # YOLO settings
        self.yolo_input_size = 640
        self.confidence_threshold = 0.5
        self.iou_threshold = 0.45
        
        # YOLO detection
        self.last_detection_time = 0
        self.detection_interval = 0.5  # Run detection every 0.5 seconds
        
        # Servo direction alignment - BOTH INVERTED FOR UPSIDE-DOWN CAMERA
        self.invert_pan = True   # Invert left/right
        self.invert_tilt = True  # Invert up/down
        
        # Now initialize components
        self.setup_gpio()
        self.setup_camera()
        self.setup_servos()
        self.setup_yolov8()
        
    def setup_gpio(self):
        """Initialize all GPIO components using gpiozero"""
        print("Setting up GPIO components...")
        
        # DHT-22 (uses adafruit_dht library directly)
        self.dht_sensor = adafruit_dht.DHT22(DHT_PIN)
        
        # MO-2 Gas Sensor - Digital Output
        self.gas_sensor = DigitalInputDevice(GAS_SENSOR_PIN)
        self.gas_sensor.when_activated = self.gas_detected
        self.gas_sensor.when_deactivated = self.gas_cleared
        
        # SW-420 Vibration Sensor
        self.vibration_sensor = DigitalInputDevice(VIBRATION_PIN)
        self.vibration_sensor.when_activated = self.vibration_detected
        
        # Active Buzzer
        self.buzzer = Buzzer(BUZZER_PIN)
        
        # Relay Module - Pump (Normally Closed circuit)
        # active_high=False means LOW turns relay ON, HIGH turns relay OFF
        self.pump_relay = DigitalOutputDevice(PUMP_RELAY_PIN, active_high=False, initial_value=False)
        
        print("GPIO setup complete")
        
    def setup_camera(self):
        """Initialize camera with 640x480 resolution"""
        print("Setting up camera...")
        self.picam2 = Picamera2()
        
        # Create configuration with 640x480
        config = self.picam2.create_preview_configuration(
            main={"size": (self.frame_width, self.frame_height)}
        )
        self.picam2.configure(config)
        self.picam2.start()
        time.sleep(2)  # Allow camera to initialize
        print(f"Camera setup complete - Resolution: {self.frame_width}x{self.frame_height}")
        
    def setup_servos(self):
        """Initialize PCA9685 and servos"""
        print("Setting up servos...")
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.pca = PCA9685(i2c)
            self.pca.frequency = 50
            
            # Servo parameters for M6996R
            self.servo_pan = servo.Servo(self.pca.channels[0], min_pulse=500, max_pulse=2500)
            self.servo_tilt = servo.Servo(self.pca.channels[1], min_pulse=500, max_pulse=2500)
            
            # Center servos
            self.pan_angle = 90
            self.tilt_angle = 90
            self.servo_pan.angle = self.pan_angle
            self.servo_tilt.angle = self.tilt_angle
            print("Servos setup complete")
            
        except Exception as e:
            print(f"Servo setup error: {e}")
            self.pca = None
            
    def setup_yolov8(self):
        """Load YOLOv8 model for fire detection"""
        try:
            # Load YOLOv8n model
            self.model = YOLO('yolov8n.pt')
            
            # Get class names
            self.class_names = self.model.names
            print("YOLOv8 model loaded successfully")
            print(f"Available classes: {self.class_names}")
            
            # Check if we have fire-related classes
            self.fire_class_ids = []
            for idx, name in self.class_names.items():
                if 'fire' in name.lower() or 'smoke' in name.lower() or 'flame' in name.lower():
                    self.fire_class_ids.append(idx)
                    print(f"Fire-related class found: {name} (ID: {idx})")
            
            # If no fire classes found, we'll assume class 0 is fire (for custom models)
            if not self.fire_class_ids:
                print("No fire-related classes found. Assuming class 0 for fire detection.")
                self.fire_class_ids = [0]
                
        except Exception as e:
            print(f"Error loading YOLOv8 model: {e}")
            print("Please make sure 'ultralytics' is installed: pip install ultralytics")
            self.model = None
            
    def gas_detected(self):
        """Handle gas detection"""
        print("Gas detected!")
        
    def gas_cleared(self):
        """Handle gas clearance"""
        print("Gas level normal")
        
    def vibration_detected(self):
        """Handle vibration detection with earthquake logic"""
        current_time = time.time()
        
        with self.vibration_lock:
            # Reset count if more than 10 seconds since last vibration
            if current_time - self.last_vibration_time > 10:
                self.vibration_count = 0
                
            self.vibration_count += 1
            self.last_vibration_time = current_time
            
            print(f"Vibration detected! Count: {self.vibration_count}/5")
            
            # Trigger earthquake alarm after 5 vibrations
            if self.vibration_count >= 5:
                print("EARTHQUAKE DETECTED! Triggering alarm!")
                self.trigger_earthquake_alarm()
                self.vibration_count = 0  # Reset after alarm
                
    def trigger_earthquake_alarm(self):
        """Activate buzzer for earthquake warning"""
        def alarm_sequence():
            for _ in range(10):  # Beep 10 times
                self.buzzer.on()
                time.sleep(0.5)
                self.buzzer.off()
                time.sleep(0.5)
                
        # Run alarm in separate thread to not block main program
        alarm_thread = threading.Thread(target=alarm_sequence)
        alarm_thread.daemon = True
        alarm_thread.start()
        
    def read_dht22(self):
        """Read temperature and humidity from DHT-22"""
        try:
            temperature = self.dht_sensor.temperature
            humidity = self.dht_sensor.humidity
            if temperature is not None and humidity is not None:
                return temperature, humidity
        except RuntimeError as e:
            print(f"DHT22 read error: {e}")
        except Exception as e:
            print(f"DHT22 unexpected error: {e}")
        return None, None
        
    def preprocess_image_for_yolo(self, image):
        """Preprocess image for YOLOv8 model with proper input shape (1, 3, 640, 640)"""
        # Resize image to YOLO input size (640x640)
        resized = cv2.resize(image, (self.yolo_input_size, self.yolo_input_size))
        
        # Convert BGR to RGB
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        
        # Normalize pixel values to [0, 1]
        normalized = rgb.astype(np.float32) / 255.0
        
        # Convert to tensor and add batch dimension (BCHW format)
        tensor = torch.from_numpy(normalized).permute(2, 0, 1).unsqueeze(0)
        
        return tensor, resized.shape[:2]
        
    def detect_fire_yolov8(self, image):
        """Run fire detection using YOLOv8 model with proper input/output shapes"""
        if self.model is None:
            return False, 0, 0, 0, []
            
        try:
            # Preprocess image for YOLO
            input_tensor, yolo_shape = self.preprocess_image_for_yolo(image)
            
            # Run YOLOv8 inference
            with torch.no_grad():
                results = self.model(input_tensor)
            
            # Process results
            fire_detected = False
            max_confidence = 0
            fire_x, fire_y = 0, 0
            fire_bbox = []
            all_detections = []
            
            # YOLOv8 returns a list of Results objects
            for result in results:
                if result.boxes is not None and len(result.boxes) > 0:
                    boxes = result.boxes.cpu().numpy()
                    
                    for i, box in enumerate(boxes.xyxy):
                        x1, y1, x2, y2 = box
                        confidence = boxes.conf[i]
                        class_id = int(boxes.cls[i])
                        
                        # Store all detections for drawing
                        all_detections.append({
                            'bbox': [x1, y1, x2, y2],
                            'confidence': confidence,
                            'class_id': class_id,
                            'class_name': self.class_names[class_id]
                        })
                        
                        # Check if this is a fire detection
                        if class_id in self.fire_class_ids and confidence > self.confidence_threshold:
                            if confidence > max_confidence:
                                max_confidence = confidence
                                fire_detected = True
                                # Calculate center of bounding box
                                fire_x = (x1 + x2) / 2
                                fire_y = (y1 + y2) / 2
                                fire_bbox = [x1, y1, x2, y2]
            
            return fire_detected, fire_x, fire_y, max_confidence, all_detections
                        
        except Exception as e:
            print(f"YOLOv8 detection error: {e}")
            
        return False, 0, 0, 0, []
        
    def aim_servos_at_fire(self, fire_x, fire_y, yolo_width=640, yolo_height=640):
        """Aim servos at detected fire location with proper camera alignment"""
        if self.pca is None or self.manual_mode:
            return self.pan_angle, self.tilt_angle
            
        # Convert YOLO coordinates (640x640) to original image coordinates (640x480)
        scale_x = self.frame_width / yolo_width
        scale_y = self.frame_height / yolo_height
        
        orig_x = fire_x * scale_x
        orig_y = fire_y * scale_y
        
        # Convert coordinates to servo angles
        # Pan: 0-180 degrees, left to right
        target_pan = (orig_x / self.frame_width) * 180
        
        # Tilt: 0-180 degrees, but inverted to match camera view
        # Since camera is upside down, we need to invert both directions
        target_tilt = (orig_y / self.frame_height) * 180
        
        # Apply inversion for upside-down camera
        # Invert both pan and tilt for 180-degree rotated camera
        if self.invert_pan:
            target_pan = 180 - target_pan
        if self.invert_tilt:
            target_tilt = 180 - target_tilt
        
        # Constrain angles to safe limits
        target_pan = max(0, min(180, target_pan))
        target_tilt = max(0, min(180, target_tilt))
        
        # Smooth movement (adjust increment for speed)
        pan_increment = 3
        tilt_increment = 3
        
        # Move pan servo gradually
        if abs(target_pan - self.pan_angle) > 2:
            if target_pan > self.pan_angle:
                self.pan_angle = min(self.pan_angle + pan_increment, target_pan)
            else:
                self.pan_angle = max(self.pan_angle - pan_increment, target_pan)
            self.servo_pan.angle = self.pan_angle
            
        # Move tilt servo gradually
        if abs(target_tilt - self.tilt_angle) > 2:
            if target_tilt > self.tilt_angle:
                self.tilt_angle = min(self.tilt_angle + tilt_increment, target_tilt)
            else:
                self.tilt_angle = max(self.tilt_angle - tilt_increment, target_tilt)
            self.servo_tilt.angle = self.tilt_angle
            
        return self.pan_angle, self.tilt_angle

    def manual_servo_control(self, key):
        """Control servos manually with keyboard input with proper camera alignment"""
        if self.pca is None:
            return
            
        if key == ord('a'):  # Pan left (camera view left)
            if self.invert_pan:
                self.pan_angle = min(180, self.pan_angle + self.servo_step)
            else:
                self.pan_angle = max(0, self.pan_angle - self.servo_step)
        elif key == ord('d'):  # Pan right (camera view right)
            if self.invert_pan:
                self.pan_angle = max(0, self.pan_angle - self.servo_step)
            else:
                self.pan_angle = min(180, self.pan_angle + self.servo_step)
        elif key == ord('w'):  # Tilt up (camera view up)
            if self.invert_tilt:
                self.tilt_angle = min(180, self.tilt_angle + self.servo_step)
            else:
                self.tilt_angle = max(0, self.tilt_angle - self.servo_step)
        elif key == ord('s'):  # Tilt down (camera view down)
            if self.invert_tilt:
                self.tilt_angle = max(0, self.tilt_angle - self.servo_step)
            else:
                self.tilt_angle = min(180, self.tilt_angle + self.servo_step)
        elif key == ord('c'):  # Center servos
            self.pan_angle = 90
            self.tilt_angle = 90
        elif key == ord('m'):  # Toggle manual mode
            self.manual_mode = not self.manual_mode
            mode = "MANUAL" if self.manual_mode else "AUTO"
            print(f"Mode switched to: {mode}")
        elif key == ord('i'):  # Toggle inversion settings
            self.invert_tilt = not self.invert_tilt
            self.invert_pan = not self.invert_pan
            print(f"Servo inversion - Pan: {self.invert_pan}, Tilt: {self.invert_tilt}")
        
        # Update servo positions
        self.servo_pan.angle = self.pan_angle
        self.servo_tilt.angle = self.tilt_angle
        
    def control_pump(self):
        """Control pump based on fire detection timing"""
        current_time = time.time()
        
        if self.fire_detected and not self.pump_active:
            # Fire detected for 5 seconds, turn on pump
            if current_time - self.fire_detection_time >= 5:
                print("FIRE CONFIRMED! Activating pump!")
                self.pump_relay.on()  # Turn pump ON (active_high=False)
                self.pump_active = True
                self.pump_on_time = current_time
                
        elif self.pump_active:
            # Pump has been on for 10 seconds, turn off
            if current_time - self.pump_on_time >= 10:
                print("Deactivating pump after 10 seconds")
                self.pump_relay.off()  # Turn pump OFF
                self.pump_active = False
                self.fire_detected = False
                
    def dht_monitor(self):
        """Monitor DHT-22 sensor in separate thread"""
        while True:
            temp, humidity = self.read_dht22()
            if temp is not None and humidity is not None:
                print(f"Temperature: {temp:.1f}°C, Humidity: {humidity:.1f}%")
            else:
                print("Failed to read DHT22 sensor")
            time.sleep(3)  # Update every 3 seconds

    def draw_detections(self, image, detections):
        """Draw YOLOv8 detections on the image"""
        display_image = image.copy()
        
        # Calculate scaling factors from YOLO size (640x640) to display size (640x480)
        scale_x = self.frame_width / self.yolo_input_size
        scale_y = self.frame_height / self.yolo_input_size
        
        for detection in detections:
            x1, y1, x2, y2 = detection['bbox']
            confidence = detection['confidence']
            class_name = detection['class_name']
            class_id = detection['class_id']
            
            # Scale coordinates from YOLO size to display size
            x1 = int(x1 * scale_x)
            y1 = int(y1 * scale_y)
            x2 = int(x2 * scale_x)
            y2 = int(y2 * scale_y)
            
            # Choose color based on class (RED for fire, BLUE for others) - BGR format
            color = (0, 0, 255) if class_id in self.fire_class_ids else (255, 0, 0)
            
            # Draw bounding box
            cv2.rectangle(display_image, (x1, y1), (x2, y2), color, 2)
            
            # Draw label background
            label = f"{class_name} {confidence:.2f}"
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
            cv2.rectangle(display_image, (x1, y1 - label_size[1] - 10), 
                         (x1 + label_size[0], y1), color, -1)
            
            # Draw label text
            cv2.putText(display_image, label, (x1, y1 - 5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        
        return display_image

    def draw_hud(self, image):
        """Draw heads-up display on the camera feed"""
        hud_image = image.copy()
        
        # Add status information
        status_text = [
            f"Mode: {'MANUAL' if self.manual_mode else 'AUTO'}",
            f"Pan: {self.pan_angle:.0f}° Tilt: {self.tilt_angle:.0f}°",
            f"Fire: {'DETECTED' if self.fire_detected else 'None'}",
            f"Pump: {'ON' if self.pump_active else 'OFF'}",
            f"Earthquake: {self.vibration_count}/5",
            f"Servo Invert: P{self.invert_pan} T{self.invert_tilt}"
        ]
        
        # Draw semi-transparent background for text
        overlay = hud_image.copy()
        cv2.rectangle(overlay, (0, 0), (350, 155), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, hud_image, 0.4, 0, hud_image)
        
        # Draw text
        for i, text in enumerate(status_text):
            cv2.putText(hud_image, text, (10, 25 + i*25), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Draw crosshair in the center
        h, w = hud_image.shape[:2]
        cv2.line(hud_image, (w//2 - 15, h//2), (w//2 + 15, h//2), (0, 255, 0), 2)
        cv2.line(hud_image, (w//2, h//2 - 15), (w//2, h//2 + 15), (0, 255, 0), 2)
        cv2.circle(hud_image, (w//2, h//2), 30, (0, 255, 0), 2)
        
        # Draw controls info
        controls_text = [
            "Controls:",
            "W - Tilt up    S - Tilt down",
            "A - Pan left   D - Pan right", 
            "C - Center servos",
            "M - Toggle manual/auto",
            "I - Toggle servo inversion",
            "Q - Quit"
        ]
        
        # Draw semi-transparent background for controls
        overlay = hud_image.copy()
        cv2.rectangle(overlay, (w-280, 0), (w, 180), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, hud_image, 0.4, 0, hud_image)
        
        # Draw controls text
        for i, text in enumerate(controls_text):
            cv2.putText(hud_image, text, (w-270, 25 + i*25), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        return hud_image
            
    def run(self):
        """Main system loop"""
        print("Starting Fire Detection System with YOLOv8...")
        print(f"YOLO Input Shape: (1, 3, {self.yolo_input_size}, {self.yolo_input_size}) BCHW")
        print(f"Camera Resolution: {self.frame_width}x{self.frame_height}")
        print(f"Servo Inversion - Pan: {self.invert_pan}, Tilt: {self.invert_tilt} (BOTH INVERTED FOR UPSIDE-DOWN CAMERA)")
        
        # Start monitoring threads
        dht_thread = threading.Thread(target=self.dht_monitor)
        dht_thread.daemon = True
        dht_thread.start()
        
        print("System ready. Monitoring for fires...")
        print("Controls:")
        print("  W/S - Tilt up/down (aligned with camera view)")
        print("  A/D - Pan left/right (aligned with camera view)") 
        print("  C - Center servos")
        print("  M - Toggle manual/auto mode")
        print("  I - Toggle servo inversion")
        print("  Q - Quit")
        
        try:
            while True:
                current_time = time.time()
                
                # Capture frame from camera
                try:
                    image = self.picam2.capture_array()
                    
                    # Manual vertical flip for upside-down camera (180 degrees)
                    image = cv2.flip(image, -1)  # Flip both horizontally and vertically
                    
                    # Convert camera RGB to BGR for OpenCV
                    image_bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
                    
                    # Run YOLOv8 detection (only in auto mode and at intervals)
                    fire_detected = False
                    fire_x, fire_y = 0, 0
                    confidence = 0
                    all_detections = []
                    
                    if not self.manual_mode and current_time - self.last_detection_time > self.detection_interval:
                        fire_detected, fire_x, fire_y, confidence, all_detections = self.detect_fire_yolov8(image_bgr)
                        self.last_detection_time = current_time
                        
                        if fire_detected:
                            if not self.fire_detected:
                                self.fire_detected = True
                                self.fire_detection_time = current_time
                                print(f"Fire detected! Confidence: {confidence:.2f}, Position: ({fire_x:.1f}, {fire_y:.1f})")
                            
                            # Aim servos at fire
                            pan_angle, tilt_angle = self.aim_servos_at_fire(fire_x, fire_y)
                            if pan_angle != self.pan_angle or tilt_angle != self.tilt_angle:
                                print(f"Aiming servos - Pan: {pan_angle:.1f}°, Tilt: {tilt_angle:.1f}°")
                            
                        else:
                            if self.fire_detected and not self.pump_active:
                                self.fire_detected = False
                                print("Fire no longer detected")
                    
                    # Control pump based on fire detection
                    self.control_pump()
                    
                    # Draw detections and HUD on the BGR image
                    display_image = self.draw_detections(image_bgr, all_detections)
                    display_image = self.draw_hud(display_image)
                    
                    # Add FPS counter
                    fps = 1.0 / (current_time - self.last_detection_time + 0.001)
                    cv2.putText(display_image, f"FPS: {fps:.1f}", (10, 180), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                    
                    # Display the image (OpenCV expects BGR)
                    cv2.imshow('Fire Detection System - YOLOv8', display_image)
                    
                    # Handle keyboard input
                    key = cv2.waitKey(1) & 0xFF
                    if key != 255:  # A key was pressed
                        if key == ord('q'):  # Quit
                            break
                        else:
                            self.manual_servo_control(key)
                            # Print servo positions when manually moved
                            if key in [ord('w'), ord('a'), ord('s'), ord('d'), ord('c')]:
                                print(f"Manual control - Pan: {self.pan_angle:.0f}°, Tilt: {self.tilt_angle:.0f}°")
                    
                except Exception as e:
                    print(f"Camera capture error: {e}")
                
        except KeyboardInterrupt:
            print("\nShutting down system...")
        finally:
            self.cleanup()
            
    def cleanup(self):
        """Clean up resources"""
        print("Cleaning up...")
        self.pump_relay.off()  # Ensure pump is off
        self.buzzer.off()
        if hasattr(self, 'picam2'):
            self.picam2.stop()
        if hasattr(self, 'pca') and self.pca:
            self.pca.deinit()
        if hasattr(self, 'dht_sensor'):
            try:
                self.dht_sensor.exit()
            except:
                pass
        cv2.destroyAllWindows()
        print("Cleanup complete")

# Run the system
if __name__ == "__main__":
    system = FireDetectionSystem()
    system.run()