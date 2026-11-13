from functools import lru_cache

from pydantic import AliasChoices, AnyHttpUrl, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    host: str = Field(default="0.0.0.0", alias="PRINTERPRINTER_HOST")
    port: int = Field(default=8080, alias="PRINTERPRINTER_PORT")
    log_level: str = Field(default="INFO", alias="PRINTERPRINTER_LOG_LEVEL")
    db_path: str = Field(default="./data/printerprinter.sqlite3", alias="PRINTERPRINTER_DB_PATH")

    bambuddy_base_url: AnyHttpUrl = Field(alias="BAMBUDDY_BASE_URL")
    bambuddy_api_token: str = Field(alias="BAMBUDDY_API_TOKEN")
    bambuddy_timeout_seconds: float = Field(default=15.0, alias="BAMBUDDY_TIMEOUT_SECONDS")
    bambuddy_auth_mode: str = Field(default="bearer", alias="BAMBUDDY_AUTH_MODE")
    bambuddy_auth_header_name: str = Field(default="X-API-Key", alias="BAMBUDDY_AUTH_HEADER_NAME")
    bambuddy_jobs_endpoint: str = Field(default="/api/v1/print-log/", alias="BAMBUDDY_JOBS_ENDPOINT")
    bambuddy_printers_endpoint: str = Field(default="/api/v1/printers/", alias="BAMBUDDY_PRINTERS_ENDPOINT")
    printer_status_endpoint_template: str = Field(
        default="/api/v1/printers/{printer_id}/status",
        alias="BAMBUDDY_PRINTER_STATUS_ENDPOINT_TEMPLATE",
    )
    monitored_printer_ids: str = Field(default="", alias="PRINTERPRINTER_MONITORED_PRINTER_IDS")
    monitored_printer_identifiers: str = Field(
        default="",
        alias="PRINTERPRINTER_MONITORED_PRINTER_IDENTIFIERS",
    )
    poll_interval_seconds: float = Field(default=5.0, alias="PRINTERPRINTER_POLL_INTERVAL_SECONDS")
    label_wait_seconds: float = Field(default=60.0, alias="PRINTERPRINTER_LABEL_WAIT_SECONDS")
    label_wait_poll_seconds: float = Field(default=5.0, alias="PRINTERPRINTER_LABEL_WAIT_POLL_SECONDS")
    pending_label_max_age_seconds: float = Field(
        default=900.0,
        alias="PRINTERPRINTER_PENDING_LABEL_MAX_AGE_SECONDS",
    )
    env_file_path: str = Field(default=".env", alias="PRINTERPRINTER_ENV_FILE_PATH")
    service_name: str = Field(default="printerprinter", alias="PRINTERPRINTER_SERVICE_NAME")
    install_dir: str = Field(default="/opt/printerprinter", alias="PRINTERPRINTER_INSTALL_DIR")
    update_branch: str = Field(default="main", alias="PRINTERPRINTER_UPDATE_BRANCH")
    venv_path: str = Field(default="/opt/printerprinter/venv", alias="PRINTERPRINTER_VENV_PATH")

    # Generic label printer backend selection (backward-compatible with BROTHER_* / DYMO_* aliases)
    printer_backend: str = Field(default="brother", alias="PRINTER_BACKEND")
    printer_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("PRINTER_ENABLED", "BROTHER_ENABLED"),
    )
    printer_interface: str = Field(
        default="usb",
        validation_alias=AliasChoices("PRINTER_INTERFACE", "DYMO_INTERFACE"),
    )
    label_size: str = Field(
        default="",
        validation_alias=AliasChoices("PRINTER_LABEL_SIZE", "DYMO_LABEL_SIZE", "BROTHER_LABEL_SIZE"),
    )

    # Brother settings
    brother_model: str = Field(default="QL-820NWB", alias="BROTHER_MODEL")
    brother_printer_uri: str = Field(default="tcp://10.206.58.111:9100", alias="BROTHER_PRINTER_URI")
    brother_cut: bool = Field(default=True, alias="BROTHER_CUT")

    # Dymo settings (Linux / Raspberry Pi via CUPS + printer-driver-dymo)
    dymo_model: str = Field(default="LabelWriter-400-Turbo", alias="DYMO_MODEL")
    dymo_usb_queue_name: str = Field(default="", alias="DYMO_USB_QUEUE_NAME")
    dymo_wifi_queue_name: str = Field(default="", alias="DYMO_WIFI_QUEUE_NAME")
    dymo_print_quality: str = Field(default="Graphics", alias="DYMO_PRINT_QUALITY")
    dymo_print_density: str = Field(default="Normal", alias="DYMO_PRINT_DENSITY")
    dymo_job_expire_seconds: int = Field(default=300, alias="DYMO_JOB_EXPIRE_SECONDS")

    # Pricing / label content settings
    show_price_on_label: bool = Field(default=True, alias="SHOW_PRICE_ON_LABEL")
    filament_price_per_gram: float = Field(default=0.10, alias="FILAMENT_PRICE_PER_GRAM")

    @model_validator(mode="after")
    def _normalize_printer_defaults(self) -> "Settings":
        self.printer_backend = self.printer_backend.strip().lower() or "brother"
        self.printer_interface = self.printer_interface.strip().lower() or "usb"
        self.label_size = self.label_size.strip()
        if not self.label_size:
            self.label_size = "30336" if self.printer_backend == "dymo" else "62x100"
        return self

    @property
    def brother_enabled(self) -> bool:
        return self.printer_enabled

    @property
    def brother_label_size(self) -> str:
        return self.label_size


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
