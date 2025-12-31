"""
Scheduled tasks for data retention and cleanup.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import os
import asyncio

from storage import list_user_files, delete_user_file, get_all_user_ids

# Configuration
DATA_RETENTION_DAYS = int(os.getenv("DATA_RETENTION_DAYS", "60"))


async def cleanup_old_files():
    """
    Delete files and reports older than the retention period.
    
    This function runs daily and removes:
    - Excel files
    - Metadata
    - Analysis reports
    
    for all files older than DATA_RETENTION_DAYS.
    """
    print(f"🧹 Starting data retention cleanup (retention: {DATA_RETENTION_DAYS} days)...")

    try:
        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=DATA_RETENTION_DAYS)
        cutoff_date_str = cutoff_date.isoformat()

        deleted_count = 0
        error_count = 0

        # Get all user IDs
        user_ids = await get_all_user_ids()
        print(f"📋 Checking files for {len(user_ids)} users...")

        # Check files for each user
        for user_id in user_ids:
            try:
                # Get all files for this user
                files = await list_user_files(user_id)

                # Delete files older than retention period
                for file_metadata in files:
                    upload_date_str = file_metadata.get("upload_date", "")

                    if upload_date_str < cutoff_date_str:
                        file_id = file_metadata["file_id"]
                        filename = file_metadata.get("filename", "unknown")

                        success = await delete_user_file(user_id, file_id)

                        if success:
                            deleted_count += 1
                            print(
                                f"  ✅ Deleted: {filename} (uploaded: {upload_date_str[:10]})"
                            )
                        else:
                            error_count += 1
                            print(f"  ❌ Failed to delete: {filename}")

            except Exception as e:
                print(f"  ⚠️  Error processing files for user {user_id}: {e}")
                error_count += 1

        # Summary
        print(f"\n📊 Cleanup Summary:")
        print(f"  - Files deleted: {deleted_count}")
        print(f"  - Errors: {error_count}")
        print(f"  - Retention period: {DATA_RETENTION_DAYS} days")
        print(f"  - Cutoff date: {cutoff_date_str[:10]}")
        print(f"✅ Data retention cleanup completed\n")

    except Exception as e:
        print(f"❌ Error during cleanup: {e}")


def run_cleanup_sync():
    """Synchronous wrapper for async cleanup function."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(cleanup_old_files())
    finally:
        loop.close()


def start_scheduler():
    """
    Start the background scheduler for data retention.
    
    The cleanup job runs daily at midnight UTC.
    """
    scheduler = BackgroundScheduler()

    # Schedule daily cleanup at midnight UTC
    scheduler.add_job(
        run_cleanup_sync,
        trigger=CronTrigger(hour=0, minute=0),  # Daily at 00:00 UTC
        id="data_retention_cleanup",
        name="Data Retention Cleanup",
        replace_existing=True,
    )

    # Optional: Run cleanup on startup (uncomment if desired)
    # scheduler.add_job(
    #     run_cleanup_sync,
    #     id="startup_cleanup",
    #     name="Startup Cleanup",
    # )

    scheduler.start()
    print(f"⏰ Scheduler started - Cleanup runs daily at 00:00 UTC")
    print(f"📅 Data retention period: {DATA_RETENTION_DAYS} days")


if __name__ == "__main__":
    # For testing: run cleanup immediately
    print("Running cleanup test...")
    run_cleanup_sync()
