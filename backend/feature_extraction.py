"""Flask backend for IMU buffering, segmentation, and feature extraction."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional
import math

from flask import Flask, jsonify, request
import numpy as np


GYRO_MOVEMENT_THRESHOLD = 20.0  # deg/s
MAX_BUFFER_SIZE = 2000
SENSORS = ("joint_a", "joint_b")


@dataclass
class ImuSample:
    timestamp: float
    accel: np.ndarray
    gyro: np.ndarray

    @property
    def gyro_magnitude(self) -> float:
        return float(np.linalg.norm(self.gyro))

    @property
    def accel_magnitude(self) -> float:
        return float(np.linalg.norm(self.accel))


class RepetitionFeatureExtractor:
    def __init__(self) -> None:
        self.buffers: Dict[str, Deque[ImuSample]] = {
            sensor: deque(maxlen=MAX_BUFFER_SIZE) for sensor in SENSORS
        }
        self.crossings: Dict[str, Deque[float]] = {
            sensor: deque(maxlen=20) for sensor in SENSORS
        }

    def add_sample(self, sensor_id: str, sample: ImuSample) -> Optional[dict]:
        if sensor_id not in self.buffers:
            return None

        sensor_buffer = self.buffers[sensor_id]
        sensor_buffer.append(sample)
        self._detect_zero_velocity_crossing(sensor_id)
        return self._try_extract_repetition_features()

    def _detect_zero_velocity_crossing(self, sensor_id: str) -> None:
        sensor_buffer = self.buffers[sensor_id]
        if len(sensor_buffer) < 2:
            return

        prev = sensor_buffer[-2].gyro_magnitude - GYRO_MOVEMENT_THRESHOLD
        curr = sensor_buffer[-1].gyro_magnitude - GYRO_MOVEMENT_THRESHOLD

        # Crossing from movement (>0) to near-rest (<=0) marks a phase boundary.
        if prev > 0 and curr <= 0:
            self.crossings[sensor_id].append(sensor_buffer[-1].timestamp)

    def _try_extract_repetition_features(self) -> Optional[dict]:
        if not all(len(self.crossings[sensor]) >= 2 for sensor in SENSORS):
            return None

        # Use the most recent completed cycle visible on both joints.
        starts = [self.crossings[sensor][-2] for sensor in SENSORS]
        ends = [self.crossings[sensor][-1] for sensor in SENSORS]

        repetition_start = max(starts)
        repetition_end = min(ends)
        if repetition_end <= repetition_start:
            return None

        windows = {
            sensor: self._slice_buffer(self.buffers[sensor], repetition_start, repetition_end)
            for sensor in SENSORS
        }

        if not all(len(window) >= 2 for window in windows.values()):
            return None

        return self._extract_features(windows, repetition_start, repetition_end)

    @staticmethod
    def _slice_buffer(
        samples: Deque[ImuSample], start_ts: float, end_ts: float
    ) -> List[ImuSample]:
        return [sample for sample in samples if start_ts <= sample.timestamp <= end_ts]

    def _extract_features(
        self,
        windows: Dict[str, List[ImuSample]],
        repetition_start: float,
        repetition_end: float,
    ) -> dict:
        timing = {
            "joint_a_phase_onset_ms": self._phase_onset_ms(windows["joint_a"], repetition_start),
            "joint_b_phase_onset_ms": self._phase_onset_ms(windows["joint_b"], repetition_start),
        }
        timing["onset_delta_ms"] = abs(
            timing["joint_a_phase_onset_ms"] - timing["joint_b_phase_onset_ms"]
        )

        form = {
            sensor: {"angle_range_deg": self._angle_range_deg(samples)}
            for sensor, samples in windows.items()
        }

        force = {
            sensor: {
                "peak_angular_velocity_deg_s": max(
                    sample.gyro_magnitude for sample in samples
                ),
                "peak_acceleration_g": max(sample.accel_magnitude for sample in samples),
            }
            for sensor, samples in windows.items()
        }

        return {
            "repetition_window_ms": {
                "start": repetition_start,
                "end": repetition_end,
                "duration": repetition_end - repetition_start,
            },
            "timing": timing,
            "form": form,
            "force": force,
        }

    @staticmethod
    def _phase_onset_ms(samples: List[ImuSample], repetition_start: float) -> float:
        for sample in samples:
            if sample.gyro_magnitude > GYRO_MOVEMENT_THRESHOLD:
                return sample.timestamp - repetition_start
        return 0.0

    @staticmethod
    def _angle_range_deg(samples: List[ImuSample]) -> float:
        # Beginner-friendly approximation: integrate gyroscope Y-axis to angle.
        if len(samples) < 2:
            return 0.0

        angles = [0.0]
        running_angle = 0.0
        for prev, curr in zip(samples[:-1], samples[1:]):
            dt_seconds = max((curr.timestamp - prev.timestamp) / 1000.0, 1e-3)
            running_angle += curr.gyro[1] * dt_seconds
            angles.append(running_angle)

        return float(max(angles) - min(angles))


app = Flask(__name__)
extractor = RepetitionFeatureExtractor()


@app.post("/imu")
def ingest_imu() -> tuple:
    payload = request.get_json(silent=True) or {}

    try:
        sensor_id = str(payload["sensor_id"])
        timestamp = float(payload["timestamp"])

        accel = np.array(
            [
                float(payload["accel"]["x"]),
                float(payload["accel"]["y"]),
                float(payload["accel"]["z"]),
            ],
            dtype=float,
        )
        gyro = np.array(
            [
                float(payload["gyro"]["x"]),
                float(payload["gyro"]["y"]),
                float(payload["gyro"]["z"]),
            ],
            dtype=float,
        )
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Invalid payload format"}), 400

    sample = ImuSample(timestamp=timestamp, accel=accel, gyro=gyro)
    features = extractor.add_sample(sensor_id, sample)

    if sensor_id not in SENSORS:
        return jsonify({"error": f"Unsupported sensor_id '{sensor_id}'"}), 400

    if features is None:
        return jsonify({"status": "buffering"}), 202

    return jsonify({"status": "repetition_detected", "features": features}), 200


@app.get("/health")
def health() -> tuple:
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
