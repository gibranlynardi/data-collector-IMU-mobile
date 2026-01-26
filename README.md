# 📱 IMU Data Collector (Flutter)

![Flutter Version](https://img.shields.io/badge/Flutter-3.x-blue?logo=flutter) ![Platform](https://img.shields.io/badge/Platform-Android-green?logo=android) ![License](https://img.shields.io/badge/License-MIT-purple)

> **⚠️ Acknowledgement:**
> This project is based on [Sensors-App](https://github.com/Kshitijpawar/Sensors-App) by **Kshitijpawar**.
>
> It has been **heavily refactored and re-architected** to pivot from online Firebase streaming to **offline CSV Data Collection** for Machine Learning Dataset. Key changes include a complete rewrite of the data logic to support Dual Mode (Phone Internal/Bluetooth), dynamic frequency control, physical unit standardization, and a new dashboard UI.

**IMU Data Collector** is a mobile application designed for acquiring inertial sensor data (Accelerometer & Gyroscope) in real-time. This application is optimized for collecting **Machine Learning datasets** (e.g., Human Activity Recognition), Physics research, or IoT prototyping.

The core feature is **Dual Mode Acquisition**, allowing users to seamlessly switch between **Internal Smartphone Sensors** and **External Hardware** (Arduino/ESP32) via Bluetooth Classic (HC-05).

---

## Key Features

* **Dual Sensor Mode:** Seamlessly switch data sources between **Internal Sensors** (Phone) and **External Sensors** (Bluetooth).
* **Real-time Visualization:** High-refresh-rate plotting of 6-Axis data (Acc X,Y,Z & Gyro X,Y,Z).
* **CSV Data Logging:** Saves structured datasets directly to local storage for offline analysis.
* **Dynamic Configuration:**
    * Adjust **Sampling Rate** (Hz) on-the-fly (1 Hz - 100 Hz).
    * Tag data with **Location ID** and **Label ID** using restricted integer dropdowns (0-10) to ensure dataset consistency.
* **Unit Standardization:** Internal sensor data is automatically converted to standard physical units:
    * Accelerometer: **g (Gravitational Unit)**
    * Gyroscope: **&deg;/s (Degrees per second)**

---



## CSV Output

Generated CSV files are stored in `Documents` or `Android/data/com.example.sensors_app/files/`. Each row represents a single time-step.

| Column | Header Name | Unit | Description |
| :--- | :--- | :--- | :--- |
| 1 | `Timestamp` | ISO8601 | Precise capture time. |
| 2 | `Acc_X_g` | g | X-axis Acceleration (Normalized to gravity). |
| 3 | `Acc_Y_g` | g | Y-axis Acceleration. |
| 4 | `Acc_Z_g` | g | Z-axis Acceleration (approx 1.0 when static). |
| 5 | `Gyro_X_deg` | &deg;/s | X-axis Angular Velocity. |
| 6 | `Gyro_Y_deg` | &deg;/s | Y-axis Angular Velocity. |
| 7 | `Gyro_Z_deg` | &deg;/s | Z-axis Angular Velocity. |
| 8 | `Location` | `int` | Sensor placement ID (0-10), user-defined. |
| 9 | `Label` | `int` | Activity Label ID (0-10), user-defined. |

---

## Setup

1.  **Clone Repository:**
    ```bash
    git clone [https://github.com/username/imu-data-collector.git](https://github.com/username/imu-data-collector.git)
    cd imu-data-collector
    ```

2.  **Install Dependencies:**
    ```bash
    flutter pub get
    ```

3.  **Run on Android Device:**
    Connect your device via USB and ensure USB Debugging is active.
    ```bash
    flutter run --release
    ```


---

## Arduino Mode

To ensure data consistency when using **Bluetooth Mode**, your microcontroller (Arduino + HC-05 + MPU6050) must transmit data in the following format:

**Protocol Format:**
```text
ax,ay,az,gx,gy,gz\n
```
Values must be comma-separated and end with a newline character.


To match the app's internal sensor units, please ensure your Arduino converts raw data to *g* and &deg;/s before sending.
```c++
void loop() {
  mpu.getEvent(&a, &g, &temp);

  Serial.print(a.acceleration.x / 9.81); Serial.print(",");
  Serial.print(a.acceleration.y / 9.81); Serial.print(",");
  Serial.print(a.acceleration.z / 9.81); Serial.print(",");
  
  Serial.print(g.gyro.x * 57.296); Serial.print(",");
  Serial.print(g.gyro.y * 57.296); Serial.print(",");
  Serial.println(g.gyro.z * 57.296); 

  delay(20); 
}
```

