import subprocess
import os
import shutil
import glob
import sys

STATE_PATTERNS = ["data-*.json", "posts-*.json", "performance-*.json", "pending-*.json", "review-*.json"]

def run_git(args, cwd=None, capture=False):
    """Helper to run a git command and return result."""
    try:
        res = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=capture,
            text=True,
            check=True
        )
        return res
    except subprocess.CalledProcessError as e:
        return e

def get_state_files():
    """Get all local files matching the state file patterns."""
    state_files = []
    for pattern in STATE_PATTERNS:
        state_files.extend(glob.glob(pattern))
    return list(set(state_files))

def pull_state():
    print("Syncing: Pulling latest bot state from remote 'state' branch...")
    # 1. Fetch the remote state branch
    res = run_git(["fetch", "origin", "state"])
    if isinstance(res, subprocess.CalledProcessError):
        print("Warning: Failed to fetch state branch from origin. Working offline?")
        return False

    # 2. Check if origin/state exists
    res = run_git(["rev-parse", "--verify", "origin/state"], capture=True)
    if isinstance(res, subprocess.CalledProcessError):
        print("Remote branch 'state' does not exist yet. Nothing to pull.")
        return False

    # 3. Get the list of files tracked on origin/state
    res = run_git(["ls-tree", "-r", "--name-only", "origin/state"], capture=True)
    if isinstance(res, subprocess.CalledProcessError):
        print("Failed to list files in state branch.")
        return False

    files = res.stdout.strip().splitlines()
    state_files_to_checkout = []
    for f in files:
        if f.endswith(".json") and any(f.startswith(p.replace("*.json", "")) for p in STATE_PATTERNS):
            state_files_to_checkout.append(f)

    if not state_files_to_checkout:
        print("No state files found in remote 'state' branch.")
        return False

    # 4. Checkout the state files into the working directory
    print(f"Restoring state files from remote: {', '.join(state_files_to_checkout)}")
    res = run_git(["checkout", "origin/state", "--"] + state_files_to_checkout)
    if isinstance(res, subprocess.CalledProcessError):
        print("Warning: Failed to checkout state files.")
        return False

    print("State successfully pulled.")
    return True

def push_state(message="chore: update bot state"):
    print("Syncing: Pushing latest bot state to remote 'state' branch...")
    # 1. Ensure the remote exists and fetch it
    run_git(["fetch", "origin", "state"])

    # 2. Ensure local 'state' branch exists.
    res_local = run_git(["rev-parse", "--verify", "state"], capture=True)
    res_remote = run_git(["rev-parse", "--verify", "origin/state"], capture=True)

    if isinstance(res_local, subprocess.CalledProcessError):
        if not isinstance(res_remote, subprocess.CalledProcessError):
            # Remote exists, track it locally
            run_git(["branch", "state", "origin/state"])
        else:
            # Neither exists. Create it locally as an orphan empty branch
            print("Creating remote state branch for the first time...")
            curr_branch_res = run_git(["rev-parse", "--abbrev-ref", "HEAD"], capture=True)
            curr_branch = curr_branch_res.stdout.strip() if not isinstance(curr_branch_res, subprocess.CalledProcessError) else "main"
            
            run_git(["checkout", "--orphan", "state"])
            run_git(["reset"]) # unstage everything
            for f in get_state_files():
                run_git(["add", f])
            run_git(["commit", "-m", "Initial state commit"])
            run_git(["push", "-u", "origin", "state"])
            run_git(["checkout", curr_branch])
            return True

    # 3. Use git worktree to commit and push changes safely
    worktree_path = "state-worktree"
    if os.path.exists(worktree_path):
        shutil.rmtree(worktree_path, ignore_errors=True)
        run_git(["worktree", "prune"])

    # Create worktree
    res_wt = run_git(["worktree", "add", worktree_path, "state"])
    if isinstance(res_wt, subprocess.CalledProcessError):
        print("Failed to add git worktree for state sync.")
        return False

    try:
        # Copy current local state files to worktree
        state_files = get_state_files()
        if not state_files:
            print("No state files found to push.")
            return False

        for f in state_files:
            shutil.copy2(f, os.path.join(worktree_path, f))

        # Commit and push from within worktree
        run_git(["add", "."], cwd=worktree_path)
        
        # Check if there are differences to commit
        res_diff = subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=worktree_path)
        if res_diff.returncode == 0:
            print("No changes in bot state to commit.")
            return True

        run_git(["commit", "-m", message], cwd=worktree_path)

        # Pull with rebase to merge any staggered bot updates
        run_git(["pull", "--rebase", "origin", "state"], cwd=worktree_path)

        # Push to origin
        run_git(["push", "origin", "state"], cwd=worktree_path)
        print("State successfully pushed.")
        return True

    finally:
        # Clean up worktree
        run_git(["worktree", "remove", "--force", worktree_path])
        run_git(["worktree", "prune"])

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "pull":
            pull_state()
        elif cmd == "push":
            msg = sys.argv[2] if len(sys.argv) > 2 else "chore: update bot state"
            push_state(msg)
        else:
            print(f"Unknown command: {cmd}")
    else:
        print("Usage: python sync_state.py [pull|push]")
