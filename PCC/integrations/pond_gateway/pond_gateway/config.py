from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Mapping
from urllib.parse import urlparse


class ConfigurationError(ValueError):
    pass


_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    try:
        return int(env.get(key, str(default)))
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be an integer") from exc


def _float(env: Mapping[str, str], key: str, default: float) -> float:
    try:
        return float(env.get(key, str(default)))
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be a number") from exc


def _bool(env: Mapping[str, str], key: str, default: bool = False) -> bool:
    value = env.get(key, str(default)).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{key} must be true or false")


@dataclass(frozen=True)
class RegisterSpec:
    metric: str
    unit: str
    slave_id: int
    address: int
    register_type: str
    scale: float
    offset: float
    signed: bool
    physical_min: float
    physical_max: float

    def decode(self, raw: int) -> float:
        if not 0 <= raw <= 0xFFFF:
            raise ValueError("register value must fit uint16")
        value = raw - 0x10000 if self.signed and raw >= 0x8000 else raw
        return round(value * self.scale + self.offset, 4)


@dataclass(frozen=True)
class Settings:
    mode: str
    pcc_url: str
    telemetry_token: str
    site_id: str
    line_id: str
    station_id: str
    device_id: str
    sample_interval_seconds: float
    request_timeout_seconds: float
    serial_port: str
    baudrate: int
    bytesize: int
    parity: str
    stopbits: int
    serial_timeout_seconds: float
    spool_path: str
    heartbeat_path: str
    ph: RegisterSpec
    temperature: RegisterSpec

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if values is None else values
        mode = env.get("POND_GATEWAY_MODE", "mock").strip().lower()
        if mode not in {"mock", "modbus"}:
            raise ConfigurationError("POND_GATEWAY_MODE must be mock or modbus")
        parity = env.get("POND_SERIAL_PARITY", "N").strip().upper()
        if parity not in {"N", "E", "O"}:
            raise ConfigurationError("POND_SERIAL_PARITY must be N, E or O")
        register_type = env.get("POND_REGISTER_TYPE", "holding").strip().lower()
        if register_type not in {"holding", "input"}:
            raise ConfigurationError("POND_REGISTER_TYPE must be holding or input")
        token = env.get("PCC_TELEMETRY_TOKEN", "").strip()
        if not token:
            raise ConfigurationError("PCC_TELEMETRY_TOKEN is required")
        sample_interval = _float(env, "POND_SAMPLE_INTERVAL_SECONDS", 5.0)
        if sample_interval < 1 or sample_interval > 3600:
            raise ConfigurationError("POND_SAMPLE_INTERVAL_SECONDS must be between 1 and 3600")
        pcc_url = env.get("PCC_TELEMETRY_URL", "http://127.0.0.1:3000/api/v1/telemetry").rstrip("/")
        parsed_url = urlparse(pcc_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ConfigurationError("PCC_TELEMETRY_URL must be an http(s) URL")
        identifiers = {
            "POND_SITE_ID": env.get("POND_SITE_ID", "factory-01"),
            "POND_LINE_ID": env.get("POND_LINE_ID", "line-1"),
            "POND_STATION_ID": env.get("POND_STATION_ID", "final-pond"),
            "POND_DEVICE_ID": env.get("POND_DEVICE_ID", "pond-gateway-01"),
        }
        invalid_identifier = next((key for key, value in identifiers.items() if not _ID.fullmatch(value)), None)
        if invalid_identifier:
            raise ConfigurationError(f"{invalid_identifier} must contain only letters, numbers, _ or -")
        request_timeout = _float(env, "PCC_REQUEST_TIMEOUT_SECONDS", 5.0)
        serial_timeout = _float(env, "POND_SERIAL_TIMEOUT_SECONDS", 2.0)
        baudrate = _int(env, "POND_SERIAL_BAUDRATE", 9600)
        bytesize = _int(env, "POND_SERIAL_BYTESIZE", 8)
        stopbits = _int(env, "POND_SERIAL_STOPBITS", 1)
        if not 0.1 <= request_timeout <= 60:
            raise ConfigurationError("PCC_REQUEST_TIMEOUT_SECONDS must be between 0.1 and 60")
        if not 0.1 <= serial_timeout <= 30:
            raise ConfigurationError("POND_SERIAL_TIMEOUT_SECONDS must be between 0.1 and 30")
        if baudrate <= 0 or bytesize not in {7, 8} or stopbits not in {1, 2}:
            raise ConfigurationError("invalid serial baudrate, bytesize or stopbits")

        def register(prefix: str, metric: str, unit: str, physical_min: float, physical_max: float) -> RegisterSpec:
            kind = env.get(f"{prefix}_REGISTER_TYPE", register_type).strip().lower()
            if kind not in {"holding", "input"}:
                raise ConfigurationError(f"{prefix}_REGISTER_TYPE must be holding or input")
            slave_id = _int(env, f"{prefix}_SLAVE_ID", 1)
            address = _int(env, f"{prefix}_REGISTER_ADDRESS", 0 if prefix == "POND_PH" else 1)
            if not 1 <= slave_id <= 247:
                raise ConfigurationError(f"{prefix}_SLAVE_ID must be between 1 and 247")
            if not 0 <= address <= 65535:
                raise ConfigurationError(f"{prefix}_REGISTER_ADDRESS must be between 0 and 65535")
            return RegisterSpec(
                metric=metric,
                unit=unit,
                slave_id=slave_id,
                address=address,
                register_type=kind,
                scale=_float(env, f"{prefix}_SCALE", 0.01 if prefix == "POND_PH" else 0.1),
                offset=_float(env, f"{prefix}_OFFSET", 0.0),
                signed=_bool(env, f"{prefix}_SIGNED", False),
                physical_min=physical_min,
                physical_max=physical_max,
            )

        return cls(
            mode=mode,
            pcc_url=pcc_url,
            telemetry_token=token,
            site_id=identifiers["POND_SITE_ID"],
            line_id=identifiers["POND_LINE_ID"],
            station_id=identifiers["POND_STATION_ID"],
            device_id=identifiers["POND_DEVICE_ID"],
            sample_interval_seconds=sample_interval,
            request_timeout_seconds=request_timeout,
            serial_port=env.get("POND_SERIAL_PORT", "COM3"),
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            serial_timeout_seconds=serial_timeout,
            spool_path=env.get("POND_SPOOL_PATH", "./data/pond-gateway-spool.sqlite3"),
            heartbeat_path=env.get("POND_HEARTBEAT_PATH", "./data/pond-gateway-heartbeat.json"),
            ph=register("POND_PH", "water_ph", "pH", 0.0, 14.0),
            temperature=register("POND_TEMPERATURE", "water_temperature", "°C", -10.0, 100.0),
        )
