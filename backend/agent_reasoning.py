"""LLM reasoning module for diagnosing timing/form/force faults."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

import requests


class CoachReasoner:
    def __init__(self, reference_profile_path: str = "reference_profile.json") -> None:
        self.reference_profile = self._load_reference_profile(reference_profile_path)
        self.endpoint = os.getenv("AZURE_AI_FOUNDRY_ENDPOINT", "").rstrip("/")
        self.api_key = os.getenv("AZURE_AI_FOUNDRY_API_KEY", "")
        self.model = os.getenv("AZURE_AI_FOUNDRY_MODEL", "gpt-4o-mini")
        self.api_version = os.getenv("AZURE_AI_FOUNDRY_API_VERSION", "2024-05-01-preview")

    @staticmethod
    def _load_reference_profile(reference_profile_path: str) -> Dict[str, Any]:
        profile_file = Path(reference_profile_path)
        with profile_file.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def compare_to_reference(self, extracted_features: Dict[str, Any]) -> Dict[str, Any]:
        reference = self.reference_profile

        timing_delta = (
            extracted_features["timing"]["onset_delta_ms"]
            - reference["timing"]["onset_delta_ms"]
        )

        form_delta = {}
        force_delta = {}
        for sensor in ("joint_a", "joint_b"):
            form_delta[sensor] = {
                "angle_range_deg": (
                    extracted_features["form"][sensor]["angle_range_deg"]
                    - reference["form"][sensor]["angle_range_deg"]
                )
            }
            force_delta[sensor] = {
                "peak_angular_velocity_deg_s": (
                    extracted_features["force"][sensor]["peak_angular_velocity_deg_s"]
                    - reference["force"][sensor]["peak_angular_velocity_deg_s"]
                ),
                "peak_acceleration_g": (
                    extracted_features["force"][sensor]["peak_acceleration_g"]
                    - reference["force"][sensor]["peak_acceleration_g"]
                ),
            }

        return {
            "timing": {"onset_delta_ms": timing_delta},
            "form": form_delta,
            "force": force_delta,
        }

    def build_prompt(self, deviations: Dict[str, Any]) -> str:
        return (
            "You are a biomechanics coaching assistant.\n"
            "Analyze the deviation data and diagnose whether timing, form, or force "
            "is the primary fault dimension.\n"
            "Then explain the biomechanical cause in simple terms and give one corrective "
            "instruction in plain language.\n"
            "Respond as JSON with keys: primary_fault, biomechanical_cause, corrective_instruction.\n\n"
            f"Deviation data:\n{json.dumps(deviations, indent=2)}"
        )

    def diagnose_with_llm(self, extracted_features: Dict[str, Any]) -> Dict[str, Any]:
        deviations = self.compare_to_reference(extracted_features)
        prompt = self.build_prompt(deviations)

        if not self.endpoint or not self.api_key:
            return {
                "warning": "Missing AZURE_AI_FOUNDRY_ENDPOINT or AZURE_AI_FOUNDRY_API_KEY",
                "deviations": deviations,
                "prompt": prompt,
            }

        url = f"{self.endpoint}/openai/deployments/{self.model}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "api-key": self.api_key,
        }
        params = {"api-version": self.api_version}
        body = {
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert in human movement diagnostics.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        response = requests.post(url, headers=headers, params=params, json=body, timeout=30)
        response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]
        return {
            "deviations": deviations,
            "llm_response": content,
        }


if __name__ == "__main__":
    reasoner = CoachReasoner()

    sample_features = {
        "timing": {"onset_delta_ms": 140.0},
        "form": {
            "joint_a": {"angle_range_deg": 54.0},
            "joint_b": {"angle_range_deg": 42.0},
        },
        "force": {
            "joint_a": {
                "peak_angular_velocity_deg_s": 210.0,
                "peak_acceleration_g": 2.3,
            },
            "joint_b": {
                "peak_angular_velocity_deg_s": 195.0,
                "peak_acceleration_g": 2.0,
            },
        },
    }

    print(json.dumps(reasoner.diagnose_with_llm(sample_features), indent=2))
