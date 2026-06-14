import os
import json
import subprocess
import time
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

ACCOUNTS = ["account1", "account2", "account3"]

def read_json(filename):
    if not os.path.exists(filename):
        return {}
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except Exception as e:
        return {}

def read_file(filename):
    if not os.path.exists(filename):
        return ""
    try:
        with open(filename, "r") as f:
            return f.read()
    except Exception:
        return ""

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status", methods=["GET"])
def get_status():
    status_data = {}
    current_time = time.time()
    
    for i, acc in enumerate(ACCOUNTS):
        data_log = read_json(f"data-{acc}.json")
        posts_log = read_json(f"posts-{acc}.json")
        pending_log = read_json(f"pending-{acc}.json")
        review_log = read_json(f"review-{acc}.json")
        
        last_check = data_log.get("last_reply_check", 0)
        next_post = data_log.get("next_post_time", 0)
        
        # Read the account name from .env, fallback to "Account X"
        env_name_key = f"ACCOUNT{i+1}_NAME"
        bot_name = os.getenv(env_name_key, f"Account {i+1}")

        # Usernames for links
        threads_user = os.getenv(f"ACCOUNT{i+1}_THREADS_USERNAME", "")
        twitter_user = os.getenv(f"ACCOUNT{i+1}_X_USERNAME", "")

        perf_log = read_json(f"performance-{acc}.json")

        status_data[acc] = {
            "name": bot_name,
            "threads_url": f"https://www.threads.net/@{threads_user}" if threads_user else None,
            "twitter_url": f"https://x.com/{twitter_user}" if twitter_user else None,
            "post_count": data_log.get("post_count", 0),
            "replied_count": len(data_log.get("replied_comments", [])),
            "last_reply_check": last_check,
            "next_post_time": next_post,
            "is_active": (current_time - last_check) < 3600, # Active if checked in last hour
            "upcoming_posts": posts_log,
            "has_role_file": os.path.exists(f"roles/{acc}.txt"),
            "pending_approvals": pending_log if isinstance(pending_log, list) else [],
            "review_requests": review_log if isinstance(review_log, list) else [],
            "performance": perf_log.get("posts", []) if isinstance(perf_log, dict) else []
        }
    return jsonify(status_data)

@app.route("/api/roles", methods=["GET"])
def get_roles():
    roles_data = {}
    for acc in ACCOUNTS:
        roles_data[acc] = read_file(f"roles/{acc}.txt")
    return jsonify(roles_data)

@app.route("/api/roles/<account>", methods=["POST"])
def update_role(account):
    if account not in ACCOUNTS:
        return jsonify({"error": "Invalid account"}), 400
    data = request.json
    new_role = data.get("role_text")
    if new_role is not None:
        os.makedirs("roles", exist_ok=True)
        with open(f"roles/{account}.txt", "w") as f:
            f.write(new_role)
        return jsonify({"success": True})
    return jsonify({"error": "Missing role_text"}), 400

@app.route("/api/posts/<account>", methods=["POST"])
def update_posts(account):
    if account not in ACCOUNTS:
        return jsonify({"error": "Invalid account"}), 400
    data = request.json
    new_posts = data.get("posts")
    if new_posts is not None:
        with open(f"posts-{account}.json", "w") as f:
            json.dump(new_posts, f)
        return jsonify({"success": True})
    return jsonify({"error": "Missing posts"}), 400

@app.route("/api/trigger/<account>", methods=["POST"])
def trigger_run(account):
    if account not in ACCOUNTS:
        return jsonify({"error": "Invalid account"}), 400
    
    # Run the bot in a subprocess
    cmd = ["python", "main.py", account, "--role-txt-path", f"roles/{account}.txt"]
    subprocess.Popen(cmd) # Run asynchronously
    return jsonify({"success": True, "message": f"Triggered run for {account}"})

@app.route("/api/settings", methods=["GET"])
def get_settings_route():
    settings = read_json("settings.json")
    return jsonify(settings)

@app.route("/api/settings", methods=["POST"])
def update_settings():
    new_settings = request.json
    with open("settings.json", "w") as f:
        json.dump(new_settings, f, indent=4)
    return jsonify({"success": True})

@app.route("/api/approve_post/<account>", methods=["POST"])
def approve_post(account):
    if account not in ACCOUNTS:
        return jsonify({"error": "Invalid account"}), 400
        
    data = request.json
    action = data.get("action") # "approve" or "reject"
    post_index = data.get("index")
    
    pending = read_json(f"pending-{account}.json")
    if not isinstance(pending, list) or post_index < 0 or post_index >= len(pending):
        return jsonify({"error": "Invalid index"}), 400
        
    post_text = pending.pop(post_index)
    
    if action == "approve":
        # Launch a background task to post it
        cmd = ["python", "-c", f"""
import asyncio
from api import post_to_threads
from twitter import post_to_x
import json
with open('settings.json') as f:
    settings = json.load(f)
sync_x = settings.get('{account}', {{}}).get('sync_x', False)
asyncio.run(post_to_threads({repr(post_text)}, '{account}'))
if sync_x:
    post_to_x({repr(post_text)})
"""]
        subprocess.Popen(cmd)
        
    # Save the updated pending list
    with open(f"pending-{account}.json", "w") as f:
        json.dump(pending, f)
        
    return jsonify({"success": True})

@app.route("/api/reply_review/<account>", methods=["POST"])
def reply_review(account):
    if account not in ACCOUNTS:
        return jsonify({"error": "Invalid account"}), 400
        
    data = request.json
    index = data.get("index")
    reply_text = data.get("reply_text")
    
    reviews = read_json(f"review-{account}.json")
    if not isinstance(reviews, list) or index < 0 or index >= len(reviews):
        return jsonify({"error": "Invalid index"}), 400
        
    review_item = reviews.pop(index)
    
    if reply_text and reply_text.strip():
        # Launch background task to reply
        cmd = ["python", "-c", f"""
import asyncio
from api import reply_to_thread
asyncio.run(reply_to_thread({repr(reply_text)}, '{review_item["reply_id"]}', '{account}'))
"""]
        subprocess.Popen(cmd)
        
    with open(f"review-{account}.json", "w") as f:
        json.dump(reviews, f)
        
    return jsonify({"success": True})

if __name__ == "__main__":
    import webbrowser
    from threading import Timer

    def open_browser():
        webbrowser.open_new("http://127.0.0.1:5000/")

    Timer(1, open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
