"""Tasks page: manage internal preparation, application, assessment, and follow-up tasks."""

from __future__ import annotations

import streamlit as st

from components.status_badge import format_status_badge_html
from components.system_view import render_sidebar
from components.theme import (
    inject_editorial_theme,
    render_callout,
    render_page_hero,
    render_section_kicker,
)
from components.widgets import confirm_archive_action, pagination_controls, show_api_error
from services.api_client import build_api_client_from_env
from services.time_utils import format_kolkata_timestamp

TASK_TYPES = [
    "TO_APPLY",
    "PREPARING",
    "APPLIED",
    "ASSESSMENT",
    "INTERVIEW_PREP",
    "FOLLOW_UP",
]
TASK_STATUSES = ["PENDING", "IN_PROGRESS", "COMPLETED", "CANCELLED"]


def main() -> None:
    """Render the internal Tasks workflow management page."""
    st.set_page_config(page_title="HydraJob — Tasks", layout="wide")
    inject_editorial_theme()

    with build_api_client_from_env() as client:
        render_sidebar(client.base_url, client.has_api_key)

    render_page_hero(
        kicker="HydraJob · Phase 1 & 3",
        title="Internal Task Queue",
        subtitle="Manage application, assessment, interview preparation, and follow-up tasks directly in PostgreSQL.",
    )

    f1, f2, f3 = st.columns(3)
    type_filter = f1.selectbox("Category", options=["", *TASK_TYPES], key="task_type_filter")
    status_filter = f2.selectbox("Status", options=["", *TASK_STATUSES], key="task_status_filter")
    include_archived = f3.checkbox("Include archived", value=False, key="task_arch_filter")

    with build_api_client_from_env() as client:
        init_tasks = client.list_tasks(
            task_type=type_filter or None,
            status=status_filter or None,
            include_archived=include_archived,
            limit=30,
            offset=0,
        )

    if show_api_error(init_tasks, "Loading Tasks"):
        return

    render_section_kicker(number="01", label="Create", title="Add Internal Task")
    with st.expander("Create New Task", expanded=False), st.form("create_task_form"):
        t_title = st.text_input("Task Title *", placeholder="Prepare tailored ML resume")
        c1, c2 = st.columns(2)
        t_type = c1.selectbox("Task Category", options=TASK_TYPES)
        t_priority = c2.selectbox("Priority", options=["HIGH", "MEDIUM", "LOW"], index=1)
        t_due = st.text_input("Due Date (ISO-8601 UTC or blank)")
        t_desc = st.text_area("Description")
        if st.form_submit_button("Create Task", type="primary"):
            if not t_title.strip():
                st.warning("Task title is required.")
            else:
                with build_api_client_from_env() as client:
                    cr = client.create_task(
                        {
                            "title": t_title.strip(),
                            "task_type": t_type,
                            "priority": t_priority,
                            "due_date": t_due.strip() or None,
                            "description": t_desc.strip() or None,
                        }
                    )
                if not show_api_error(cr, "Create Task"):
                    st.success("Task created.")
                    st.rerun()

    render_section_kicker(
        number="02",
        label="Queue",
        title=f"Active & Historical Tasks ({init_tasks.total})",
    )
    limit, offset = pagination_controls("tasks", init_tasks.total, default_limit=30)
    if offset > 0 or limit != 30:
        with build_api_client_from_env() as client:
            tasks_res = client.list_tasks(
                task_type=type_filter or None,
                status=status_filter or None,
                include_archived=include_archived,
                limit=limit,
                offset=offset,
            )
    else:
        tasks_res = init_tasks

    tasks = tasks_res.items
    if not tasks:
        render_callout("No Tasks Found", "Create a task above or evaluate eligible jobs to generate tasks.", tone="info")
        return

    for task in tasks:
        tid = str(task.get("id"))
        t_status = str(task.get("status") or "PENDING")
        badge = format_status_badge_html(t_status, label_override=t_status)
        with st.expander(
            f"{task.get('title')} · [{task.get('task_type', 'GENERAL')}] · {t_status}",
            expanded=False,
        ):
            st.markdown(
                f"{badge} · **Priority:** `{task.get('priority', 'MEDIUM')}` · "
                f"**Due:** `{format_kolkata_timestamp(task.get('due_date'))}`",
                unsafe_allow_html=True,
            )
            if task.get("description"):
                st.write(task.get("description"))

            c_stat, c_btn, c_arch = st.columns([2, 1, 1.5])
            new_status = c_stat.selectbox(
                "Status",
                options=TASK_STATUSES,
                index=TASK_STATUSES.index(t_status) if t_status in TASK_STATUSES else 0,
                key=f"sel_task_status_{tid}",
            )
            if c_btn.button("Update Status", key=f"upd_task_{tid}", type="primary"):
                with build_api_client_from_env() as client:
                    upd = client.update_task_status(tid, new_status)
                if not show_api_error(upd, "Update Task Status"):
                    st.success("Task updated.")
                    st.rerun()
            with c_arch:
                if confirm_archive_action(f"arch_task_{tid}", "Archive", f"'{task.get('title')}'"):
                    with build_api_client_from_env() as client:
                        arch = client.archive_task(tid)
                    if not show_api_error(arch, "Archive Task"):
                        st.success("Task archived.")
                        st.rerun()


if __name__ == "__main__":
    main()
