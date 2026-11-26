from plan_bridge import merge_user_plan


def test_merge_user_plan_preserves_other_users_and_alert_delivery_state():
    rows = [
        {
            "user_id": "user-1",
            "task_id": "task-1",
            "status": "unscheduled",
            "unscheduled_alert_id": "alert-1",
            "unscheduled_alerted": True,
        },
        {"user_id": "user-2", "task_id": "other-task", "status": "scheduled"},
    ]
    new_plan = [{
        "task_id": "task-1",
        "status": "unscheduled",
        "unscheduled_alert_id": "alert-1",
        "unscheduled_alerted": False,
    }]

    merged = merge_user_plan(rows, "user-1", new_plan)

    assert merged == [
        {"user_id": "user-2", "task_id": "other-task", "status": "scheduled"},
        {
            **new_plan[0],
            "user_id": "user-1",
            "unscheduled_alerted": True,
        },
    ]
    assert new_plan[0]["unscheduled_alerted"] is False
