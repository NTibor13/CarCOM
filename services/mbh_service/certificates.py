from dataclasses import dataclass
from pathlib import Path

from shared.config.settings import settings


@dataclass(frozen=True)
class MbhCertificateConfig:
    environment: str

    sandbox_private_key_path: str
    sandbox_public_key_path: str

    qwac_cert_path: str | None
    qwac_key_path: str | None

    qseal_cert_path: str | None
    qseal_key_path: str | None

    signing_issuer: str


def get_mbh_certificate_config() -> MbhCertificateConfig:
    return MbhCertificateConfig(
        environment=settings.mbh_environment,
        sandbox_private_key_path=settings.mbh_private_key_path,
        sandbox_public_key_path=settings.mbh_public_key_path,
        qwac_cert_path=settings.mbh_qwac_cert_path or None,
        qwac_key_path=settings.mbh_qwac_key_path or None,
        qseal_cert_path=settings.mbh_qseal_cert_path or None,
        qseal_key_path=settings.mbh_qseal_key_path or None,
        signing_issuer=settings.mbh_signing_issuer,
    )


def _read_text_file(path: str, *, label: str) -> str:
    if not path:
        raise RuntimeError(f"Missing MBH {label} path configuration.")

    file_path = Path(path)

    if not file_path.exists():
        raise RuntimeError(f"Configured MBH {label} file does not exist: {path}")

    return file_path.read_text(encoding="utf-8")


def load_mbh_signing_private_key_pem() -> str:
    config = get_mbh_certificate_config()

    if config.environment in ("production", "certificate_simulation"):
        return _read_text_file(
            config.qseal_key_path or "",
            label="QSEAL private key",
        )

    return _read_text_file(
        config.sandbox_private_key_path,
        label="sandbox private key",
    )


def load_mbh_signing_public_key_pem() -> str:
    config = get_mbh_certificate_config()

    if config.environment in ("production", "certificate_simulation"):
        return _read_text_file(
            config.qseal_cert_path or "",
            label="QSEAL certificate",
        )

    return _read_text_file(
        config.sandbox_public_key_path,
        label="sandbox public key",
    )


def get_mbh_signing_issuer() -> str:
    return get_mbh_certificate_config().signing_issuer


def get_mbh_mtls_cert() -> tuple[str, str] | None:
    config = get_mbh_certificate_config()

    if config.environment == "certificate_simulation":
        if not config.qwac_cert_path or not config.qwac_key_path:
            raise RuntimeError(
                "MBH certificate_simulation mode requires QWAC certificate and private key paths."
            )

        # Simulation mode validates that QWAC config exists,
        # but does not attach it to sandbox HTTP requests.
        return None

    if config.environment != "production":
        return None

    if not config.qwac_cert_path or not config.qwac_key_path:
        raise RuntimeError(
            "MBH production mode requires QWAC certificate and private key paths."
        )

    return config.qwac_cert_path, config.qwac_key_path

def validate_mbh_certificate_configuration() -> dict:
    config = get_mbh_certificate_config()

    result = {
        "environment": config.environment,
        "qseal_key_loaded": False,
        "qseal_cert_loaded": False,
        "qwac_cert_configured": False,
        "qwac_key_configured": False,
        "mtls_enabled": False,
    }

    if config.environment in ("production", "certificate_simulation"):
        _read_text_file(config.qseal_key_path or "", label="QSEAL private key")
        _read_text_file(config.qseal_cert_path or "", label="QSEAL certificate")
        result["qseal_key_loaded"] = True
        result["qseal_cert_loaded"] = True

        _read_text_file(config.qwac_cert_path or "", label="QWAC certificate")
        _read_text_file(config.qwac_key_path or "", label="QWAC private key")
        result["qwac_cert_configured"] = True
        result["qwac_key_configured"] = True

        result["mtls_enabled"] = config.environment == "production"

    else:
        _read_text_file(config.sandbox_private_key_path, label="sandbox private key")
        _read_text_file(config.sandbox_public_key_path, label="sandbox public key")

    return result