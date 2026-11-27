"""LINE 文件型課後筆記：擷取 .txt / 文字型 .pdf / .docx。

移植並收斂自 joeuser-max main commit 1ef63c8e（檔案下載、大小限制、
PDF 與 DOCX 文字擷取）。此模組不含組員的 Streamlit UI 或時段勾選。
掃描 PDF 無文字時明確回報，不假裝已使用 OCR/視覺 AI。
"""
from __future__ import annotations

from io import BytesIO
import os
import re
from urllib.parse import quote
import xml.etree.ElementTree as ET
import zipfile

import requests
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from storage import DataError

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_EXPANDED_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 50_000
LINE_CONTENT_URL = "https://api-data.line.me/v2/bot/message/{}/content"
EXTENSIONS = {"txt", "pdf", "docx"}


def clean_filename(raw: str) -> str:
    if not isinstance(raw, str):
        raise DataError("LINE 檔名格式不合法")
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", raw)
    cleaned = cleaned.replace("\\", "/").rsplit("/", 1)[-1].strip()[:255]
    if cleaned.rpartition(".")[2].lower() not in EXTENSIONS:
        raise DataError("僅支援 TXT、文字型 PDF 與 DOCX；ICS 請從網頁行事曆匯入")
    return cleaned


def download_line_file(message_id: str, file_size: object) -> bytes:
    if not isinstance(message_id, str) or not message_id:
        raise DataError("LINE 檔案缺少訊息 ID")
    if type(file_size) is int and file_size > MAX_FILE_BYTES:
        raise DataError("檔案超過 10 MB")
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token:
        raise DataError("尚未設定 LINE_CHANNEL_ACCESS_TOKEN")
    chunks, total = [], 0
    with requests.get(
        LINE_CONTENT_URL.format(quote(message_id, safe="")),
        headers={"Authorization": f"Bearer {token}"},
        stream=True, timeout=(5,20),
    ) as response:
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise DataError("檔案超過 10 MB")
            chunks.append(chunk)
    if not chunks:
        raise DataError("檔案為空")
    return b"".join(chunks)


def extract_text(filename: str, content: bytes) -> str:
    filename = clean_filename(filename)
    if not isinstance(content, bytes) or not content or len(content) > MAX_FILE_BYTES:
        raise DataError("筆記檔必須在 1 byte 至 10 MB 之間")
    ext = filename.rsplit(".",1)[-1].lower()
    if ext == "txt":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DataError("TXT 筆記請使用 UTF-8 編碼") from exc
    elif ext == "pdf":
        try:
            reader = PdfReader(BytesIO(content), strict=False)
            if reader.is_encrypted:
                raise DataError("目前不支援加密 PDF")
            pieces = []
            count = 0
            for page in reader.pages:
                part = page.extract_text() or ""
                count += len(part)
                if count > MAX_TEXT_CHARS:
                    raise DataError("筆記超過 50,000 字")
                pieces.append(part)
            text = "\n".join(pieces)
        except (PdfReadError, ValueError, OSError) as exc:
            if isinstance(exc, DataError):
                raise
            raise DataError("PDF 無法解析，請確認檔案完整且含可擷取文字") from exc
    else:
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                entries = archive.infolist()
                if sum(info.file_size for info in entries) > MAX_EXPANDED_BYTES:
                    raise DataError("DOCX 解壓後超過 20 MB")
                document = archive.getinfo("word/document.xml")
                if document.file_size > MAX_EXPANDED_BYTES:
                    raise DataError("DOCX 文字超過大小上限")
                with archive.open(document) as f:
                    xml = f.read(MAX_EXPANDED_BYTES + 1)
                if len(xml) > MAX_EXPANDED_BYTES:
                    raise DataError("DOCX 文字超過大小上限")
                if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
                    raise DataError("DOCX 不能包含 DTD 或外部實體")
                root = ET.fromstring(xml)
        except (KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
            raise DataError("DOCX 檔案損毀或格式不支援") from exc
        ns="{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paragraphs = []
        for paragraph in root.iter(f"{ns}p"):
            value="".join(n.text or "" for n in paragraph.iter(f"{ns}t"))
            if value:
                paragraphs.append(value)
        text = "\n".join(paragraphs)
    result = text.strip()
    if len(result) < 2:
        raise DataError("找不到可擷取文字；掃描 PDF 暫不支援 OCR，請傳文字型 PDF 或 TXT")
    if len(result) > MAX_TEXT_CHARS:
        raise DataError("筆記超過 50,000 字，請拆分檔案")
    return result
