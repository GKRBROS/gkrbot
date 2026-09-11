import sqlite3
import json

def inspect():
    conn = sqlite3.connect("registration.sqlite3")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    forms = cur.execute("SELECT * FROM registration_configs").fetchall()
    print(f"Total forms in DB: {len(forms)}")
    for f in forms:
        d = dict(f)
        print(f"\n--- Form #{d['id']}: {d['title']} ---")
        print(f"Description: {d.get('description')}")
        print(f"Guild: {d.get('guild_id')}, Channel: {d.get('channel_id')}, Review Channel: {d.get('review_channel_id')}")
        print(f"Auto Approve: {bool(d.get('auto_approve'))}, Allow Multiple: {bool(d.get('allow_multiple'))}")
        print(f"Assigned Roles: {d.get('assigned_role_ids')}, Nickname Format: {d.get('nickname_format')}")

        questions = cur.execute(
            "SELECT * FROM registration_questions WHERE form_id = ? ORDER BY order_index ASC", 
            (d['id'],)
        ).fetchall()
        print(f"Questions ({len(questions)}):")
        for q in questions:
            qd = dict(q)
            opts = json.loads(qd.get("options") or "[]")
            print(f"  • Q{qd['id']} [{qd['question_type']}]: '{qd['label']}' (required={bool(qd['required'])}, options_count={len(opts)})")
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
        print(f"  [{ld['timestamp']}] {ld['event_type']} (Form {ld['form_id']}): {ld['details']}")

if __name__ == "__main__":
    inspect()
