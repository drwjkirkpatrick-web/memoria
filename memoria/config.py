"""memoria.config — where data lives, how it is laid out."""
from __future__ import annotations
import os
from dataclasses import dataclass

DEFAULT_DATA_DIR = os.path.expanduser("~/memoria-data")
SCHEMA_VERSION = 1

@dataclass
class MemoriaConfig:
    """All filesystem locations derive from one root data dir."""
    data_dir: str = DEFAULT_DATA_DIR
    schema_version: int = SCHEMA_VERSION

    @property
    def executor_key(self) -> str:
        """The executor secret, from the config dir (created on first read)."""
        import os as _os
        path = _os.path.join(self.config_dir, "executor_key")
        if not _os.path.isfile(path):
            import secrets
            self.ensure_dirs()
            with open(path, "w") as f:
                f.write("mem-exec-" + secrets.token_hex(16))
            _os.chmod(path, 0o600)
        with open(path) as f:
            return f.read().strip()

    @property
    def people_dir(self) -> str:
        return os.path.join(self.data_dir, "people")

    @property
    def config_dir(self) -> str:
        return os.path.join(self.data_dir, "config")

    @property
    def exports_dir(self) -> str:
        return os.path.join(self.data_dir, "exports")

    def person_dir(self, person_id: str) -> str:
        return os.path.join(self.people_dir, person_id)

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.people_dir, self.config_dir, self.exports_dir):
            os.makedirs(d, exist_ok=True)

def load_config(env: dict | None = None) -> MemoriaConfig:
    """Config from env (MEMORIA_DATA) or defaults."""
    env = dict(os.environ if env is None else env)
    return MemoriaConfig(data_dir=env.get("MEMORIA_DATA", DEFAULT_DATA_DIR))
