from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
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

    brother_enabled: bool = Field(default=True, alias="BROTHER_ENABLED")
    brother_model: str = Field(default="QL-820NWB", alias="BROTHER_MODEL")
    brother_printer_uri: str = Field(default="tcp://10.206.58.111:9100", alias="BROTHER_PRINTER_URI")
    brother_label_size: str = Field(default="62x100", alias="BROTHER_LABEL_SIZE")
    brother_cut: bool = Field(default=True, alias="BROTHER_CUT")
    show_price_on_label: bool = Field(default=True, alias="SHOW_PRICE_ON_LABEL")
    filament_price_per_gram: float = Field(default=0.10, alias="FILAMENT_PRICE_PER_GRAM")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
