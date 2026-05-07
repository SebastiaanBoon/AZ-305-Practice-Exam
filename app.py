import os
from typing import Any, Dict, List, Tuple

import streamlit as st

from db import ExamDB
from exam_parser import evaluate_answer, parse_docx_questions


APP_TITLE = "DP-700 Practice Exam Trainer"
DEFAULT_DOCX = "dp700_final.docx"


def _safe_index(options: List[str], value: str) -> int:
    try:
        return options.index(value)
    except ValueError:
        return 0


def load_questions_if_needed(db: ExamDB, docx_path: str) -> Tuple[bool, str]:
    if db.has_questions():
        return True, "Questions already loaded from database."

    if not os.path.exists(docx_path):
        return False, f"DOCX file not found: {docx_path}"

    questions = parse_docx_questions(docx_path)
    if not questions:
        return False, "No questions parsed from DOCX."

    db.upsert_questions(questions)
    return True, f"Loaded {len(questions)} questions from {docx_path}."


def get_status_icon(answer_row: Dict[str, Any]) -> str:
    if not answer_row:
        return "○"
    payload = answer_row.get("answer") or {}
    has_value = any(bool(v) for v in payload.values())
    if not has_value:
        return "○"
    if answer_row.get("is_checked"):
        return "✅" if answer_row.get("is_correct") else "❌"
    return "◐"


def render_question_display(question: Dict[str, Any]) -> None:
    """Display question text with proper formatting."""
    st.markdown(f"### {question['qcode']} — {question.get('topic', '')}")
    
    qtext = question.get("question_text", "")
    
    # Split on code blocks or placeholders for better readability
    lines = qtext.split("\n")
    for line in lines:
        if line.strip():
            if "[Dropdown" in line or "[Blank" in line:
                st.markdown(f"**{line}**")
            elif line.startswith("SELECT") or line.startswith("WITH") or line.startswith("CREATE") or line.startswith("INSERT"):
                st.code(line, language="sql")
            else:
                st.markdown(line)


def render_answer_editor(question: Dict[str, Any], existing_answer: Dict[str, Any], key_prefix: str) -> Dict[str, Any]:
    payload = existing_answer.get("answer", {}) if existing_answer else {}

    options = question.get("options", [])
    dropdown_groups = question.get("dropdown_groups", {})
    statements = question.get("statements", [])
    available_values = question.get("available_values", [])
    qtype = question.get("qtype", "UNKNOWN")

    out: Dict[str, Any] = {}

    # === HOTSPOT / DROPDOWN questions ===
    if dropdown_groups and not statements:
        st.markdown("**Select an option for each dropdown:**")
        item_answers = payload.get("item_answers", {})
        for idx, (label, choices) in enumerate(dropdown_groups.items(), start=1):
            # Clean label (e.g., "Dropdown 1 — JOIN type..." → "Dropdown 1: JOIN type...")
            clean_label = label.replace(" — ", ": ")
            available = [""] + choices
            default_val = item_answers.get(label, "")
            chosen = st.selectbox(
                clean_label,
                options=available,
                index=_safe_index(available, default_val),
                key=f"{key_prefix}_dd_{idx}",
            )
            out.setdefault("item_answers", {})[label] = chosen

    # === DRAGDROP / YESNO / FILL-BLANKS (via available_values) ===
    elif available_values and ("Blank" in question.get("question_text", "") or "Step" in question.get("question_text", "") or statements):
        item_answers = payload.get("item_answers", {})
        
        # DRAGDROP with blanks or steps
        if "Blank" in question.get("question_text", "") or "Step" in question.get("question_text", ""):
            st.markdown("**Select values to fill each position:**")
            blanks = question.get("correct_answer", {}).get("items", [])
            for idx, item in enumerate(blanks, start=1):
                label = item.get("label") or f"Item {idx}"
                opts = [""] + available_values
                default_val = item_answers.get(label, "")
                chosen = st.selectbox(
                    f"**{label}**",
                    options=opts,
                    index=_safe_index(opts, default_val),
                    key=f"{key_prefix}_blank_{idx}",
                    help=f"Available options: {', '.join(available_values[:3])}..." if len(available_values) > 3 else f"Available: {', '.join(available_values)}",
                )
                out.setdefault("item_answers", {})[label] = chosen
        
        # YESNO statements
        elif statements:
            st.markdown("**Answer each statement (Yes/No):**")
            for idx, statement in enumerate(statements, start=1):
                label = statement
                default_val = item_answers.get(label, "")
                chosen = st.radio(
                    label,
                    options=["", "Yes", "No"],
                    index=_safe_index(["", "Yes", "No"], default_val),
                    horizontal=True,
                    key=f"{key_prefix}_yn_{idx}",
                )
                out.setdefault("item_answers", {})[label] = chosen

    # === MULTI-SELECT (multiple choice answers) ===
    elif qtype == "MULTI" or question.get("select_count", 1) > 1:
        if options:
            st.markdown("**Select one or more options:**")
            option_labels = [f"{o['key']}. {o['text']}" for o in options]
            key_to_text = {o["key"]: o["text"] for o in options}

            default_selected = payload.get("selected_options", [])
            selected = st.multiselect(
                "Options",
                options=[o["key"] for o in options],
                default=default_selected,
                key=f"{key_prefix}_multi",
            )
            out["selected_options"] = selected
            out["selected_option_texts"] = [key_to_text.get(s, "") for s in selected]
            
            # Show selected options
            if selected:
                st.info(f"Selected: {' + '.join(selected)}")

    # === SINGLE-SELECT (multiple choice) ===
    elif options:
        st.markdown("**Select one option:**")
        choices = [""] + [o["key"] for o in options]
        key_to_text = {o["key"]: o["text"] for o in options}
        default_key = payload.get("selected_option", "")
        
        selected = st.radio(
            "Options",
            choices,
            index=_safe_index(choices, default_key),
            format_func=lambda x: "Choose..." if x == "" else f"{x}. {key_to_text.get(x, '')}",
            key=f"{key_prefix}_single",
        )
        out["selected_option"] = selected
        out["selected_option_text"] = key_to_text.get(selected, "")

    # === FALLBACK TEXT ANSWER ===
    else:
        st.markdown("**Your answer:**")
        text_default = payload.get("text_answer", "")
        out["text_answer"] = st.text_area(
            "Type your answer",
            value=text_default,
            key=f"{key_prefix}_txt",
            placeholder="Type your answer...",
            height=100,
        )

    return out


def submit_and_check_round(
    db: ExamDB,
    session: Dict[str, Any],
    round_row: Dict[str, Any],
    round_questions: List[Dict[str, Any]],
) -> Tuple[int, int, List[str]]:
    round_id = int(round_row["id"])
    answers = db.get_round_answers(round_id)
    total = len(round_questions)
    correct_count = 0
    failed_qcodes: List[str] = []

    for q in round_questions:
        qcode = q["qcode"]
        current = answers.get(qcode, {"answer": {}})
        result = evaluate_answer(q, current.get("answer") or {})
        is_correct = bool(result["is_correct"])
        if is_correct:
            correct_count += 1
        else:
            failed_qcodes.append(qcode)

        db.upsert_answer(
            round_id=round_id,
            qcode=qcode,
            answer_payload=current.get("answer") or {},
            is_checked=True,
            is_correct=is_correct,
            feedback=result.get("feedback", ""),
        )

    db.complete_round(round_id)

    if failed_qcodes:
        next_round = int(session["current_round"]) + 1
        if session["retry_mode"] == "auto":
            db.create_round(int(session["id"]), next_round, failed_qcodes)
            db.update_session_round(int(session["id"]), next_round)
        else:
            db.update_session_round(int(session["id"]), next_round)
    else:
        db.complete_session(int(session["id"]))

    return correct_count, total, failed_qcodes


def render_history(db: ExamDB) -> None:
    st.subheader("📊 Session History")
    sessions = db.list_sessions()
    if not sessions:
        st.info("No sessions yet.")
        return

    for s in sessions:
        rounds = db.list_rounds(int(s["id"]))
        with st.expander(
            f"Session #{s['id']} — {s['name']} ({s['status']}) | {len(rounds)} round(s)",
            expanded=False,
        ):
            for r in rounds:
                questions = db.get_round_questions(int(r["id"]))
                qcodes = [q["qcode"] for q in questions]
                answers = db.get_round_answers(int(r["id"]))
                
                correct_count = sum(
                    1 for q in questions
                    if answers.get(q["qcode"], {}).get("is_correct") is True
                )
                
                col_info, col_action = st.columns([3, 1])
                with col_info:
                    st.markdown(
                        f"**Round {r['round_number']}** | {len(qcodes)} Q | "
                        f"Correct: {correct_count}/{len(qcodes)} | {r['status']} | {r['created_at'][:10]}"
                    )
                with col_action:
                    if r["status"] == "completed":
                        failed_qcodes = [
                            q["qcode"] for q in questions
                            if not (answers.get(q["qcode"], {}).get("is_correct") is True)
                        ]
                        if failed_qcodes:
                            if st.button(
                                f"🔄 Retry {len(failed_qcodes)}",
                                key=f"retry_round_{r['id']}",
                                use_container_width=True,
                            ):
                                next_round_no = int(r["round_number"]) + 1
                                db.create_round(int(s["id"]), next_round_no, failed_qcodes)
                                db.update_session_round(int(s["id"]), next_round_no)
                                st.rerun()


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="🧠", layout="wide")
    st.title(APP_TITLE)
    st.caption("Local-first practice app with persistent exam sessions, retries, and explanations.")

    db = ExamDB("exam_app.db")

    docx_path = st.sidebar.text_input("DOCX path", value=DEFAULT_DOCX)
    ready, msg = load_questions_if_needed(db, docx_path)
    if ready:
        st.sidebar.success(msg)
    else:
        st.sidebar.error(msg)
        st.stop()

    page = st.sidebar.radio(
        "Navigation",
        ["Practice", "History"],
        index=0,
    )

    if page == "History":
        render_history(db)
        return

    # ==================== PRACTICE PAGE ====================
    st.subheader("Practice")
    sessions = db.list_sessions()
    in_progress_sessions = [s for s in sessions if s["status"] == "in_progress"]

    if "active_session_id" not in st.session_state:
        st.session_state["active_session_id"] = None

    # === START NEW SESSION ===
    with st.expander("➕ Start New Session", expanded=not st.session_state.get("active_session_id")):
        col_name, col_btn = st.columns([3, 1])
        with col_name:
            name = st.text_input("Session name", value="My DP-700 Session", key="new_session_name")
        with col_btn:
            if st.button("Create", type="primary", use_container_width=True):
                all_qcodes = [q["qcode"] for q in db.get_questions()]
                session_id = db.create_session(name=name, source_docx=docx_path)
                db.create_round(session_id=session_id, round_number=1, qcodes=all_qcodes)
                st.session_state["active_session_id"] = session_id
                st.success(f"✓ Created session #{session_id} with {len(all_qcodes)} questions")
                st.rerun()

    # === CONTINUE SESSION ===
    if in_progress_sessions:
        with st.expander("▶️ Continue Session"):
            for s in in_progress_sessions:
                current_round_no = int(s["current_round"])
                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(
                        f"**#{s['id']} — {s['name']}** | Round {current_round_no} | {s['created_at'][:10]}"
                    )
                with col_btn:
                    if st.button("Open", key=f"open_session_{s['id']}", use_container_width=True):
                        st.session_state["active_session_id"] = s["id"]
                        st.rerun()

    # === NO SESSION SELECTED ===
    if not st.session_state.get("active_session_id"):
        if not in_progress_sessions:
            st.info("No active sessions. Create a new one above.")
        return

    # === ACTIVE SESSION ===
    session_id = int(st.session_state["active_session_id"])
    session = db.get_session(session_id)
    if not session:
        st.warning("Session not found.")
        st.session_state["active_session_id"] = None
        st.rerun()

    st.divider()
    st.markdown(f"### Session #{session['id']} — {session['name']}")

    current_round_no = int(session["current_round"])
    round_row = db.get_round(session_id, current_round_no)

    # === CHECK IF ROUND COMPLETED ===
    if not round_row:
        prev_round_no = current_round_no - 1
        if prev_round_no > 0:
            prev_round = db.get_round(session_id, prev_round_no)
            if prev_round:
                prev_questions = db.get_round_questions(int(prev_round["id"]))
                prev_answers = db.get_round_answers(int(prev_round["id"]))
                failed_qcodes = [
                    q["qcode"]
                    for q in prev_questions
                    if not (prev_answers.get(q["qcode"], {}).get("is_correct") is True)
                ]

                st.markdown(f"#### Round {prev_round_no} Completed")
                correct_count = sum(
                    1
                    for q in prev_questions
                    if prev_answers.get(q["qcode"], {}).get("is_correct") is True
                )
                st.metric("Score", f"{correct_count}/{len(prev_questions)}")

                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("➕ Retry All Questions", type="primary", use_container_width=True):
                        all_qcodes = [q["qcode"] for q in db.get_questions()]
                        db.create_round(session_id, current_round_no, all_qcodes)
                        st.rerun()

                with col2:
                    if failed_qcodes:
                        if st.button(
                            f"🔄 Retry Failed ({len(failed_qcodes)})",
                            use_container_width=True,
                        ):
                            db.create_round(session_id, current_round_no, failed_qcodes)
                            st.rerun()
                    else:
                        st.success("✅ All correct!")

                with col3:
                    if st.button("📊 View History", use_container_width=True):
                        st.session_state["view_history"] = True
                        st.rerun()
            else:
                st.info("Session complete. Start a new one or view history.")
        else:
            st.info("No round created yet.")
        return

    # === ACTIVE ROUND QUESTIONS ===
    round_id = int(round_row["id"])
    round_questions = db.get_round_questions(round_id)
    qcodes = [q["qcode"] for q in round_questions]
    answers = db.get_round_answers(round_id)

    stats = db.get_round_stats(round_id, qcodes)

    # === METRICS & NAVIGATION ===
    metric_cols = st.columns(5)
    metric_cols[0].metric("Questions", len(qcodes))
    metric_cols[1].metric("Open", stats["open"])
    metric_cols[2].metric("Filled", stats["filled"])
    metric_cols[3].metric("Checked", stats["checked"])
    metric_cols[4].metric("Correct", stats["correct"])

    st.caption(
        f"Round {round_row['round_number']} | {len(qcodes)} questions"
    )

    # === QUESTION NAVIGATOR ===
    nav_cols = st.columns(10)
    for i, q in enumerate(round_questions):
        icon = get_status_icon(answers.get(q["qcode"], {}))
        with nav_cols[i % 10]:
            if st.button(f"{icon} {q['qcode']}", key=f"nav_{round_id}_{q['qcode']}", use_container_width=True):
                st.session_state["question_idx"] = i

    if "question_idx" not in st.session_state:
        st.session_state["question_idx"] = 0

    idx = int(st.session_state.get("question_idx", 0))
    if idx < 0:
        idx = 0
    if idx >= len(round_questions):
        idx = len(round_questions) - 1

    q = round_questions[idx]
    existing_answer = answers.get(q["qcode"], {})

    # === QUESTION DISPLAY ===
    render_question_display(q)

    # === ANSWER EDITOR ===
    st.divider()
    st.subheader("Your Answer")
    answer_payload = render_answer_editor(q, existing_answer, key_prefix=f"r{round_id}_{q['qcode']}")

    # === ACTION BUTTONS ===
    st.divider()
    col_actions = st.columns(5)
    with col_actions[0]:
        if st.button("✓ Save answer", type="primary", use_container_width=True):
            db.upsert_answer(
                round_id=round_id,
                qcode=q["qcode"],
                answer_payload=answer_payload,
                is_checked=False,
                is_correct=None,
                feedback="",
            )
            st.success("✓ Saved")
            st.rerun()

    with col_actions[1]:
        if st.button("🔍 Check this", use_container_width=True):
            result = evaluate_answer(q, answer_payload)
            db.upsert_answer(
                round_id=round_id,
                qcode=q["qcode"],
                answer_payload=answer_payload,
                is_checked=True,
                is_correct=bool(result["is_correct"]),
                feedback=result.get("feedback", ""),
            )
            st.rerun()

    with col_actions[2]:
        if st.button("← Prev", use_container_width=True):
            st.session_state["question_idx"] = max(0, idx - 1)
            st.rerun()

    with col_actions[3]:
        if st.button("Next →", use_container_width=True):
            st.session_state["question_idx"] = min(len(round_questions) - 1, idx + 1)
            st.rerun()

    with col_actions[4]:
        if st.button("📤 Submit Round", type="primary", use_container_width=True):
            correct_count, total, failed_qcodes = submit_and_check_round(
                db,
                session,
                round_row,
                round_questions,
            )
            st.rerun()

    # === RESULT / FEEDBACK ===
    refreshed_answer = db.get_answer(round_id, q["qcode"])
    if refreshed_answer and refreshed_answer.get("is_checked"):
        st.divider()
        if refreshed_answer.get("is_correct"):
            st.success("✅ **Correct!**")
        else:
            st.error("❌ **Not correct yet.**")

        if refreshed_answer.get("feedback"):
            with st.expander("Check details", expanded=True):
                st.markdown(refreshed_answer["feedback"])

        if q.get("explanation"):
            with st.expander("📖 Explanation", expanded=True):
                st.info(q["explanation"])



if __name__ == "__main__":
    main()
