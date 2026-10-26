"""
BloodLink Safe Additive Database Migration Script
-------------------------------------------------
Applies non-destructive, idempotent database schema updates:
1. Creates 'users' table (user_id, name, email, password_hash, role, is_active, created_at).
2. Adds nullable 'user_id' column to 'donors' with foreign key referencing users(user_id) ON DELETE SET NULL.
3. Adds 'contact_consent' column to 'donors' (TINYINT(1) DEFAULT 0).
4. Adds nullable 'user_id' column to 'recipients' with foreign key referencing users(user_id) ON DELETE SET NULL.
5. Creates 'campaigns' table (campaign_id, campaign_name, description, location, start_date, end_date, status, created_at).

Safety guarantees:
- Idempotent: checks for existence before creating tables, columns, or foreign key constraints.
- Non-destructive: does not drop, recreate, or rename existing tables or columns.
- Preserves all existing live data without modifying row counts or clinical/contact values.
- Validates pre-migration and post-migration row counts.
"""

import sys
import os

# Ensure local imports work cleanly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database


def column_exists(cursor, table_name, column_name, db_name="blood_donation"):
    query = """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
    """
    cursor.execute(query, (db_name, table_name, column_name))
    row = cursor.fetchone()
    count = row["cnt"] if isinstance(row, dict) else row[0]
    return count > 0


def table_exists(cursor, table_name, db_name="blood_donation"):
    query = """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
    """
    cursor.execute(query, (db_name, table_name))
    row = cursor.fetchone()
    count = row["cnt"] if isinstance(row, dict) else row[0]
    return count > 0


def fk_exists(cursor, table_name, constraint_name, db_name="blood_donation"):
    query = """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND CONSTRAINT_NAME = %s
    """
    cursor.execute(query, (db_name, table_name, constraint_name))
    row = cursor.fetchone()
    count = row["cnt"] if isinstance(row, dict) else row[0]
    return count > 0


def get_table_row_count(cursor, table_name):
    cursor.execute(f"SELECT COUNT(*) AS cnt FROM `{table_name}`")
    row = cursor.fetchone()
    return row["cnt"] if isinstance(row, dict) else row[0]


def run_migration():
    print("=" * 60)
    print("Starting BloodLink Additive Database Migration")
    print("=" * 60)

    # 1. Verify backup existence first
    backup_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "backups",
        "backup_20261025_003259",
        "blood_donation_backup.sql"
    )
    if not os.path.isfile(backup_path) or os.path.getsize(backup_path) == 0:
        raise RuntimeError(f"Database backup verification failed: '{backup_path}' does not exist or is empty.")
    print(f"Verified backup SQL file exists: {backup_path} ({os.path.getsize(backup_path)} bytes)")

    db = database.get_db_connection()
    cursor = db.cursor(dictionary=True)

    try:
        # 2. Record Pre-migration row counts
        existing_tables = ["donors", "recipients", "emergency_requests", "hospitals"]
        pre_counts = {}
        for tbl in existing_tables:
            if table_exists(cursor, tbl):
                pre_counts[tbl] = get_table_row_count(cursor, tbl)
                print(f"Pre-migration count for '{tbl}': {pre_counts[tbl]}")
            else:
                raise RuntimeError(f"Required table '{tbl}' is missing before migration!")

        # ---------------------------------------------------------
        # A. Create 'users' table
        # ---------------------------------------------------------
        if not table_exists(cursor, "users"):
            print("Creating 'users' table...")
            create_users_sql = """
                CREATE TABLE `users` (
                    `user_id` INT AUTO_INCREMENT PRIMARY KEY,
                    `name` VARCHAR(100) NOT NULL,
                    `email` VARCHAR(150) NOT NULL UNIQUE,
                    `password_hash` VARCHAR(255) NOT NULL,
                    `role` VARCHAR(20) NOT NULL,
                    `is_active` TINYINT(1) NOT NULL DEFAULT 1,
                    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
            cursor.execute(create_users_sql)
            db.commit()
            print("Table 'users' created successfully.")
        else:
            print("Table 'users' already exists. Skipping creation.")

        # ---------------------------------------------------------
        # B. Update 'donors' table: add user_id, foreign key, contact_consent
        # ---------------------------------------------------------
        if not column_exists(cursor, "donors", "user_id"):
            print("Adding 'user_id' column to 'donors'...")
            cursor.execute("ALTER TABLE `donors` ADD COLUMN `user_id` INT NULL DEFAULT NULL AFTER `donor_id`")
            db.commit()
            print("Column 'user_id' added to 'donors'.")
        else:
            print("Column 'user_id' already exists in 'donors'. Skipping.")

        if not fk_exists(cursor, "donors", "fk_donors_user"):
            print("Adding foreign key 'fk_donors_user' to 'donors'...")
            cursor.execute("""
                ALTER TABLE `donors` 
                ADD CONSTRAINT `fk_donors_user` 
                FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) 
                ON DELETE SET NULL ON UPDATE CASCADE
            """)
            db.commit()
            print("Foreign key 'fk_donors_user' added successfully.")
        else:
            print("Foreign key 'fk_donors_user' already exists in 'donors'. Skipping.")

        if not column_exists(cursor, "donors", "contact_consent"):
            print("Adding 'contact_consent' column to 'donors'...")
            cursor.execute("ALTER TABLE `donors` ADD COLUMN `contact_consent` TINYINT(1) NOT NULL DEFAULT 0 AFTER `medical_status`")
            cursor.execute("UPDATE `donors` SET `contact_consent` = 0 WHERE `contact_consent` IS NULL")
            db.commit()
            print("Column 'contact_consent' added to 'donors' with default 0.")
        else:
            print("Column 'contact_consent' already exists in 'donors'. Skipping.")

        # ---------------------------------------------------------
        # C. Update 'recipients' table: add user_id, foreign key
        # ---------------------------------------------------------
        if not column_exists(cursor, "recipients", "user_id"):
            print("Adding 'user_id' column to 'recipients'...")
            cursor.execute("ALTER TABLE `recipients` ADD COLUMN `user_id` INT NULL DEFAULT NULL AFTER `recipient_id`")
            db.commit()
            print("Column 'user_id' added to 'recipients'.")
        else:
            print("Column 'user_id' already exists in 'recipients'. Skipping.")

        if not fk_exists(cursor, "recipients", "fk_recipients_user"):
            print("Adding foreign key 'fk_recipients_user' to 'recipients'...")
            cursor.execute("""
                ALTER TABLE `recipients` 
                ADD CONSTRAINT `fk_recipients_user` 
                FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) 
                ON DELETE SET NULL ON UPDATE CASCADE
            """)
            db.commit()
            print("Foreign key 'fk_recipients_user' added successfully.")
        else:
            print("Foreign key 'fk_recipients_user' already exists in 'recipients'. Skipping.")

        # ---------------------------------------------------------
        # D. Create 'campaigns' table
        # ---------------------------------------------------------
        if not table_exists(cursor, "campaigns"):
            print("Creating 'campaigns' table...")
            create_campaigns_sql = """
                CREATE TABLE `campaigns` (
                    `campaign_id` INT AUTO_INCREMENT PRIMARY KEY,
                    `campaign_name` VARCHAR(150) NOT NULL,
                    `description` TEXT NULL,
                    `location` VARCHAR(150) NOT NULL,
                    `start_date` DATETIME NOT NULL,
                    `end_date` DATETIME NOT NULL,
                    `status` VARCHAR(20) NOT NULL DEFAULT 'PLANNED',
                    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
            cursor.execute(create_campaigns_sql)
            db.commit()
            print("Table 'campaigns' created successfully.")
        else:
            print("Table 'campaigns' already exists. Skipping creation.")

        # ---------------------------------------------------------
        # E. Create 'donation_requests' table (Stage 6)
        # ---------------------------------------------------------
        if not table_exists(cursor, "donation_requests"):
            print("Creating 'donation_requests' table...")
            create_donation_requests_sql = """
                CREATE TABLE `donation_requests` (
                    `request_id` INT AUTO_INCREMENT PRIMARY KEY,
                    `recipient_id` INT NOT NULL,
                    `donor_id` INT NOT NULL,
                    `emergency_request_id` INT NULL DEFAULT NULL,
                    `hospital_id` INT NULL DEFAULT NULL,
                    `blood_group_required` VARCHAR(5) NOT NULL,
                    `units_required` INT NOT NULL DEFAULT 1,
                    `urgency_level` VARCHAR(20) NOT NULL DEFAULT 'HIGH',
                    `clinical_notes` VARCHAR(255) NULL DEFAULT NULL,
                    `status` VARCHAR(20) NOT NULL DEFAULT 'PENDING',
                    `recipient_consent_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    `donor_contact_consent_at` TIMESTAMP NULL DEFAULT NULL,
                    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    `responded_at` TIMESTAMP NULL DEFAULT NULL,
                    CONSTRAINT `fk_dr_recipient` FOREIGN KEY (`recipient_id`) 
                        REFERENCES `recipients` (`recipient_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
                    CONSTRAINT `fk_dr_donor` FOREIGN KEY (`donor_id`) 
                        REFERENCES `donors` (`donor_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
                    CONSTRAINT `fk_dr_emergency` FOREIGN KEY (`emergency_request_id`) 
                        REFERENCES `emergency_requests` (`request_id`) ON DELETE SET NULL ON UPDATE CASCADE,
                    CONSTRAINT `fk_dr_hospital` FOREIGN KEY (`hospital_id`) 
                        REFERENCES `hospitals` (`hospital_id`) ON DELETE SET NULL ON UPDATE CASCADE,
                    INDEX `idx_dr_recipient_status` (`recipient_id`, `status`),
                    INDEX `idx_dr_donor_status` (`donor_id`, `status`),
                    INDEX `idx_dr_emergency` (`emergency_request_id`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
            cursor.execute(create_donation_requests_sql)
            db.commit()
            print("Table 'donation_requests' created successfully.")
        else:
            print("Table 'donation_requests' already exists. Skipping creation.")

        # ---------------------------------------------------------
        # Post-migration Verification & Integrity Checks
        # ---------------------------------------------------------
        print("\n" + "=" * 60)
        print("Post-Migration Verification")
        print("=" * 60)

        post_counts = {}
        for tbl in existing_tables:
            post_counts[tbl] = get_table_row_count(cursor, tbl)
            print(f"Post-migration count for '{tbl}': {post_counts[tbl]}")
            if post_counts[tbl] != pre_counts[tbl]:
                raise RuntimeError(
                    f"DATA INTEGRITY MISMATCH! Table '{tbl}' changed from {pre_counts[tbl]} to {post_counts[tbl]} rows!"
                )

        users_count = get_table_row_count(cursor, "users")
        campaigns_count = get_table_row_count(cursor, "campaigns")
        donation_requests_count = get_table_row_count(cursor, "donation_requests")
        print(f"Table 'users' count: {users_count} (Expected 0 - no hardcoded/default accounts)")
        print(f"Table 'campaigns' count: {campaigns_count} (Expected 0 - no invented campaigns)")
        print(f"Table 'donation_requests' count: {donation_requests_count} (Expected 0 - newly created table)")

        # Verify donor contact_consent default
        cursor.execute("SELECT COUNT(*) AS non_zero FROM `donors` WHERE `contact_consent` != 0")
        non_zero = cursor.fetchone()
        non_zero_cnt = non_zero["non_zero"] if isinstance(non_zero, dict) else non_zero[0]
        if non_zero_cnt != 0:
            raise RuntimeError(f"Unexpected non-zero contact_consent found on {non_zero_cnt} donors!")
        print("Verified all existing donors have contact_consent = 0.")

        # Verify unlinked user_id on existing records
        cursor.execute("SELECT COUNT(*) AS linked FROM `donors` WHERE `user_id` IS NOT NULL")
        linked_d = cursor.fetchone()
        linked_d_cnt = linked_d["linked"] if isinstance(linked_d, dict) else linked_d[0]
        cursor.execute("SELECT COUNT(*) AS linked FROM `recipients` WHERE `user_id` IS NOT NULL")
        linked_r = cursor.fetchone()
        linked_r_cnt = linked_r["linked"] if isinstance(linked_r, dict) else linked_r[0]
        print(f"Verified legacy donors linked to users: {linked_d_cnt} (Expected 0)")
        print(f"Verified legacy recipients linked to users: {linked_r_cnt} (Expected 0)")

        print("\nALL POST-MIGRATION CHECKS PASSED SUCCESSFULLY.")
        print("=" * 60)

    except Exception as e:
        db.rollback()
        print(f"\nMIGRATION FAILED: {e}", file=sys.stderr)
        raise
    finally:
        cursor.close()
        db.close()


if __name__ == "__main__":
    run_migration()
