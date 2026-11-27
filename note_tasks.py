"""ClassPulse note → question → review task, with source-level traceability.

A question mark or explicit 疑問 marker creates one candidate for each distinct
question. Candidates are NOT tasks: only an explicit human confirmation writes
to tasks.json. Unknown LINE inbox course must be classified before confirming.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, time
import hashlib
import re

from storage import DataError, TZ, data_path, load_json, update_json, validate_task

DEFAULT_REVIEW_MINUTES = 30
MAX_QUESTIONS_PER_NOTE = 32


def _normalized(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def _question_segments(text: str) -> list[str]:
    """Split multiple ？/?, keeping one independent action per question."""
    found = []
    for raw in text.replace("\r", "\n").split("\n"):
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)、]|Q\d*[:：])\s*", "", raw).strip()
        if not line:
            continue
        pieces = re.findall(r"[^？?]+[？?]", line)
        for part in pieces:
            value = part.strip(" ，。、：:;；\t")
            if 2 <= len(value) <= 500:
                found.append(value)
    return found


def extract_questions(note: dict) -> list[str]:
    analysis = note.get("ai_analysis")
    explicit = []
    if isinstance(analysis, dict):
        qs = analysis.get("unresolved_questions")
        if isinstance(qs, list):
            explicit = [s.strip() for s in qs if isinstance(s, str) and s.strip()]
    content = note.get("content")
    text = content if isinstance(content, str) else ""
    candidates = explicit + _question_segments(text)
    tags = note.get("topic_tags")
    if not isinstance(tags, list):
        tags = []
    marked = any("疑問" in str(tag) or "question" in str(tag).casefold() for tag in tags)
    if (note.get("is_question") is True or marked) and not candidates:
        # Explicit question note without punctuation: each non-empty line is a question.
        candidates = [
            re.sub(r"^\s*(?:[-*•]|\d+[.)、])\s*", "", line).strip()
            for line in text.splitlines() if len(line.strip()) >= 2
        ]
    unique, seen = [], set()
    for q in candidates:
        key = _normalized(q.rstrip("？?"))
        if key and key not in seen:
            seen.add(key)
            unique.append(q)
    return unique[:MAX_QUESTIONS_PER_NOTE]


def question_key(feedback_id: str, question: str) -> str:
    normalized = _normalized(question.rstrip("？?"))
    return hashlib.sha256((feedback_id + "\0" + normalized).encode("utf-8")).hexdigest()[:24]


def next_class_start(course: dict, now: datetime) -> datetime:
    """Earliest weekly occurrence strictly after now; minute-accurate."""
    current = now.astimezone(TZ) if now.tzinfo else now.replace(tzinfo=TZ)
    weekday = int(course["weekday"])
    start_time = time.fromisoformat(course["start_time"])
    days_until = (weekday - current.isoweekday()) % 7
    upcoming = datetime.combine(current.date()+timedelta(days=days_until),start_time,tzinfo=TZ)
    if upcoming <= current:
        upcoming += timedelta(days=7)
    return upcoming


def candidate_tasks(notes: list[dict], courses: list[dict],
                    tasks: list[dict], user_id: str,
                    now: datetime | None = None) -> list[dict]:
    now = (now or datetime.now(TZ)).astimezone(TZ)
    own_courses = {e["event_id"]: e for e in courses if e.get("user_id") == user_id}
    existing = {(t.get("source_feedback_id"), t.get("source_question_key"))
                for t in tasks if t.get("user_id") == user_id and t.get("source_question_key")}
    out = []
    for note in notes:
        if note.get("user_id") != user_id or not note.get("feedback_id"):
            continue
        course = own_courses.get(note.get("event_id"))
        for question in extract_questions(note):
            qkey = question_key(note["feedback_id"], question)
            if (note["feedback_id"], qkey) in existing:
                continue
            due = next_class_start(course, now) if course else None
            out.append({
                "source_feedback_id": note["feedback_id"],
                "source_question_key": qkey,
                "source_event_id": course["event_id"] if course else "",
                "question": question,
                "suggested_task": "釐清並練習：" + question.rstrip("？?"),
                "subject": course["title"] if course else "",
                "source_class_date": note.get("class_date", ""),
                "estimated_minutes": DEFAULT_REVIEW_MINUTES,
                "deadline_at": due.isoformat(timespec="minutes") if due else "",
                "deadline": due.date().isoformat() if due else "",
                "needs_classification": course is None,
            })
    return out


def confirm_question_task(user_id: str, candidate: dict,
                          now: datetime | None = None,
                          title: str | None = None) -> dict:
    """Idempotent confirmation per (user, feedback, question); never schedules."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    feedback_id = str(candidate.get("source_feedback_id") or "")
    question = str(candidate.get("question") or "")
    expected_key = question_key(feedback_id, question)
    if not feedback_id or not question or candidate.get("source_question_key") != expected_key:
        raise DataError("疑問來源與識別碼不正確")
    notes = load_json(data_path("feedback"))
    note = next((n for n in notes if n.get("user_id")==user_id
                 and n.get("feedback_id")==feedback_id),None)
    if note is None or question not in extract_questions(note):
        raise DataError("疑問已不存在於來源筆記，請重新整理")
    courses = load_json(data_path("events"))
    course = next((e for e in courses if e.get("user_id")==user_id
                   and e.get("event_id")==note.get("event_id")),None)
    if course is None:
        raise DataError("未分類筆記：請先將來源關聯至課程再建立有下次課程期限的任務")
    deadline = next_class_start(course,now)
    label = (title or candidate.get("suggested_task") or "").strip()
    if not label:
        raise DataError("建議的複習內容不可空白")
    task = {
        "task_id": "aiq_"+expected_key, "user_id":user_id,
        "subject":course["title"], "title":label[:300],
        "deadline":deadline.date().isoformat(),
        "deadline_at":deadline.isoformat(timespec="minutes"),
        "estimated_minutes":DEFAULT_REVIEW_MINUTES,
        "status":"pending", "preferred_availability_id":"",
        "source":"ai_confirmed",
        "suggestion_method":candidate.get("suggestion_method","question_rule"),
        "source_feedback_id":feedback_id,
        "source_question_key":expected_key, "source_question":question,
        "source_event_id":course["event_id"],
        "source_class_date":note.get("class_date",""),
    }
    validate_task(task)
    def save(rows: list) -> list:
        if any(t.get("user_id")==user_id and
               t.get("source_feedback_id")==feedback_id and
               t.get("source_question_key")==expected_key for t in rows):
            raise DataError("這項疑問已新增過任務，請勿重複建立")
        if any(t.get("task_id")==task["task_id"] for t in rows):
            raise DataError("任務 ID 已存在")
        return rows + [task]
    update_json(data_path("tasks"),save)
    return task


def assign_note_course(user_id: str, feedback_id: str, event_id: str) -> None:
    """Explicit reclassification from LINE Inbox to a source course."""
    events=load_json(data_path("events"))
    if not any(e.get("event_id")==event_id and e.get("user_id")==user_id
               for e in events):
        raise DataError("指定的來源課程不存在")
    def save(rows: list) -> list:
        if not any(row.get("feedback_id")==feedback_id
                   and row.get("user_id")==user_id for row in rows):
            raise DataError("找不到指定的筆記")
        return [
            {**row,"event_id":event_id}
            if row.get("feedback_id")==feedback_id and row.get("user_id")==user_id
            else row for row in rows
        ]
    update_json(data_path("feedback"),save)
