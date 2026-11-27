"""V2 筆記庫的 PDF 原檔存放，沿用組員以使用者+回饋 ID 雜湊的隔離邏輯。

目前只保存 PDF 原檔；DOCX/TXT 保留擷取文字與原檔名。資料不進 Git。
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from filelock import FileLock, Timeout

from storage import DataError, data_path

MAX_PDF_BYTES=10*1024*1024


def attachment_path(user_id: str, feedback_id: str) -> Path:
    if not user_id or not feedback_id or not isinstance(user_id,str) or not isinstance(feedback_id,str):
        raise DataError("使用者與筆記 ID 不可空白")
    key=hashlib.sha256((user_id+"\0"+feedback_id).encode("utf-8")).hexdigest()
    return data_path("feedback").parent/"attachments"/(key+".pdf")


def save_pdf_attachment(user_id: str, feedback_id: str, content: bytes) -> Path:
    if not isinstance(content,bytes) or not 0<len(content)<=MAX_PDF_BYTES:
        raise DataError("PDF 原檔大小需在 1 byte–10 MB")
    if not content.lstrip().startswith(b"%PDF-"):
        raise DataError("PDF 附件格式錯誤")
    path=attachment_path(user_id,feedback_id)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=None
    try:
        with FileLock(str(path)+".lock",timeout=8):
            fd,temp=tempfile.mkstemp(prefix=".pending-",suffix=".tmp",dir=path.parent)
            with os.fdopen(fd,"wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp,path)
            temp=None
    except (Timeout,OSError) as exc:
        raise DataError("PDF 原檔寫入失敗") from exc
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)
    return path


def delete_pdf_attachment(user_id: str, feedback_id: str) -> None:
    path=attachment_path(user_id,feedback_id)
    if not path.parent.exists():
        return
    try:
        with FileLock(str(path)+".lock",timeout=8):
            path.unlink(missing_ok=True)
    except (Timeout,OSError) as exc:
        raise DataError("PDF 原檔刪除失敗") from exc
