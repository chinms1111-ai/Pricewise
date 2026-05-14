"""
clone_job.py — PriceWise Background Clone Job
=============================================
Runs daily and auto-generates market reviews for every user
who has a profile, even when they're not online.

This is the "living clone" in action — the system simulates
each user's market review based on their profile + behavior,
without them needing to be present.

HOW TO RUN:
-----------
Option 1 — Run once manually (for testing):
    python clone_job.py

Option 2 — Run on a schedule (keeps running, fires daily at 8am):
    python clone_job.py --schedule

Option 3 — Integrate into app.py on startup (Render):
    from clone_job import run_clone_job
    run_clone_job()  # runs once on deploy

Option 4 — APScheduler (recommended for Render):
    See bottom of this file for scheduler setup.
"""

import sqlite3
import argparse
from datetime import datetime, timedelta


def get_db():
    conn = sqlite3.connect("pricewise.db")
    conn.row_factory = sqlite3.Row
    return conn


def get_all_user_profiles():
    """Fetch every user who has completed onboarding."""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT session_id, role, primary_commodity, state, priority, total_sessions
        FROM user_profiles
        WHERE primary_commodity IS NOT NULL
    """)
    profiles = c.fetchall()
    conn.close()
    return profiles


def already_generated_today(session_id, commodity):
    """
    Check if a clone review was already generated today for this user + commodity.
    Prevents duplicate runs if the job fires more than once a day.
    """
    conn = get_db()
    c = conn.cursor()
    today = datetime.now().date().isoformat()
    c.execute("""
        SELECT COUNT(*) as cnt FROM generated_reviews
        WHERE session_id = ? AND commodity = ?
        AND DATE(generated_at) = ?
        AND triggered_by = 'auto'
    """, (session_id, commodity, today))
    result = c.fetchone()["cnt"]
    conn.close()
    return result > 0


def run_clone_job():
    """
    Main clone job function.
    Loops through all user profiles and generates a review
    for each user's primary commodity if not already done today.
    """
    print(f"\n[CLONE JOB] Starting at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    profiles = get_all_user_profiles()

    if not profiles:
        print("[CLONE JOB] No user profiles found. Nothing to do.")
        return

    print(f"[CLONE JOB] Found {len(profiles)} user profile(s) to process.")

    success_count = 0
    skip_count = 0
    error_count = 0

    for profile in profiles:
        session_id = profile["session_id"]
        commodity = profile["primary_commodity"]
        role = profile["role"]
        state = profile["state"] or "Nigeria"

        # Skip if already generated today
        if already_generated_today(session_id, commodity):
            print(f"[CLONE JOB] Skipping {session_id[:8]}... — already generated today")
            skip_count += 1
            continue

        try:
            # Import here to avoid circular import issues
            from agent import generate_user_review

            print(f"[CLONE JOB] Generating review for {session_id[:8]}... | {role} | {commodity} | {state}")

            result = generate_user_review(session_id, commodity)

            if result:
                # Mark as auto-triggered (override the 'manual' default)
                _update_triggered_by(result["id"], "auto")

                print(f"[CLONE JOB] ✅ Done — {result['star_rating']}/5 stars | {result['sentiment']}")
                print(f"[CLONE JOB]    Preview: {result['review_text'][:80]}...")
                success_count += 1
            else:
                print(f"[CLONE JOB] ⚠️  No price data found for {commodity} — skipped")
                skip_count += 1

        except Exception as e:
            print(f"[CLONE JOB] ❌ Error for {session_id[:8]}...: {str(e)}")
            error_count += 1
            continue

    print(f"\n[CLONE JOB] Complete.")
    print(f"[CLONE JOB] ✅ Generated: {success_count} | ⏭️  Skipped: {skip_count} | ❌ Errors: {error_count}")
    print(f"[CLONE JOB] Finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")


def _update_triggered_by(review_id, triggered_by):
    """Update triggered_by field after insertion (since generate_user_review always sets 'manual')."""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        UPDATE generated_reviews SET triggered_by = ? WHERE id = ?
    """, (triggered_by, review_id))
    conn.commit()
    conn.close()


def run_scheduled():
    """
    Keeps the script alive and runs the clone job every 24 hours.
    Use this for local testing of the scheduler.
    For Render, use APScheduler integrated into app.py instead.
    """
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()

        # Run immediately on start
        run_clone_job()

        # Then every 24 hours at 8:00 AM
        scheduler.add_job(
            run_clone_job,
            trigger='cron',
            hour=8,
            minute=0,
            id='clone_job'
        )

        print(f"[CLONE JOB] Scheduler running. Next fire: 08:00 AM daily.")
        print("[CLONE JOB] Press Ctrl+C to stop.\n")
        scheduler.start()

    except ImportError:
        print("[CLONE JOB] APScheduler not installed.")
        print("[CLONE JOB] Run: pip install apscheduler")
        print("[CLONE JOB] Running once manually instead...\n")
        run_clone_job()

    except (KeyboardInterrupt, SystemExit):
        print("\n[CLONE JOB] Scheduler stopped.")


# ─────────────────────────────────────────────
# HOW TO INTEGRATE INTO app.py FOR RENDER
# ─────────────────────────────────────────────
# Add this to your app.py after app is created:
#
# from apscheduler.schedulers.background import BackgroundScheduler
# from clone_job import run_clone_job
#
# scheduler = BackgroundScheduler()
# scheduler.add_job(run_clone_job, trigger='cron', hour=8, minute=0)
# scheduler.start()
#
# This runs the clone job in the background every day at 8AM
# without blocking your Flask server.
# ─────────────────────────────────────────────


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PriceWise Clone Job")
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run on a daily schedule instead of once"
    )
    args = parser.parse_args()

    if args.schedule:
        run_scheduled()
    else:
        run_clone_job()