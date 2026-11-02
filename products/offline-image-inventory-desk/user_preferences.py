"""Per-user, offline JA/EN preference. No project files or network access."""
import json
import os
from pathlib import Path
import tempfile

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = frozenset(("en", "ja"))
MAX_CONFIG_BYTES = 4096


def preference_path():
    """Use a user-specific directory, never the source tree or EXE directory."""
    override = os.environ.get("OFFLINE_IMAGE_INVENTORY_CONFIG_DIR")
    if override:
        directory = Path(override)
    elif os.name == "nt":
        directory = Path(os.environ.get("LOCALAPPDATA") or
                         (Path.home() / "AppData" / "Local")) / "OfflineImageInventoryDesk"
    else:
        directory = Path(os.environ.get("XDG_CONFIG_HOME") or
                         (Path.home() / ".config")) / "offline-image-inventory-desk"
    return directory / "preferences.json"


def load_language():
    """Corrupt, oversized, missing, or linked settings safely fall back to EN."""
    path = preference_path()
    try:
        if path.is_symlink() or path.stat().st_size > MAX_CONFIG_BYTES:
            return DEFAULT_LANGUAGE
        value = json.loads(path.read_text(encoding="utf-8"))
        if (type(value) is dict and type(value.get("version")) is int
                and value["version"] == 1
                and type(value.get("language")) is str
                and value["language"] in SUPPORTED_LANGUAGES):
            return value["language"]
    except (OSError, UnicodeError, ValueError, TypeError):
        pass
    return DEFAULT_LANGUAGE


def save_language(language):
    """Atomic replacement: failed writes never truncate the previous preference."""
    if type(language) is not str or language not in SUPPORTED_LANGUAGES:
        raise ValueError("Unsupported language")
    path = preference_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OSError("Refusing linked preferences")
    pending = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=str(path.parent),
                prefix=".preferences-", suffix=".tmp", delete=False) as stream:
            pending = Path(stream.name)
            json.dump({"version": 1, "language": language}, stream,
                      ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        if pending is not None:
            try:
                pending.unlink(missing_ok=True)
            except OSError:
                pass
