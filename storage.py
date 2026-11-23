import json
import os
import tempfile
from pathlib import Path
from typing import Any


class StorageError(Exception):
    pass


def load_json(path: str | os.PathLike[str]) -> list[Any]:
    file_path = Path(path)
    if not file_path.exists():
        return []

    try:
        with file_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise StorageError(f"{file_path} 的 JSON 格式錯誤：{exc}") from exc
    except OSError as exc:
        raise StorageError(f"無法讀取 {file_path}：{exc}") from exc

    if not isinstance(data, list):
        raise StorageError(f"{file_path} 必須是 JSON 陣列")
    return data


def save_json(path: str | os.PathLike[str], data: list[dict[str, Any]]) -> None:
    file_path = Path(path)
    if not isinstance(data, list):
        raise StorageError("儲存資料必須是 list")

    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: str | None = None
    try:
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{file_path.name}.", suffix=".tmp", dir=file_path.parent
        )
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, file_path)
    except OSError as exc:
        raise StorageError(f"無法安全寫入 {file_path}：{exc}") from exc
    finally:
        if temp_path:
            temp_file = Path(temp_path)
            if temp_file.exists():
                temp_file.unlink()
