import pytest
from pathlib import Path
from eyeamme.config import Settings


def test_settings_from_environment_var(monkeypatch):
    monkeypatch.setenv("R2_ACCOUNT_ID", "8372c198a6857d1a119ee13add9dfb5b")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "28192e5f84464b5302da77bac2a88685")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "d6ff8952545360a7481626b03fa49aa9d0fd76c761875e4572ed40316be92765")
    monkeypatch.setenv("R2_BUCKET_NAME", "eyeamme")
    monkeypatch.setenv("R2_ENDPOINT_URL", "https://8372c198a6857d1a119ee13add9dfb5b.r2.cloudflarestorage.com")

    monkeypatch.setenv("SECRET_KEY", "cfb7cbef358e6fdfa37a1b5bbdc0df51d6fcd32d518b93de4000186507361f96")

    monkeypatch.setenv("ENCRYPTION_KEY", "Hj6vCNVu39O4RJtHhQ61eMTgMc-M3UOYVKlGJoo_biM=")

    monkeypatch.setenv("DATA_RETENTION_DAYS", "60")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")

    monkeypatch.setenv("LOG_LEVEL", "INFO")

    Settings()


def test_settings_from_environment_file(tmp_path: Path):
    temp_dotenv_file = tmp_path.joinpath(".env.tmp")
    temp_dotenv_file.write_text("""
R2_ACCOUNT_ID=8372c198a6857d1a119ee13add9dfb5b
R2_ACCESS_KEY_ID=28192e5f84464b5302da77bac2a88685
R2_SECRET_ACCESS_KEY=d6ff8952545360a7481626b03fa49aa9d0fd76c761875e4572ed40316be92765
R2_BUCKET_NAME=eyeamme
R2_ENDPOINT_URL=https://8372c198a6857d1a119ee13add9dfb5b.r2.cloudflarestorage.com

SECRET_KEY=cfb7cbef358e6fdfa37a1b5bbdc0df51d6fcd32d518b93de4000186507361f96

ENCRYPTION_KEY=Hj6vCNVu39O4RJtHhQ61eMTgMc-M3UOYVKlGJoo_biM=

DATA_RETENTION_DAYS=60
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

LOG_LEVEL=INFO

    """)
    Settings(_env_file=temp_dotenv_file)

def test_settings_from_environment_missing_var(tmp_path: Path):
    with pytest.raises(ValueError):

        temp_dotenv_file = tmp_path.joinpath(".env.tmp")
        temp_dotenv_file.write_text("""
R2_ACCESS_KEY_ID=28192e5f84464b5302da77bac2a88685
R2_SECRET_ACCESS_KEY=d6ff8952545360a7481626b03fa49aa9d0fd76c761875e4572ed40316be92765
R2_BUCKET_NAME=eyeamme
R2_ENDPOINT_URL=https://8372c198a6857d1a119ee13add9dfb5b.r2.cloudflarestorage.com

SECRET_KEY=cfb7cbef358e6fdfa37a1b5bbdc0df51d6fcd32d518b93de4000186507361f96

ENCRYPTION_KEY=Hj6vCNVu39O4RJtHhQ61eMTgMc-M3UOYVKlGJoo_biM=

DATA_RETENTION_DAYS=60

LOG_LEVEL=INFO

        """)
        Settings(_env_file=temp_dotenv_file)
