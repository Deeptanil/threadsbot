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
    
    for acc in ACCOUNTS:
        data_log = read_json(f"data-{acc}.json")
        posts_log = read_json(f"posts-{acc}.json")
        
        last_check = data_log.get("last_reply_check", 0)
        next_post = data_log.get("next_post_time", 0)
        
        status_data[acc] = {
            "post_count": data_log.get("post_count", 0),
            "replied_count": len(data_log.get("replied_comments", [])),
            "last_reply_check": last_check,
            "next_post_time": next_post,
            "is_active": (current_time - last_check) < 3600, # Active if checked in last hour
            "upcoming_posts": posts_log
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

if __name__ == "__main__":
    import webbrowser
    from threading import Timer

    def open_browser():
        webbrowser.open_new("http://127.0.0.1:5000/")

    Timer(1, open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
