# AZ-305 Practice Exam Trainer (Local App)

A local Streamlit app that parses the included DOCX practice exam and provides:

- Persistent exam sessions in SQLite
- Save and continue ongoing exams later
- Retry only failed questions across multiple rounds until all are correct
- Question navigation with status indicators (open / filled / checked / right / wrong)
- Explanations shown after checking
- Session/round history and old attempts retained in the database

## Requirements

- Python 3.10+
- Windows/macOS/Linux

## Quick Start

1. Open this folder in a terminal.
2. (Recommended) create and activate a virtual environment.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the app:

```bash
streamlit run app.py
```

5. Open the local URL shown in terminal (typically `http://localhost:8501`).

## How It Works

- On first run, the app reads `AZ305_renumbered.docx` and stores parsed questions/answers in SQLite.
- The SQLite file `exam_app.db` stores:
  - all parsed questions
  - all sessions
  - all rounds
  - all answer attempts
- In **submit mode**, answers are checked when submitting the round.
- In **immediate mode**, answers are checked per question when saved.
- In **auto retry mode**, the next round is automatically created with failed questions.
- In **manual retry mode**, you can start the failed-only next round yourself.

## Project Files

- `app.py` - Streamlit UI and exam flow
- `db.py` - SQLite schema and data operations
- `exam_parser.py` - DOCX parser and answer evaluation
- `requirements.txt` - Python dependencies
- `.gitignore` - Git ignore defaults

## GitHub Sharing

Suggested steps:

```bash
git init
git add .
git commit -m "Initial AZ-305 exam trainer"
```

Then create a GitHub repository and push:

```bash
git remote add origin <your-repo-url>
git branch -M main
git push -u origin main
```

## Notes

- If you use a different DOCX filename, set it in the app sidebar (`DOCX path`).
- If you want to re-import changed question data, delete `exam_app.db` and run again.
