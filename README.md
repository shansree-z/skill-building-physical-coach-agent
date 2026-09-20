# Skill-Building Physical Coach Agent

AI-based causal fault diagnosis system for physical skill coaching using wearable sensors.

## Problem Statement
Build a wearable AI coaching system that diagnoses *why* movement errors happen (timing, form, or force) instead of only outputting a similarity score.

## Project Structure
- `firmware/` - ESP32 + MPU6050 Arduino firmware that samples at 50Hz and streams IMU JSON over Wi-Fi.
- `backend/feature_extraction.py` - Flask backend that buffers dual-sensor IMU data, segments repetitions with gyroscope zero-velocity-crossing logic, and extracts timing/form/force features.
- `backend/agent_reasoning.py` - Reasoning module that compares extracted features to a baseline profile and sends a structured diagnostic prompt to an Azure AI Foundry-compatible LLM endpoint.
- `reference_profile.json` - Example baseline timing/form/force profile for a sample exercise.
- `requirements.txt` - Python dependencies.

## Tech Stack
- Firmware: C++ (Arduino framework, ESP32, MPU6050)
- Backend: Python (Flask, NumPy, Requests)
- AI Integration: Azure AI Foundry-compatible chat completions API

## Firmware Setup (ESP32 + MPU6050)
1. Open `firmware/skill_building_physical_coach_agent.ino` in Arduino IDE.
2. Install required libraries:
   - `MPU6050`
   - `WiFi` / `HTTPClient` (bundled for ESP32 core)
3. Set:
   - `WIFI_SSID`
   - `WIFI_PASSWORD`
   - `BACKEND_ENDPOINT`
   - `SENSOR_ID` (`joint_a` or `joint_b`)
4. Upload firmware to each ESP32 wearable device.

## Backend Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python backend/feature_extraction.py
```

### IMU Streaming Endpoint
- **POST** `/imu`
- Payload example:
```json
{
  "sensor_id": "joint_a",
  "timestamp": 12540,
  "accel": {"x": 0.01, "y": -0.02, "z": 0.99},
  "gyro": {"x": 1.2, "y": 42.0, "z": 0.3}
}
```

Backend response:
- `202` while buffering / waiting for a full repetition
- `200` with extracted `timing`, `form`, and `force` features when repetition is detected

## Agent Reasoning Setup
Set environment variables before calling `backend/agent_reasoning.py`:

```bash
export AZURE_AI_FOUNDRY_ENDPOINT="https://<your-resource>.openai.azure.com"
export AZURE_AI_FOUNDRY_API_KEY="<your-api-key>"
export AZURE_AI_FOUNDRY_MODEL="gpt-4o-mini"
export AZURE_AI_FOUNDRY_API_VERSION="2024-05-01-preview"
```

Run a local reasoning demo:
```bash
python backend/agent_reasoning.py
```

If endpoint or key are missing, the module returns the generated diagnostic prompt and computed deviations for debugging.
