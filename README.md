# AI Traffic Signal Control + ESP32 IoT

## Included
- `app.py` — complete four-direction GUI
- `detector.py` — normal YOLO vehicle detection
- `emergency_detector.py` — separate automatic emergency detection
- `iot_controller.py` — Python ↔ ESP32 Wi-Fi communication
- `esp32_traffic_signal.ino` — ESP32 firmware
- `test_esp32.py` — ESP32 connection test
- `requirements.txt` — Python dependencies
- `RUN.bat` — install and run
- `TEST_ESP32.bat` — test ESP32

## Models
Place your working `yolo11n.pt` in this folder. The emergency detector uses `yolov8s-worldv2.pt`; Ultralytics can download it on first use if internet is available.

## Setup
1. Flash `esp32_traffic_signal.ino` to ESP32 after entering Wi-Fi credentials.
2. Open Serial Monitor at 115200 baud and copy the ESP32 IP.
3. Edit `iot_controller.py`: `ESP32_IP = "YOUR_ESP32_IP"`.
4. Connect laptop and ESP32 to the same Wi-Fi.
5. Run `TEST_ESP32.bat` and verify the NORTH green LED.
6. Run `RUN.bat`.
7. Upload NORTH/EAST/SOUTH/WEST images.
8. Click `CALCULATE TRAFFIC SIGNAL`.
9. Click `START SIGNAL SEQUENCE`.

## Logic
Normal vehicle detection is performed separately from emergency detection. Emergency directions are placed first; remaining directions are ordered by vehicle count. Python sends each direction and green duration to ESP32.

## Pins
NORTH: R13 Y12 G14  
EAST: R27 Y26 G25  
SOUTH: R33 Y32 G23  
WEST: R19 Y18 G5  

Use a 220-ohm resistor in series with every LED. For high-power real traffic lamps, use proper isolated driver hardware; never connect mains/high-power lamps directly to ESP32 GPIO pins.
