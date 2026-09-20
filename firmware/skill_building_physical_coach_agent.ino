#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <MPU6050.h>

// ------------------------------
// User configuration
// ------------------------------
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* BACKEND_ENDPOINT = "http://YOUR_BACKEND_IP:5000/imu";
const char* SENSOR_ID = "joint_a"; // Change to joint_b for the second wearable

const unsigned long SAMPLE_INTERVAL_MS = 20; // 50 Hz

MPU6050 mpu;
unsigned long lastSampleTime = 0;

void connectToWifi() {
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(" connected");
  Serial.print("Device IP: ");
  Serial.println(WiFi.localIP());
}

void setup() {
  Serial.begin(115200);
  Wire.begin();

  mpu.initialize();
  if (!mpu.testConnection()) {
    Serial.println("MPU6050 connection failed. Check wiring.");
    while (true) {
      delay(1000);
    }
  }

  connectToWifi();
}

void sendImuSample() {
  int16_t axRaw, ayRaw, azRaw;
  int16_t gxRaw, gyRaw, gzRaw;

  mpu.getMotion6(&axRaw, &ayRaw, &azRaw, &gxRaw, &gyRaw, &gzRaw);

  // Convert to physical units:
  // - Accelerometer: ±2g mode -> 16384 LSB/g
  // - Gyroscope: ±250 deg/s mode -> 131 LSB/(deg/s)
  float ax = axRaw / 16384.0f;
  float ay = ayRaw / 16384.0f;
  float az = azRaw / 16384.0f;

  float gx = gxRaw / 131.0f;
  float gy = gyRaw / 131.0f;
  float gz = gzRaw / 131.0f;

  String payload = "{";
  payload += "\"sensor_id\":\"" + String(SENSOR_ID) + "\",";
  payload += "\"timestamp\":" + String(millis()) + ",";
  payload += "\"accel\":{";
  payload += "\"x\":" + String(ax, 6) + ",";
  payload += "\"y\":" + String(ay, 6) + ",";
  payload += "\"z\":" + String(az, 6) + "},";
  payload += "\"gyro\":{";
  payload += "\"x\":" + String(gx, 6) + ",";
  payload += "\"y\":" + String(gy, 6) + ",";
  payload += "\"z\":" + String(gz, 6) + "}";
  payload += "}";

  if (WiFi.status() != WL_CONNECTED) {
    connectToWifi();
  }

  HTTPClient http;
  http.begin(BACKEND_ENDPOINT);
  http.addHeader("Content-Type", "application/json");

  int responseCode = http.POST(payload);
  if (responseCode > 0) {
    Serial.printf("POST %d\n", responseCode);
  } else {
    Serial.printf("POST failed: %s\n", http.errorToString(responseCode).c_str());
  }

  http.end();
}

void loop() {
  unsigned long now = millis();
  if (now - lastSampleTime >= SAMPLE_INTERVAL_MS) {
    lastSampleTime = now;
    sendImuSample();
  }
}
