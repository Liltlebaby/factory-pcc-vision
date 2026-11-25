from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PLACEHOLDER_MARKERS = (
    "replace",
    "your_project",
    "example",
    "changeme",
    "password",
)

REQUIRED_KEYS = (
    "PUBLIC_VISION_MONITOR_URL",
    "PCC_PUBLIC_URL",
    "PCC_ORIGINS",
    "RACK_MODEL_FILE",
    "SUPABASE_URL",
    "SUPABASE_SECRET_KEY",
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
    "RACK_API_TOKEN",
    "PCC_SYNC_TOKEN",
    "PCC_TELEMETRY_TOKEN",
    "CAMERA_RTSP_AI",
)

SECRET_KEYS = (
    "SUPABASE_SECRET_KEY",
    "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
    "RACK_API_TOKEN",
    "PCC_SYNC_TOKEN",
    "PCC_TELEMETRY_TOKEN",
)

POND_KEYS = (
    "POND_PH_SLAVE_ID",
    "POND_PH_REGISTER_TYPE",
    "POND_PH_REGISTER_ADDRESS",
    "POND_PH_SCALE",
    "POND_TEMPERATURE_SLAVE_ID",
    "POND_TEMPERATURE_REGISTER_TYPE",
    "POND_TEMPERATURE_REGISTER_ADDRESS",
    "POND_TEMPERATURE_SCALE",
)


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    message: str


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"line {line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"line {line_number}: invalid variable name")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _placeholder(value: str) -> bool:
    lowered = value.casefold()
    return not value or any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def _valid_url(value: str, schemes: set[str]) -> bool:
    parsed = urlparse(value)
    return parsed.scheme.casefold() in schemes and bool(parsed.hostname)


def _float(value: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def validate_config(
    env: Mapping[str, str],
    *,
    project_root: Path,
    with_pond: bool = False,
) -> list[Finding]:
    findings: list[Finding] = []

    for key in REQUIRED_KEYS:
        value = env.get(key, "").strip()
        if not value:
            findings.append(Finding("error", "missing", f"{key} is required"))
        elif _placeholder(value):
            findings.append(Finding("error", "placeholder", f"{key} still contains a placeholder"))

    public_urls = {
        "PUBLIC_VISION_MONITOR_URL": {"https"},
        "PCC_PUBLIC_URL": {"https"},
        "SUPABASE_URL": {"https"},
        "NEXT_PUBLIC_SUPABASE_URL": {"https"},
    }
    for key, schemes in public_urls.items():
        value = env.get(key, "").strip()
        if value and not _valid_url(value, schemes):
            findings.append(Finding("error", "invalid_url", f"{key} must be a valid HTTPS URL"))

    camera_url = env.get("CAMERA_RTSP_AI", "").strip()
    if camera_url and not _valid_url(camera_url, {"rtsp", "rtsps"}):
        findings.append(Finding("error", "invalid_rtsp", "CAMERA_RTSP_AI must use rtsp:// or rtsps://"))

    origins = [item.strip() for item in env.get("PCC_ORIGINS", "").split(",") if item.strip()]
    if env.get("PCC_ORIGINS") and (
        not origins or any(not _valid_url(origin, {"https"}) for origin in origins)
    ):
        findings.append(Finding("error", "invalid_origins", "Every PCC_ORIGINS entry must be an HTTPS origin"))

    if (
        env.get("SUPABASE_URL", "").rstrip("/")
        != env.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    ):
        findings.append(Finding("error", "supabase_mismatch", "SUPABASE URLs must point to the same project"))

    secret_values: dict[str, str] = {}
    for key in SECRET_KEYS:
        value = env.get(key, "").strip()
        if not value:
            continue
        if len(value) < 32:
            findings.append(Finding("error", "weak_secret", f"{key} must contain at least 32 characters"))
        if _placeholder(value):
            findings.append(Finding("error", "placeholder", f"{key} still contains a placeholder"))
        if value in secret_values:
            findings.append(
                Finding("error", "reused_secret", f"{key} must differ from {secret_values[value]}")
            )
        else:
            secret_values[value] = key

    if env.get("PCC_AUTH_REQUIRED", "false").casefold() not in {"true", "1", "yes", "on"}:
        findings.append(Finding("error", "auth_disabled", "PCC_AUTH_REQUIRED must be true in production"))

    for key, default in (("PCC_PORT", "3000"), ("VISION_MONITOR_PORT", "8011")):
        port = _int(env.get(key, default))
        if port is None or not 1 <= port <= 65535:
            findings.append(Finding("error", "invalid_port", f"{key} must be an integer from 1 to 65535"))

    model_value = env.get("RACK_MODEL_FILE", "").strip()
    if model_value:
        model_path = Path(model_value)
        if not model_path.is_absolute():
            model_path = project_root / model_path
        if model_path.suffix.casefold() != ".pt":
            findings.append(Finding("error", "model_type", "RACK_MODEL_FILE must point to a .pt file"))
        elif not model_path.is_file() or model_path.stat().st_size == 0:
            findings.append(Finding("error", "model_missing", "RACK_MODEL_FILE does not exist or is empty"))

    if with_pond:
        for key in POND_KEYS:
            value = env.get(key, "").strip()
            if not value:
                findings.append(Finding("error", "pond_missing", f"{key} is required for pond-iot"))
            elif _placeholder(value):
                findings.append(Finding("error", "pond_placeholder", f"{key} still contains a placeholder"))

        for key in ("POND_PH_SLAVE_ID", "POND_TEMPERATURE_SLAVE_ID"):
            number = _int(env.get(key, ""))
            if number is None or not 1 <= number <= 247:
                findings.append(Finding("error", "pond_slave", f"{key} must be an integer from 1 to 247"))

        for key in ("POND_PH_REGISTER_ADDRESS", "POND_TEMPERATURE_REGISTER_ADDRESS"):
            number = _int(env.get(key, ""))
            if number is None or not 0 <= number <= 65535:
                findings.append(Finding("error", "pond_register", f"{key} must be a zero-based register from 0 to 65535"))

        for key in ("POND_PH_SCALE", "POND_TEMPERATURE_SCALE"):
            number = _float(env.get(key, ""))
            if number is None or number == 0:
                findings.append(Finding("error", "pond_scale", f"{key} must be a finite non-zero number"))

        for key in ("POND_PH_REGISTER_TYPE", "POND_TEMPERATURE_REGISTER_TYPE"):
            if env.get(key, "").casefold() not in {"holding", "input"}:
                findings.append(Finding("error", "pond_register_type", f"{key} must be holding or input"))

        serial_device = env.get("POND_SERIAL_DEVICE_HOST", "").strip()
        if not serial_device:
            findings.append(Finding("error", "pond_serial", "POND_SERIAL_DEVICE_HOST is required for pond-iot"))
        elif os.name != "nt" and not Path(serial_device).exists():
            findings.append(Finding("error", "pond_serial", "POND_SERIAL_DEVICE_HOST is not present on this host"))

    return list(dict.fromkeys(findings))


def check_services(env: Mapping[str, str], *, timeout_seconds: float = 3.0) -> list[Finding]:
    pcc_port = int(env.get("PCC_PORT", "3000"))
    vision_port = int(env.get("VISION_MONITOR_PORT", "8011"))
    endpoints = (
        ("pcc", f"http://127.0.0.1:{pcc_port}/api/health"),
        ("vision-monitor", f"http://127.0.0.1:{vision_port}/health"),
    )
    findings: list[Finding] = []
    for name, url in endpoints:
        try:
            request = Request(url, headers={"User-Agent": "factory-production-preflight/1"})
            with urlopen(request, timeout=timeout_seconds) as response:
                if not 200 <= response.status < 300:
                    findings.append(Finding("error", "service_http", f"{name} health returned HTTP {response.status}"))
        except HTTPError as exc:
            findings.append(Finding("error", "service_http", f"{name} health returned HTTP {exc.code}"))
        except (URLError, TimeoutError, OSError):
            findings.append(Finding("error", "service_unreachable", f"{name} health endpoint is unreachable"))
    return findings


def summarize(findings: Iterable[Finding]) -> dict[str, int]:
    result = {"errors": 0, "warnings": 0}
    for finding in findings:
        if finding.level == "error":
            result["errors"] += 1
        elif finding.level == "warning":
            result["warnings"] += 1
    return result


def _print_text(findings: list[Finding], source: Path) -> None:
    counts = summarize(findings)
    print("Production Deployment Preflight")
    print(f"Environment: {source}")
    if not findings:
        print("PASS: configuration is ready for the selected checks")
        return
    for finding in findings:
        print(f"[{finding.level.upper()}] {finding.code}: {finding.message}")
    print(f"Result: {counts['errors']} error(s), {counts['warnings']} warning(s)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate production deployment settings without revealing secrets.")
    parser.add_argument("--env-file", type=Path, default=Path("deploy/production.env"))
    parser.add_argument("--with-pond", action="store_true", help="Validate Final Pond RS485 settings")
    parser.add_argument("--check-services", action="store_true", help="Call local PCC and Vision health endpoints")
    parser.add_argument("--json", action="store_true", help="Print machine-readable output")
    args = parser.parse_args(argv)

    source = args.env_file.resolve()
    project_root = Path(__file__).resolve().parent.parent
    try:
        env = parse_env(source)
    except (OSError, ValueError) as exc:
        findings = [Finding("error", "env_file", f"Cannot read environment file: {exc}")]
    else:
        findings = validate_config(env, project_root=project_root, with_pond=args.with_pond)
        if args.check_services and not any(item.level == "error" for item in findings):
            findings.extend(check_services(env))

    if args.json:
        print(json.dumps({"ok": not any(item.level == "error" for item in findings), "summary": summarize(findings), "findings": [asdict(item) for item in findings]}, ensure_ascii=False))
    else:
        _print_text(findings, source)
    return 1 if any(item.level == "error" for item in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
