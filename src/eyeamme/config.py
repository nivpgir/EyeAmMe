from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Security
    secret_key: str
    algorithm: str = "hs256"
    access_token_expire_minutes: int = 30

    # Data retention
    data_retention_days: int = 60

    # Cloudflare R2
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket_name: str
    r2_endpoint_url: str

    # encryption
    encryption_key: str

    # cors
    allowed_origins: str = "http://localhost:3000"

    log_level: str | int = "INFO"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    class Config:
        case_sensitive = False
        env_file = ".env"
        extra = 'ignore'
