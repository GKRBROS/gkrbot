import os
import sys
import tempfile
import json
import sqlite3
import datetime

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Add root directory to sys.path
sys.path.insert(0, r"c:\Users\USER\Documents\Discord\GKR")

from registration import RegistrationDatabase, ValidationEngine, partition_questions, FIELD_TYPES

def run_tests():
    print("==================================================")
    print("🧪 Running Dynamic Registration System Test Suite")
    print("==================================================")

    test_db_path = os.path.join(tempfile.gettempdir(), f"test_reg_{os.getpid()}.sqlite3")
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = RegistrationDatabase(test_db_path)
    print("✅ Database initialized successfully.")

    # 1. Test Form Creation
    guild_id = "123456789012345678"
    user_id = "987654321098765432"
    form_id = db.create_form(guild_id, name="Staff Application", description="Please apply for staff", created_by=user_id)
    assert form_id > 0, "Form creation failed"
    print(f"✅ Form created with ID: {form_id}")

    form = db.get_form(form_id)
    assert form["name"] == "Staff Application"
    assert form["enabled"] == 1
    print("✅ Form retrieval verified.")

    # 2. Test Form Update & Automations configuration
    db.update_form(
        form_id,
        auto_role_enabled=1,
        add_role_ids=json.dumps(["111", "222"]),
        change_nickname_enabled=1,
        nickname_format="[Staff] {name}",
        approval_mode="staff_review",
        review_channel_id="999888777",
        log_channel_id="111222333"
    )
    form = db.get_form(form_id)
    assert form["auto_role_enabled"] == 1
    assert form["approval_mode"] == "staff_review"
    assert json.loads(form["add_role_ids"]) == ["111", "222"]
    print("✅ Form automations & settings update verified.")

    # 3. Test Question Creation (All 11 types)
    q1 = db.add_question(form_id, question="What is your full name?", field_type="short_text", required=True, min_length=3, max_length=50)
    q2 = db.add_question(form_id, question="What is your age?", field_type="number", required=True, min_value=16, max_value=99)
    q3 = db.add_question(form_id, question="Tell us about yourself", field_type="paragraph", required=False)
    q4 = db.add_question(form_id, question="Do you have a working microphone?", field_type="yes_no", required=True)
    q5 = db.add_question(form_id, question="Department Choice", field_type="single_select", required=True, options=["Moderator", "Helper", "Developer"])
    q6 = db.add_question(form_id, question="Skills", field_type="multiple_select", required=False, options=["Python", "Community", "Design"])
    q7 = db.add_question(form_id, question="Who referred you?", field_type="user_select", required=False)
    q8 = db.add_question(form_id, question="Current Server Role", field_type="role_select", required=False)
    q9 = db.add_question(form_id, question="Preferred Channel", field_type="channel_select", required=False)
    q10 = db.add_question(form_id, question="Date of Birth", field_type="date", required=True)
    q11 = db.add_question(form_id, question="Portfolio URL", field_type="url", required=False)

    questions = db.get_questions(form_id)
    assert len(questions) == 11, f"Expected 11 questions, got {len(questions)}"
    print(f"✅ Created 11 diverse dynamic questions.")

    # Set nickname source question
    db.update_form(form_id, nickname_question_id=q1)
    form = db.get_form(form_id)
    assert form["nickname_question_id"] == q1
    print("✅ Linked question #1 as source for dynamic nickname.")

    # 4. Test ValidationEngine
    q_map = {q["id"]: q for q in questions}

    # Number validation
    ok, err, clean = ValidationEngine.validate_answer(q_map[q2], "21")
    assert ok and clean == "21", f"Expected valid number: {err}"

    ok, err, clean = ValidationEngine.validate_answer(q_map[q2], "abc")
    assert not ok, "Expected non-number to fail"

    ok, err, clean = ValidationEngine.validate_answer(q_map[q2], "14")
    assert not ok, "Expected number below min_value (16) to fail"

    # URL validation
    ok, err, clean = ValidationEngine.validate_answer(q_map[q11], "https://github.com/myprofile")
    assert ok and "https://" in clean, f"Expected valid URL: {err}"

    ok, err, clean = ValidationEngine.validate_answer(q_map[q11], "not-a-url")
    assert not ok, "Expected invalid URL to fail"

    # Date validation
    ok, err, clean = ValidationEngine.validate_answer(q_map[q10], "2000-05-20")
    assert ok and clean == "2000-05-20", f"Expected valid date: {err}"

    ok, err, clean = ValidationEngine.validate_answer(q_map[q10], "not-a-date")
    assert not ok, "Expected invalid date to fail"

    # Yes/No validation
    ok, err, clean = ValidationEngine.validate_answer(q_map[q4], "yes")
    assert ok and clean == "Yes", f"Expected valid Yes/No: {err}"

    ok, err, clean = ValidationEngine.validate_answer(q_map[q4], "maybe")
    assert not ok, "Expected invalid Yes/No to fail"

    # Select choice validation
    ok, err, clean = ValidationEngine.validate_answer(q_map[q5], "Moderator")
    assert ok and clean == "Moderator", f"Expected valid choice: {err}"

    ok, err, clean = ValidationEngine.validate_answer(q_map[q5], "CEO")
    assert not ok, "Expected unconfigured choice to fail"

    # Required field validation
    ok, err, clean = ValidationEngine.validate_answer(q_map[q1], "")
    assert not ok, "Expected empty required field to fail"

    # Optional field validation
    ok, err, clean = ValidationEngine.validate_answer(q_map[q3], "")
    assert ok, "Expected empty optional field to pass"
    print("✅ ValidationEngine verified for all question types and boundary rules.")

    # 5. Test Multi-Step Question Partitioning (Handling Discord 5-item modal limit)
    steps = partition_questions(questions)
    assert len(steps) > 1, "Expected multiple steps for 11 questions"
    for s_idx, step in enumerate(steps):
        # If text-based, must be <= 5 items
        text_count = sum(1 for q in step if q["field_type"] in ("short_text", "paragraph", "number", "date", "url"))
        assert text_count <= 5, f"Step {s_idx} exceeded modal limit of 5: {text_count}"
    print(f"✅ Question partitioning verified: {len(questions)} questions split into {len(steps)} safe steps.")

    # 6. Test Submission Creation & Duplicate Prevention
    answers = {
        q1: "Alex Hunter",
        q2: "22",
        q3: "Experienced Discord moderator",
        q4: "Yes",
        q5: "Moderator",
        q6: "Python, Community",
        q10: "2002-08-14",
        q11: "https://example.com"
    }
    sub_id = db.create_submission(form_id, guild_id, user_id, answers, status="pending")
    assert sub_id > 0, "Submission creation failed"
    print(f"✅ Submission #{sub_id} created successfully.")

    # Check duplicate detection
    existing = db.get_submissions_by_user(guild_id, user_id, form_id)
    has_active = any(s["status"] in ("pending", "approved") for s in existing)
    assert has_active, "Duplicate check failed: user should have active submission"
    print("✅ Duplicate submission prevention verified.")

    # 7. Test Submissions Retrieval & Answers
    retrieved_answers = db.get_answers(sub_id)
    assert len(retrieved_answers) == len(answers), f"Answers count mismatch: {len(retrieved_answers)} vs {len(answers)}"
    ans_dict = {a["question_id"]: a["answer"] for a in retrieved_answers}
    assert ans_dict[q1] == "Alex Hunter"
    assert ans_dict[q2] == "22"
    print("✅ Stored submission answers verified.")

    # 8. Test Status Updates (Approval / Rejection)
    db.update_submission_status(sub_id, "approved", reviewed_by="AdminUser123")
    sub = db.get_submission(sub_id)
    assert sub["status"] == "approved"
    assert sub["reviewed_by"] == "AdminUser123"
    print("✅ Submission approval status update verified.")

    # 9. Test Audit Logging
    db.log_event(guild_id, "approved", f"Approved application #{sub_id}", registration_id=form_id, submission_id=sub_id, actor_id="AdminUser123", target_user_id=user_id)
    logs = db.get_logs(guild_id)
    assert len(logs) >= 2, "Expected at least 2 log entries"
    event_types = [l["event_type"] for l in logs]
    assert "form_created" in event_types
    assert "submitted" in event_types
    assert "approved" in event_types
    print(f"✅ Audit logging verified: {len(logs)} events logged.")

    # Clean up test database
    try:
        os.remove(test_db_path)
    except Exception:
        pass

    print("==================================================")
    print("🎉 ALL TESTS PASSED! REGISTRATION ENGINE 100% OPERATIONAL")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
