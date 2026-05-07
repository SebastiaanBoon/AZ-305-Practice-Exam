import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class ExamDB:
    def __init__(self, db_path: str = "exam_app.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS questions (
                    qcode TEXT PRIMARY KEY,
                    topic TEXT,
                    qtype TEXT,
                    question_text TEXT NOT NULL,
                    options_json TEXT,
                    dropdowns_json TEXT,
                    available_values_json TEXT,
                    statements_json TEXT,
                    select_count INTEGER,
                    correct_answer_json TEXT,
                    explanation TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    source_docx TEXT NOT NULL,
                    check_mode TEXT NOT NULL,
                    retry_mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_round INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS rounds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    round_number INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS round_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round_id INTEGER NOT NULL,
                    qcode TEXT NOT NULL,
                    order_index INTEGER NOT NULL,
                    FOREIGN KEY (round_id) REFERENCES rounds(id),
                    FOREIGN KEY (qcode) REFERENCES questions(qcode)
                );

                CREATE TABLE IF NOT EXISTS answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round_id INTEGER NOT NULL,
                    qcode TEXT NOT NULL,
                    answer_json TEXT,
                    is_checked INTEGER NOT NULL DEFAULT 0,
                    is_correct INTEGER,
                    feedback TEXT,
                    checked_at TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(round_id, qcode),
                    FOREIGN KEY (round_id) REFERENCES rounds(id),
                    FOREIGN KEY (qcode) REFERENCES questions(qcode)
                );
                """
            )

    def has_questions(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM questions").fetchone()
            return bool(row["c"])

    def upsert_questions(self, questions: List[Dict[str, Any]]) -> None:
        now = utc_now()
        with self._connect() as conn:
            for q in questions:
                conn.execute(
                    """
                    INSERT INTO questions (
                        qcode, topic, qtype, question_text, options_json, dropdowns_json,
                        available_values_json, statements_json, select_count,
                        correct_answer_json, explanation, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(qcode) DO UPDATE SET
                        topic = excluded.topic,
                        qtype = excluded.qtype,
                        question_text = excluded.question_text,
                        options_json = excluded.options_json,
                        dropdowns_json = excluded.dropdowns_json,
                        available_values_json = excluded.available_values_json,
                        statements_json = excluded.statements_json,
                        select_count = excluded.select_count,
                        correct_answer_json = excluded.correct_answer_json,
                        explanation = excluded.explanation,
                        updated_at = excluded.updated_at
                    """,
                    (
                        q["qcode"],
                        q.get("topic", ""),
                        q.get("qtype", "UNKNOWN"),
                        q.get("question_text", ""),
                        json.dumps(q.get("options", []), ensure_ascii=True),
                        json.dumps(q.get("dropdown_groups", {}), ensure_ascii=True),
                        json.dumps(q.get("available_values", []), ensure_ascii=True),
                        json.dumps(q.get("statements", []), ensure_ascii=True),
                        q.get("select_count"),
                        json.dumps(q.get("correct_answer", {}), ensure_ascii=True),
                        q.get("explanation", ""),
                        now,
                        now,
                    ),
                )

    def get_questions(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM questions ORDER BY qcode").fetchall()
            return [self._row_to_question(r) for r in rows]

    def get_question(self, qcode: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM questions WHERE qcode = ?", (qcode,)).fetchone()
            return self._row_to_question(row) if row else None

    def _row_to_question(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "qcode": row["qcode"],
            "topic": row["topic"],
            "qtype": row["qtype"],
            "question_text": row["question_text"],
            "options": json.loads(row["options_json"] or "[]"),
            "dropdown_groups": json.loads(row["dropdowns_json"] or "{}"),
            "available_values": json.loads(row["available_values_json"] or "[]"),
            "statements": json.loads(row["statements_json"] or "[]"),
            "select_count": row["select_count"],
            "correct_answer": json.loads(row["correct_answer_json"] or "{}"),
            "explanation": row["explanation"] or "",
        }

    def create_session(self, name: str, source_docx: str) -> int:
        now = utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO sessions (
                    name, source_docx, check_mode, retry_mode, status,
                    current_round, created_at, updated_at
                ) VALUES (?, ?, 'flexible', 'manual', 'in_progress', 1, ?, ?)
                """,
                (name, source_docx, now, now),
            )
            return int(cur.lastrowid)

    def list_sessions(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC, id DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            return dict(row) if row else None

    def update_session_round(self, session_id: int, current_round: int) -> None:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET current_round = ?, updated_at = ? WHERE id = ?",
                (current_round, now, session_id),
            )

    def complete_session(self, session_id: int) -> None:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET status = 'completed', completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, session_id),
            )

    def create_round(self, session_id: int, round_number: int, qcodes: List[str]) -> int:
        now = utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO rounds (session_id, round_number, status, created_at)
                VALUES (?, ?, 'in_progress', ?)
                """,
                (session_id, round_number, now),
            )
            round_id = int(cur.lastrowid)
            for idx, qcode in enumerate(qcodes, 1):
                conn.execute(
                    """
                    INSERT INTO round_questions (round_id, qcode, order_index)
                    VALUES (?, ?, ?)
                    """,
                    (round_id, qcode, idx),
                )
            return round_id

    def get_round(self, session_id: int, round_number: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM rounds
                WHERE session_id = ? AND round_number = ?
                LIMIT 1
                """,
                (session_id, round_number),
            ).fetchone()
            return dict(row) if row else None

    def get_current_round(self, session_id: int) -> Optional[Dict[str, Any]]:
        session = self.get_session(session_id)
        if not session:
            return None
        return self.get_round(session_id, int(session["current_round"]))

    def list_rounds(self, session_id: int) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM rounds WHERE session_id = ? ORDER BY round_number ASC",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def complete_round(self, round_id: int) -> None:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE rounds SET status = 'completed', completed_at = ? WHERE id = ?",
                (now, round_id),
            )

    def get_round_questions(self, round_id: int) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT rq.qcode
                FROM round_questions rq
                WHERE rq.round_id = ?
                ORDER BY rq.order_index ASC
                """,
                (round_id,),
            ).fetchall()
            qcodes = [r["qcode"] for r in rows]
            questions = []
            for qcode in qcodes:
                q = self.get_question(qcode)
                if q:
                    questions.append(q)
            return questions

    def upsert_answer(
        self,
        round_id: int,
        qcode: str,
        answer_payload: Dict[str, Any],
        is_checked: bool = False,
        is_correct: Optional[bool] = None,
        feedback: Optional[str] = None,
    ) -> None:
        now = utc_now()
        checked_at = now if is_checked else None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO answers (
                    round_id, qcode, answer_json, is_checked,
                    is_correct, feedback, checked_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(round_id, qcode) DO UPDATE SET
                    answer_json = excluded.answer_json,
                    is_checked = excluded.is_checked,
                    is_correct = excluded.is_correct,
                    feedback = excluded.feedback,
                    checked_at = excluded.checked_at,
                    updated_at = excluded.updated_at
                """,
                (
                    round_id,
                    qcode,
                    json.dumps(answer_payload, ensure_ascii=True),
                    1 if is_checked else 0,
                    None if is_correct is None else (1 if is_correct else 0),
                    feedback,
                    checked_at,
                    now,
                ),
            )

    def get_answer(self, round_id: int, qcode: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM answers WHERE round_id = ? AND qcode = ?",
                (round_id, qcode),
            ).fetchone()
            if not row:
                return None
            return {
                "answer": json.loads(row["answer_json"] or "{}"),
                "is_checked": bool(row["is_checked"]),
                "is_correct": None
                if row["is_correct"] is None
                else bool(row["is_correct"]),
                "feedback": row["feedback"] or "",
            }

    def get_round_answers(self, round_id: int) -> Dict[str, Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM answers WHERE round_id = ?",
                (round_id,),
            ).fetchall()
            out: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                out[row["qcode"]] = {
                    "answer": json.loads(row["answer_json"] or "{}"),
                    "is_checked": bool(row["is_checked"]),
                    "is_correct": None
                    if row["is_correct"] is None
                    else bool(row["is_correct"]),
                    "feedback": row["feedback"] or "",
                }
            return out

    def get_round_stats(self, round_id: int, qcodes: List[str]) -> Dict[str, int]:
        answers = self.get_round_answers(round_id)
        open_count = 0
        filled = 0
        checked = 0
        correct = 0
        wrong = 0
        for qcode in qcodes:
            a = answers.get(qcode)
            if not a:
                open_count += 1
                continue
            payload = a.get("answer") or {}
            has_value = any(bool(v) for v in payload.values())
            if has_value:
                filled += 1
            else:
                open_count += 1
            if a.get("is_checked"):
                checked += 1
                if a.get("is_correct"):
                    correct += 1
                elif a.get("is_correct") is False:
                    wrong += 1
        return {
            "open": open_count,
            "filled": filled,
            "checked": checked,
            "correct": correct,
            "wrong": wrong,
        }
