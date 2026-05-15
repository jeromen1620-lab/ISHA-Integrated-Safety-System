# ISHA-Integrated-Safety-System
An IoT-based emergency detection system utilizing Raspberry Pi 5 and YOLOv8 for home safety
### Project Overview
ISHA is an integrated emergency detection and alert system designed to monitor multiple household hazards, including fire, gas leaks, and earthquakes
![System Block Diagram] (images/System_block_diagram.png)
![Schematic Diagram] (images/Schematic_Diagram.png)
### Key Features
* Multi-Hazard Detection: Real-time monitoring of gas leaks (MQ-2), seismic activity (SW-420), and temperature/humidity (DHT22)
* AI-Powered Fire Prevention: Uses a Raspberry Pi Camera Module 3 and the YOLOv8n algorithm for real-time fire detection
* Automated Mitigation: Automatically activates a water mist mechanism upon fire detection
* Mobile Integration: Real-time alerts and live camera feed via a Kotlin-based Android application

### Hardware Stack
* Raspberry Pi 5 (Central Processing Unit) 
* Raspberry Pi Camera Module 3 
* Sensors: MQ-2 (Gas), SW-420 (Vibration), DHT22 (Temp/Humidity) 
* Actuators: MG996R Servos, Water Pump, Buzzer 

### Proponents
John Allain P. Accad, Rhen L. Berdol, Jerome F. Narciso, Karl Edison R. Natividad, Ruzzel P. Teotico. 
STI College Caloocan, Computer Engineering 
