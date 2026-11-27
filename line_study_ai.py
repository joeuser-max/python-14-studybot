"""At scheduled study start, enrich LINE reminder with an existing or new AI note.

Adapted from joeuser-max main commit 1ef63c8e reminder_worker._study_session_message.
Only runs with explicit ai_after_class_enabled; failures do not block the reminder.
"""
from __future__ import annotations

from ai_assistant import AIError, organize_class_feedback
from storage import DataError, update_feedback_analysis


def study_start_message(task: dict, user: dict, feedbacks: list[dict]) -> str:
    subject = task.get("subject") or "未指定科目"
    title = task.get("title") or task.get("task_id","")
    baseline = f"讀書時段開始囉！任務：科目「{subject}」，{title}，請開始完成。"
    feedback_id = task.get("source_feedback_id")
    if user.get("ai_after_class_enabled") is not True or not feedback_id:
        return baseline
    feedback = next(
        (note for note in feedbacks
         if note.get("feedback_id") == feedback_id
         and note.get("user_id") == task.get("user_id")),
        None,
    )
    if feedback is None:
        return baseline + "\n找不到關聯的課後筆記，請從 ClassPulse 筆記庫查看。"
    analysis = feedback.get("ai_analysis")
    if not isinstance(analysis,dict):
        try:
            analysis = organize_class_feedback(feedback,subject)
            update_feedback_analysis(feedback_id,task["user_id"],analysis)
        except (AIError,DataError,KeyError,ValueError) as exc:
            return baseline + f"\nAI 筆記整理未完成：{exc}。原始筆記仍在筆記庫。"
    lines=[baseline,"AI 根據筆記整理的複習內容：",
           "摘要："+str(analysis.get("summary") or "尚無摘要")]
    if analysis.get("key_points"):
        lines.append("重點："+"；".join(str(x) for x in analysis["key_points"][:5]))
    if analysis.get("unresolved_questions"):
        lines.append("待釐清："+"；".join(str(x) for x in analysis["unresolved_questions"][:4]))
    if analysis.get("topic_tags"):
        lines.append("主題："+"、".join(str(x) for x in analysis["topic_tags"][:5]))
    if analysis.get("suggested_task"):
        lines.append("AI 複習建議："+str(analysis["suggested_task"])[:180])
    return "\n".join(lines)[:4800]
