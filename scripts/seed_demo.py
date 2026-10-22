"""Create local, clearly labelled demo data without changing existing data."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from logic import normalize_questions, validate_submission

DEMO_PASSWORD = "Demo12345!"
DEMO_TAG = "stage1_walkthrough_v1"


def ensure_demo_user(db, username):
    existing = db.users.find_one({"username": username})
    if existing:
        if not check_password_hash(existing["password_hash"], DEMO_PASSWORD):
            raise SystemExit(f"Account {username} already exists with another password; nothing was reset.")
        return existing["_id"]
    return db.users.insert_one({
        "username": username, "password_hash": generate_password_hash(DEMO_PASSWORD),
        "created_at": datetime.now(timezone.utc),
    }).inserted_id


def main():
    app = create_app()
    db = app.extensions["db"]
    try:
        owner_id = ensure_demo_user(db, "demo_owner")
        writer_id = ensure_demo_user(db, "demo_user")
        survey = db.surveys.find_one({"demo_tag": DEMO_TAG, "owner_id": owner_id})
        if survey is None:
            source = Path(__file__).resolve().parents[1] / "samples" / "demo_survey.json"
            survey = json.loads(source.read_text(encoding="utf-8"))
            survey["questions"] = normalize_questions(survey["questions"])
            now = datetime.now(timezone.utc)
            survey.update(owner_id=owner_id, status="published", created_at=now, updated_at=now, demo_tag=DEMO_TAG)
            survey["_id"] = db.surveys.insert_one(survey).inserted_id
            sample_answers = [
                {"q_path": "yes", "q_fruits": ["apple", "banana"], "q_age": 20, "q_advice": "增加上机练习", "q_feedback": "页面清楚"},
                {"q_path": "no", "q_age": 16, "q_feedback": None},
            ]
            for answers in sample_answers:
                db.responses.insert_one({
                    "survey_id": survey["_id"], "respondent_id": writer_id,
                    "single_submission": False,
                    "answers": validate_submission(survey["questions"], answers),
                    "submitted_at": now,
                })
            print("Created demo questionnaire with two valid responses.")
        else:
            print("Demo questionnaire already exists; no data was overwritten or added.")
        print("Local demo accounts: demo_owner / demo_user")
        print("Demo password (both accounts):", DEMO_PASSWORD)
        print("Fill page: http://127.0.0.1:5000/survey/" + str(survey["_id"]))
        print("Statistics: http://127.0.0.1:5000/surveys/" + str(survey["_id"]) + "/statistics")
    finally:
        app.extensions["mongo_client"].close()


if __name__ == "__main__":
    main()
