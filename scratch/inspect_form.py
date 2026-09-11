import sqlite3
import json
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def inspect():
    conn = sqlite3.connect("registration.sqlite3")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    forms = cur.execute("SELECT * FROM registration_configs").fetchall()
    print(f"Total forms in DB: {len(forms)}")
    for f in forms:
        d = dict(f)
        print(f"\n--- Form #{d['id']}: {d.get('name', 'Unnamed')} ---")
        print(f"Description: {d.get('description')}")
        print(f"Guild: {d.get('guild_id')}, Channel: {d.get('channel_id')}, Review Channel: {d.get('review_channel_id')}")
        print(f"Approval Mode: {d.get('approval_mode')}, Max Submissions: {d.get('max_submissions_per_user')}")
        print(f"Add Roles: {d.get('add_role_ids')}, Nickname Format: {d.get('nickname_format')}")

        questions = cur.execute(
            "SELECT * FROM registration_questions WHERE registration_id = ? ORDER BY position ASC", 
            (d['id'],)
        ).fetchall()
        print(f"Questions ({len(questions)}):")
        for q in questions:
            qd = dict(q)
            opts = json.loads(qd.get("options") or "[]")
            print(f"  • Q{qd['id']} [{qd['field_type']}]: '{qd['question']}' (required={bool(qd['required'])}, options_count={len(opts)})")
            if opts and len(opts) <= 5:
                print(f"      Options: {opts}")
            elif opts:
                print(f"      Sample Options: {opts[:3]} ... +{len(opts)-3} more")

    subs = cur.execute("SELECT * FROM registration_submissions").fetchall()
    print(f"\nTotal Submissions: {len(subs)}")
    logs = cur.execute("SELECT * FROM registration_logs ORDER BY id DESC LIMIT 5").fetchall()
    print(f"Recent Logs ({len(logs)}):")
    for l in logs:
        ld = dict(l)
        print(f"  [{ld.get('created_at', 'N/A')}] {ld.get('action', 'N/A')} (Form {ld.get('registration_id', 'N/A')}): {ld.get('details', 'N/A')}")

def test_steps():
    from registration import RegistrationDatabase, partition_questions, StepInteractiveView
    db = RegistrationDatabase()
    cfg = db.get_form(1)
    if not cfg:
        print("No form found with ID 1.")
        return
    print(f"\nTesting Steps for Form #{cfg['id']} '{cfg['name']}':")
    questions = db.get_questions(1)
    steps = partition_questions(questions)
    print(f"Form has {len(questions)} questions divided into {len(steps)} steps:")
    for idx, s in enumerate(steps):
        q_names = [q["question"] for q in s]
        print(f"  Step {idx + 1}: {q_names}")
        view = StepInteractiveView("test-session-id", 1, idx, steps)
        print(f"    View components: {len(view.children)}")
        for child in view.children:
            opts_len = len(getattr(child, 'options', []))
            print(f"      Component: {type(child).__name__} (placeholder='{getattr(child, 'placeholder', '')}', options={opts_len})")

    # Test question update
    if questions:
        q1 = questions[0]
        orig_placeholder = q1["placeholder"]
        db.update_question(q1["id"], placeholder="Updated via Dashboard/API")
        refreshed = db.get_question(q1["id"])
        print(f"\n✅ Verified question update: '{refreshed['placeholder']}'")
        db.update_question(q1["id"], placeholder=orig_placeholder)
        print(f"✅ Restored original placeholder: '{orig_placeholder}'")

if __name__ == "__main__":
    inspect()
    test_steps()

