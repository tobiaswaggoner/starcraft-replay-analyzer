from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    replay_dir: str = ""
    db_path: str = "./data/replays.db"
    my_player_names: str = ""
    host: str = "127.0.0.1"
    port: int = 8765

    @property
    def my_names_set(self) -> set[str]:
        return {n.strip() for n in self.my_player_names.split(",") if n.strip()}

    @property
    def db_path_resolved(self) -> Path:
        return Path(self.db_path).resolve()

    @property
    def replay_dir_resolved(self) -> Path | None:
        return Path(self.replay_dir).resolve() if self.replay_dir else None


settings = Settings()
