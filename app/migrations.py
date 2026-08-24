"""Lightweight startup migrations for columns added after initial deploy.

Each migration is idempotent — it uses IF NOT EXISTS / DO NOTHING so it is
safe to run on every startup regardless of whether the column already exists.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Individual migrations — add new ones at the bottom only
# ---------------------------------------------------------------------------

_MIGRATIONS = [
    # 001 — enquiry pipeline columns (added after initial PostgreSQL deploy)
    (
        "enquiries.stage",
        """
        ALTER TABLE enquiries
        ADD COLUMN IF NOT EXISTS stage VARCHAR(30) DEFAULT NULL;
        """,
    ),
    (
        "enquiries.assigned_employee_id",
        """
        ALTER TABLE enquiries
        ADD COLUMN IF NOT EXISTS assigned_employee_id INTEGER
            REFERENCES employees(id) ON DELETE SET NULL DEFAULT NULL;
        """,
    ),
    (
        "enquiries.stage_history",
        """
        ALTER TABLE enquiries
        ADD COLUMN IF NOT EXISTS stage_history TEXT DEFAULT NULL;
        """,
    ),
    # 002 — ensure users.whatsapp_number exists (CEO Control Tower needs it)
    (
        "users.whatsapp_number",
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS whatsapp_number VARCHAR(20) DEFAULT NULL;
        """,
    ),
    # 003 — smart checkpoints (sub-tasks) for tasks
    (
        "tasks.checkpoints",
        """
        ALTER TABLE tasks
        ADD COLUMN IF NOT EXISTS checkpoints TEXT DEFAULT NULL;
        """,
    ),
    # 004 — tiered billing columns for companies
    (
        "companies.subscription_level",
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS subscription_level VARCHAR(50) NOT NULL DEFAULT 'basic';
        """,
    ),
    (
        "companies.is_premium",
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS is_premium BOOLEAN NOT NULL DEFAULT false;
        """,
    ),
    (
        "companies.tasks_created_count",
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS tasks_created_count INTEGER NOT NULL DEFAULT 0;
        """,
    ),
    # 005 — cleanup junk tasks created by CEO Control Tower bug (safe to re-run)
    (
        "cleanup.junk_ceo_tasks",
        """
        DELETE FROM tasks
        WHERE title ILIKE '%Inform Aaron about%'
           OR description ILIKE '%Tell Aaron that the deadline%';
        """,
    ),
    # 006 — owner account premium upgrade (whatsapp_number = '+919150016161')
    (
        "companies.owner_premium",
        """
        UPDATE companies
        SET is_premium = true, subscription_level = 'premium'
        WHERE id = (
            SELECT company_id FROM users
            WHERE whatsapp_number = '+919150016161'
            LIMIT 1
        );
        """,
    ),
    # 007 — premium + counter reset via role lookup (reliable fallback when
    #        whatsapp_number was not set in the DB — migration 006 may have hit 0 rows)
    (
        "companies.ceo_role_premium",
        """
        UPDATE companies
        SET is_premium = true, subscription_level = 'premium', tasks_created_count = 0
        WHERE id IN (
            SELECT DISTINCT company_id FROM users WHERE role = 'ceo'
        );
        """,
    ),
    # 008 — normalize subscription_level to 'free' for non-premium companies
    #        (old default was 'basic'; new tier vocabulary is free/basic/premium)
    (
        "companies.normalize_free_tier",
        """
        UPDATE companies
        SET subscription_level = 'free'
        WHERE subscription_level = 'basic' AND is_premium = false;
        """,
    ),
    # 009 — tiered billing: premium expiry timestamp
    (
        "companies.tier_expires_at",
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS tier_expires_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;
        """,
    ),
    # 010 — tiered billing: JSON list of paid project IDs (basic per-project)
    (
        "companies.projects_paid",
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS projects_paid TEXT DEFAULT NULL;
        """,
    ),
    # 011 — projects table (created by create_all; this migration is a safety net
    #        for existing deployments where the table may not yet exist)
    (
        "projects.table",
        """
        CREATE TABLE IF NOT EXISTS projects (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        """,
    ),
    # 012 — project_id FK on tasks (for per-project billing grouping)
    (
        "tasks.project_id",
        """
        ALTER TABLE tasks
        ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL DEFAULT NULL;
        """,
    ),
    # 013 — 7-day free trial: trial_ends_at column on companies
    (
        "companies.trial_ends_at",
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;
        """,
    ),
    # 014 — 7-day free trial: backfill existing companies (created_at + 7 days)
    (
        "companies.trial_ends_at_backfill",
        """
        UPDATE companies
        SET trial_ends_at = created_at + INTERVAL '7 days'
        WHERE trial_ends_at IS NULL;
        """,
    ),
    # 015 — email OTP verification columns on users
    (
        "users.is_verified",
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT FALSE;
        """,
    ),
    (
        "users.otp_code",
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS otp_code VARCHAR(6) DEFAULT NULL;
        """,
    ),
    (
        "users.otp_expires_at",
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS otp_expires_at TIMESTAMP DEFAULT NULL;
        """,
    ),
    # 016 — backfill: existing users (signed up before OTP) are already verified
    (
        "users.is_verified_backfill",
        """
        UPDATE users SET is_verified = TRUE WHERE is_verified = FALSE;
        """,
    ),
    # 017 — Cashfree payment gateway: order ID and payment status columns
    (
        "companies.cashfree_order_id",
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS cashfree_order_id VARCHAR(255) DEFAULT NULL;
        """,
    ),
    (
        "companies.payment_status",
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS payment_status VARCHAR(50) NOT NULL DEFAULT 'unpaid';
        """,
    ),
    # 018 — employee↔manager message threads per task
    (
        "task_messages.table",
        """
        CREATE TABLE IF NOT EXISTS task_messages (
            id SERIAL PRIMARY KEY,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            sender VARCHAR(20) NOT NULL,
            message TEXT NOT NULL,
            acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        """,
    ),
    # 019 — task_updates table (employee UPDATE <text> messages saved per task)
    (
        "task_updates.table",
        """
        CREATE TABLE IF NOT EXISTS task_updates (
            id SERIAL PRIMARY KEY,
            task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
            employee_id INTEGER,
            update_text TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        """,
    ),
    # 020 — company_settings table (per-company reminder configuration)
    (
        "company_settings.table",
        """
        CREATE TABLE IF NOT EXISTS company_settings (
            id SERIAL PRIMARY KEY,
            company_id INTEGER UNIQUE REFERENCES companies(id) ON DELETE CASCADE,
            morning_pulse_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            morning_pulse_time VARCHAR(5) NOT NULL DEFAULT '09:00',
            reminder_frequency_hours INTEGER NOT NULL DEFAULT 4,
            reminders_enabled BOOLEAN NOT NULL DEFAULT TRUE
        );
        """,
    ),
    # 021 — fix CEO phone linked to wrong company_id
    #        The user with whatsapp_number '+919150016161' was registered under
    #        company_id=14 (a stale signup row) but all real data lives in company_id=1.
    #        Re-point their company_id so get_ceo_user() resolves the right company,
    #        then delete any remaining duplicate users in company 14 with no real data.
    (
        "users.fix_ceo_company",
        """
        UPDATE users
        SET company_id = 1
        WHERE whatsapp_number = '+919150016161'
          AND company_id != 1;
        """,
    ),
    (
        "users.drop_orphan_company14_users",
        """
        DELETE FROM users
        WHERE company_id = 14
          AND whatsapp_number IS NULL
          AND email NOT IN (
              SELECT email FROM users WHERE company_id = 1 AND email IS NOT NULL
          );
        """,
    ),
    # 022 — add pending_confirmation value to PostgreSQL taskstatus enum
    #        IF NOT EXISTS is supported since PostgreSQL 9.6 — safe to re-run.
    (
        "022_taskstatus_pending_confirmation",
        """
        ALTER TYPE taskstatus ADD VALUE IF NOT EXISTS 'pending_confirmation';
        """,
    ),
    # 023 — per-task reminder schedule (hours)
    (
        "tasks.reminder_interval_hours",
        """
        ALTER TABLE tasks
        ADD COLUMN IF NOT EXISTS reminder_interval_hours INTEGER DEFAULT 4;
        """,
    ),
    # 024 — task edit tracking
    (
        "tasks.edited_at",
        """
        ALTER TABLE tasks
        ADD COLUMN IF NOT EXISTS edited_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;
        """,
    ),
    # 025 — notifications table (in-app inbox for employee activity)
    (
        "notifications.table",
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
            employee_id INTEGER,
            employee_name VARCHAR(255),
            message TEXT NOT NULL,
            type VARCHAR(20) NOT NULL,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        """,
    ),
    # 026 — gender field for employee character avatars
    (
        "employees.gender",
        """
        ALTER TABLE employees
        ADD COLUMN IF NOT EXISTS gender VARCHAR(10) NOT NULL DEFAULT 'neutral';
        """,
    ),
    # 027 — role field for employee cards (job title, editable from dashboard)
    (
        "employees.role",
        """
        ALTER TABLE employees
        ADD COLUMN IF NOT EXISTS role VARCHAR(255) DEFAULT NULL;
        """,
    ),
    # 028 — departments/teams table (multi-business support)
    (
        "departments.table",
        """
        CREATE TABLE IF NOT EXISTS departments (
            id SERIAL PRIMARY KEY,
            company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
            name VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW()
        );
        """,
    ),
    # 029 — department_id FK on employees (assign a team member to a department)
    (
        "employees.department_id",
        """
        ALTER TABLE employees
        ADD COLUMN IF NOT EXISTS department_id INTEGER
            REFERENCES departments(id) ON DELETE SET NULL DEFAULT NULL;
        """,
    ),
    # 030 — department_id FK on tasks (tag/filter tasks by team)
    (
        "tasks.department_id",
        """
        ALTER TABLE tasks
        ADD COLUMN IF NOT EXISTS department_id INTEGER
            REFERENCES departments(id) ON DELETE SET NULL DEFAULT NULL;
        """,
    ),
    # 031 — OTP verification removed: new users are verified immediately.
    #        Flip the column default and backfill any existing unverified
    #        rows (old signups that never finished the OTP flow).
    (
        "users.is_verified_default_true",
        """
        ALTER TABLE users
        ALTER COLUMN is_verified SET DEFAULT TRUE;
        """,
    ),
    (
        "users.is_verified_backfill_no_otp",
        """
        UPDATE users SET is_verified = TRUE WHERE is_verified = FALSE;
        """,
    ),
    # 032 — case-insensitive unique index on email. Backstops the app-level
    #        lowercasing in auth_routes so two accounts can't differ only by
    #        letter case. This does NOT normalize existing rows — run
    #        `normalize_emails.py --apply` first on any DB that may hold
    #        mixed-case duplicates. If a case-variant duplicate still exists the
    #        CREATE fails and is logged/skipped (run_migrations swallows it),
    #        and it will succeed automatically on the next startup once the data
    #        is clean. Deliberately not paired with a blind
    #        `UPDATE ... SET email = lower(email)`: colliding rows must be
    #        surfaced for a human, never silently merged.
    (
        "032_users_email_lower_unique_index",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email_lower
        ON users (lower(email));
        """,
    ),
    # ---------------------------------------------------------------------
    # 033 -- Real-estate vertical (DealKnot merge).
    #
    # Everything below is inert for existing accounts: `companies.vertical`
    # defaults to 'generic', and every real-estate route, nav item and
    # notification is gated on vertical = 'real_estate'. The new tables simply
    # stay empty for generic companies.
    # ---------------------------------------------------------------------
    (
        "033_companies.vertical",
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS vertical VARCHAR(30) NOT NULL DEFAULT 'generic';
        """,
    ),
    (
        "033_buyers.table",
        """
        CREATE TABLE IF NOT EXISTS buyers (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            phone VARCHAR(30),
            dial VARCHAR(10) NOT NULL DEFAULT '+91',
            country VARCHAR(2) NOT NULL DEFAULT 'IN',
            areas VARCHAR(500) NOT NULL DEFAULT '',
            property_type VARCHAR(30) NOT NULL DEFAULT 'apt_resale',
            division VARCHAR(10) NOT NULL DEFAULT 'sales',
            currency VARCHAR(3) NOT NULL DEFAULT 'INR',
            budget_min NUMERIC(18,2) NOT NULL DEFAULT 0,
            budget_max NUMERIC(18,2) NOT NULL DEFAULT 0,
            period VARCHAR(10) NOT NULL DEFAULT 'monthly',
            radius_km NUMERIC(5,2) NOT NULL DEFAULT 5,
            label VARCHAR(10) NOT NULL DEFAULT 'active',
            referred_by VARCHAR(255),
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        """,
    ),
    (
        "033_buyers.company_idx",
        "CREATE INDEX IF NOT EXISTS ix_buyers_company_id ON buyers (company_id);",
    ),
    (
        "033_sellers.table",
        """
        CREATE TABLE IF NOT EXISTS sellers (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            phone VARCHAR(30),
            dial VARCHAR(10) NOT NULL DEFAULT '+91',
            country VARCHAR(2) NOT NULL DEFAULT 'IN',
            areas VARCHAR(500) NOT NULL DEFAULT '',
            property_type VARCHAR(30) NOT NULL DEFAULT 'apt_resale',
            division VARCHAR(10) NOT NULL DEFAULT 'sales',
            currency VARCHAR(3) NOT NULL DEFAULT 'INR',
            price NUMERIC(18,2) NOT NULL DEFAULT 0,
            period VARCHAR(10) NOT NULL DEFAULT 'monthly',
            label VARCHAR(10) NOT NULL DEFAULT 'active',
            referred_by VARCHAR(255),
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        """,
    ),
    (
        "033_sellers.company_idx",
        "CREATE INDEX IF NOT EXISTS ix_sellers_company_id ON sellers (company_id);",
    ),
    (
        "033_listings.table",
        """
        CREATE TABLE IF NOT EXISTS listings (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            seller_id INTEGER REFERENCES sellers(id) ON DELETE SET NULL,
            title VARCHAR(255) NOT NULL,
            area VARCHAR(255) NOT NULL DEFAULT '',
            property_type VARCHAR(30) NOT NULL DEFAULT 'apt_resale',
            division VARCHAR(10) NOT NULL DEFAULT 'sales',
            price NUMERIC(18,2) NOT NULL DEFAULT 0,
            currency VARCHAR(3) NOT NULL DEFAULT 'INR',
            period VARCHAR(10) NOT NULL DEFAULT 'monthly',
            bedrooms INTEGER,
            bathrooms INTEGER,
            area_sqft NUMERIC(12,2),
            status VARCHAR(20) NOT NULL DEFAULT 'available',
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        """,
    ),
    (
        "033_listings.company_idx",
        "CREATE INDEX IF NOT EXISTS ix_listings_company_id ON listings (company_id);",
    ),
    (
        "033_matches.table",
        """
        CREATE TABLE IF NOT EXISTS matches (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            buyer_id INTEGER NOT NULL REFERENCES buyers(id) ON DELETE CASCADE,
            seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
            match_type VARCHAR(10) NOT NULL DEFAULT 'exact',
            distance_km NUMERIC(6,2) NOT NULL DEFAULT 0,
            price_match_kind VARCHAR(10) NOT NULL DEFAULT 'exact',
            score INTEGER NOT NULL DEFAULT 0,
            matched_buyer_area VARCHAR(255),
            matched_seller_area VARCHAR(255),
            connected BOOLEAN NOT NULL DEFAULT FALSE,
            notified_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_matches_company_buyer_seller UNIQUE (company_id, buyer_id, seller_id)
        );
        """,
    ),
    (
        "033_matches.company_idx",
        "CREATE INDEX IF NOT EXISTS ix_matches_company_id ON matches (company_id);",
    ),
    (
        "033_commissions.table",
        """
        CREATE TABLE IF NOT EXISTS commissions (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            enquiry_id INTEGER REFERENCES enquiries(id) ON DELETE SET NULL,
            deal_value NUMERIC(18,2) NOT NULL DEFAULT 0,
            commission_percent NUMERIC(6,3) NOT NULL DEFAULT 0,
            commission_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
            split_percent NUMERIC(6,3) NOT NULL DEFAULT 100,
            source VARCHAR(20) NOT NULL DEFAULT 'both_sides',
            currency VARCHAR(3) NOT NULL DEFAULT 'INR',
            status VARCHAR(20) NOT NULL DEFAULT 'Pending',
            expected_date TIMESTAMP WITH TIME ZONE,
            received_date TIMESTAMP WITH TIME ZONE,
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        """,
    ),
    (
        "033_commissions.company_idx",
        "CREATE INDEX IF NOT EXISTS ix_commissions_company_id ON commissions (company_id);",
    ),
    # Link the existing enquiries pipeline to real-estate leads. Both stay NULL
    # for generic companies, so the existing Enquiries board is unaffected.
    (
        "033_enquiries.buyer_id",
        """
        ALTER TABLE enquiries
        ADD COLUMN IF NOT EXISTS buyer_id INTEGER
            REFERENCES buyers(id) ON DELETE SET NULL DEFAULT NULL;
        """,
    ),
    (
        "033_enquiries.seller_id",
        """
        ALTER TABLE enquiries
        ADD COLUMN IF NOT EXISTS seller_id INTEGER
            REFERENCES sellers(id) ON DELETE SET NULL DEFAULT NULL;
        """,
    ),
    # The two ALTERs above add the columns but not their indexes. On a fresh
    # database create_all builds `enquiries` from the model, which declares
    # index=True, so the indexes come for free -- but on an existing database
    # (which is every real deployment) create_all skips the table entirely and
    # the columns would land unindexed. These statements are what keeps an
    # upgraded schema identical to a freshly created one.
    (
        "033_enquiries.buyer_idx",
        "CREATE INDEX IF NOT EXISTS ix_enquiries_buyer_id ON enquiries (buyer_id);",
    ),
    (
        "033_enquiries.seller_idx",
        "CREATE INDEX IF NOT EXISTS ix_enquiries_seller_id ON enquiries (seller_id);",
    ),
    # ---------------------------------------------------------------------
    # 034 -- Launch Matcher (vertical = "launch_matcher").
    #
    # One table, deliberately. Investor criteria are stored; forwarded launch
    # messages are NOT -- they are parsed in memory, answered, and discarded,
    # so no forwarded text can ever be persisted.
    #
    # There is no name, phone or email column here and there must never be
    # one: an investor is identified only by the advisor's own `label`.
    #
    # Inert for every existing account: companies.vertical defaults to
    # 'generic', and "launch_matcher" is mutually exclusive with the broker
    # CRM's "real_estate", so neither vertical's routes can see the other.
    # ---------------------------------------------------------------------
    (
        "034_investor_criteria.table",
        """
        CREATE TABLE IF NOT EXISTS investor_criteria (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            label VARCHAR(80) NOT NULL,
            emirate VARCHAR(20) NOT NULL DEFAULT 'Dubai',
            areas VARCHAR(500) NOT NULL DEFAULT '',
            budget_min NUMERIC(18,2) NOT NULL DEFAULT 0,
            budget_max NUMERIC(18,2) NOT NULL DEFAULT 0,
            property_type VARCHAR(40) NOT NULL DEFAULT '',
            off_plan_or_ready VARCHAR(10) NOT NULL DEFAULT 'both',
            payment_preference VARCHAR(15) NOT NULL DEFAULT 'either',
            timeline VARCHAR(120) NOT NULL DEFAULT '',
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        """,
    ),
    (
        "034_investor_criteria.company_idx",
        "CREATE INDEX IF NOT EXISTS ix_investor_criteria_company_id "
        "ON investor_criteria (company_id);",
    ),
    # Emirate is the top-level match filter, so every matching run narrows on
    # (company_id, emirate) first. Indexed as a pair for that access path.
    (
        "034_investor_criteria.company_emirate_idx",
        "CREATE INDEX IF NOT EXISTS ix_investor_criteria_company_emirate "
        "ON investor_criteria (company_id, emirate);",
    ),
    # ---------------------------------------------------------------------
    # 035 -- investor_criteria.payment_preference (cash / payment_plan /
    #        either). Added after 034 was written, so it needs its own ALTER:
    #        on a database where 034 already created the table, the amended
    #        CREATE TABLE above is a no-op and would silently skip the column.
    # ---------------------------------------------------------------------
    (
        "035_investor_criteria.payment_preference",
        """
        ALTER TABLE investor_criteria
        ADD COLUMN IF NOT EXISTS payment_preference VARCHAR(15)
            NOT NULL DEFAULT 'either';
        """,
    ),
]


# ---------------------------------------------------------------------------
# SQLite fallbacks — the PostgreSQL migrations above use `IF NOT EXISTS`,
# `SERIAL` and `REFERENCES … ON DELETE`, which SQLite does not accept. On a
# fresh SQLite dev DB `create_all` builds every table/column from the ORM
# models, but existing SQLite DBs still need these ALTERs. SQLite ignores the
# duplicate-column error via the try/except in run_migrations().
# ---------------------------------------------------------------------------

_SQLITE_MIGRATIONS = [
    (
        "sqlite.departments.table",
        """
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER REFERENCES companies(id),
            name VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    (
        "sqlite.employees.department_id",
        "ALTER TABLE employees ADD COLUMN department_id INTEGER REFERENCES departments(id);",
    ),
    (
        "sqlite.tasks.department_id",
        "ALTER TABLE tasks ADD COLUMN department_id INTEGER REFERENCES departments(id);",
    ),
    # Mirror of migration 032 for existing SQLite dev DBs (fresh ones get this
    # index from the User model's __table_args__ via create_all). SQLite has
    # supported expression indexes since 3.9.0.
    (
        "sqlite.users.email_lower_unique_index",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email_lower ON users (lower(email));",
    ),
    # -- Real-estate vertical (migration 033) mirrored for existing SQLite dev
    #    DBs. Fresh SQLite DBs get all of this from create_all via the ORM
    #    models; these statements only matter for a dev DB created earlier.
    #    The ALTERs have no IF NOT EXISTS in SQLite -- run_migrations() swallows
    #    the duplicate-column error on re-run, which is the existing convention.
    (
        "sqlite.companies.vertical",
        "ALTER TABLE companies ADD COLUMN vertical VARCHAR(30) NOT NULL DEFAULT 'generic';",
    ),
    (
        "sqlite.buyers.table",
        """
        CREATE TABLE IF NOT EXISTS buyers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            name VARCHAR(255) NOT NULL,
            phone VARCHAR(30),
            dial VARCHAR(10) NOT NULL DEFAULT '+91',
            country VARCHAR(2) NOT NULL DEFAULT 'IN',
            areas VARCHAR(500) NOT NULL DEFAULT '',
            property_type VARCHAR(30) NOT NULL DEFAULT 'apt_resale',
            division VARCHAR(10) NOT NULL DEFAULT 'sales',
            currency VARCHAR(3) NOT NULL DEFAULT 'INR',
            budget_min NUMERIC(18,2) NOT NULL DEFAULT 0,
            budget_max NUMERIC(18,2) NOT NULL DEFAULT 0,
            period VARCHAR(10) NOT NULL DEFAULT 'monthly',
            radius_km NUMERIC(5,2) NOT NULL DEFAULT 5,
            label VARCHAR(10) NOT NULL DEFAULT 'active',
            referred_by VARCHAR(255),
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    (
        "sqlite.sellers.table",
        """
        CREATE TABLE IF NOT EXISTS sellers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            name VARCHAR(255) NOT NULL,
            phone VARCHAR(30),
            dial VARCHAR(10) NOT NULL DEFAULT '+91',
            country VARCHAR(2) NOT NULL DEFAULT 'IN',
            areas VARCHAR(500) NOT NULL DEFAULT '',
            property_type VARCHAR(30) NOT NULL DEFAULT 'apt_resale',
            division VARCHAR(10) NOT NULL DEFAULT 'sales',
            currency VARCHAR(3) NOT NULL DEFAULT 'INR',
            price NUMERIC(18,2) NOT NULL DEFAULT 0,
            period VARCHAR(10) NOT NULL DEFAULT 'monthly',
            label VARCHAR(10) NOT NULL DEFAULT 'active',
            referred_by VARCHAR(255),
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    (
        "sqlite.listings.table",
        """
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            seller_id INTEGER REFERENCES sellers(id),
            title VARCHAR(255) NOT NULL,
            area VARCHAR(255) NOT NULL DEFAULT '',
            property_type VARCHAR(30) NOT NULL DEFAULT 'apt_resale',
            division VARCHAR(10) NOT NULL DEFAULT 'sales',
            price NUMERIC(18,2) NOT NULL DEFAULT 0,
            currency VARCHAR(3) NOT NULL DEFAULT 'INR',
            period VARCHAR(10) NOT NULL DEFAULT 'monthly',
            bedrooms INTEGER,
            bathrooms INTEGER,
            area_sqft NUMERIC(12,2),
            status VARCHAR(20) NOT NULL DEFAULT 'available',
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    (
        "sqlite.matches.table",
        """
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            buyer_id INTEGER NOT NULL REFERENCES buyers(id),
            seller_id INTEGER NOT NULL REFERENCES sellers(id),
            match_type VARCHAR(10) NOT NULL DEFAULT 'exact',
            distance_km NUMERIC(6,2) NOT NULL DEFAULT 0,
            price_match_kind VARCHAR(10) NOT NULL DEFAULT 'exact',
            score INTEGER NOT NULL DEFAULT 0,
            matched_buyer_area VARCHAR(255),
            matched_seller_area VARCHAR(255),
            connected BOOLEAN NOT NULL DEFAULT 0,
            notified_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_matches_company_buyer_seller UNIQUE (company_id, buyer_id, seller_id)
        );
        """,
    ),
    (
        "sqlite.commissions.table",
        """
        CREATE TABLE IF NOT EXISTS commissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            enquiry_id INTEGER REFERENCES enquiries(id),
            deal_value NUMERIC(18,2) NOT NULL DEFAULT 0,
            commission_percent NUMERIC(6,3) NOT NULL DEFAULT 0,
            commission_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
            split_percent NUMERIC(6,3) NOT NULL DEFAULT 100,
            source VARCHAR(20) NOT NULL DEFAULT 'both_sides',
            currency VARCHAR(3) NOT NULL DEFAULT 'INR',
            status VARCHAR(20) NOT NULL DEFAULT 'Pending',
            expected_date TIMESTAMP,
            received_date TIMESTAMP,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    (
        "sqlite.enquiries.buyer_id",
        "ALTER TABLE enquiries ADD COLUMN buyer_id INTEGER REFERENCES buyers(id);",
    ),
    (
        "sqlite.enquiries.seller_id",
        "ALTER TABLE enquiries ADD COLUMN seller_id INTEGER REFERENCES sellers(id);",
    ),
    (
        "sqlite.enquiries.buyer_idx",
        "CREATE INDEX IF NOT EXISTS ix_enquiries_buyer_id ON enquiries (buyer_id);",
    ),
    (
        "sqlite.enquiries.seller_idx",
        "CREATE INDEX IF NOT EXISTS ix_enquiries_seller_id ON enquiries (seller_id);",
    ),
    # -- Launch Matcher (migration 034) mirrored for existing SQLite dev DBs.
    #    Fresh SQLite DBs get the table from create_all via the ORM model; the
    #    indexes are repeated here because an upgraded DB that already has the
    #    table would not otherwise receive them.
    (
        "sqlite.investor_criteria.table",
        """
        CREATE TABLE IF NOT EXISTS investor_criteria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            label VARCHAR(80) NOT NULL,
            emirate VARCHAR(20) NOT NULL DEFAULT 'Dubai',
            areas VARCHAR(500) NOT NULL DEFAULT '',
            budget_min NUMERIC(18,2) NOT NULL DEFAULT 0,
            budget_max NUMERIC(18,2) NOT NULL DEFAULT 0,
            property_type VARCHAR(40) NOT NULL DEFAULT '',
            off_plan_or_ready VARCHAR(10) NOT NULL DEFAULT 'both',
            payment_preference VARCHAR(15) NOT NULL DEFAULT 'either',
            timeline VARCHAR(120) NOT NULL DEFAULT '',
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    (
        "sqlite.investor_criteria.company_idx",
        "CREATE INDEX IF NOT EXISTS ix_investor_criteria_company_id "
        "ON investor_criteria (company_id);",
    ),
    (
        "sqlite.investor_criteria.company_emirate_idx",
        "CREATE INDEX IF NOT EXISTS ix_investor_criteria_company_emirate "
        "ON investor_criteria (company_id, emirate);",
    ),
    # Mirror of migration 035. SQLite has no ADD COLUMN IF NOT EXISTS; the
    # duplicate-column error is swallowed by run_migrations on re-run, which is
    # this file's established convention.
    (
        "sqlite.investor_criteria.payment_preference",
        "ALTER TABLE investor_criteria ADD COLUMN payment_preference "
        "VARCHAR(15) NOT NULL DEFAULT 'either';",
    ),
]


async def run_migrations(engine: AsyncEngine) -> None:
    """Run all pending column migrations on startup."""
    is_sqlite = engine.dialect.name == "sqlite"
    migrations = _SQLITE_MIGRATIONS if is_sqlite else _MIGRATIONS

    async with engine.begin() as conn:
        for name, sql in migrations:
            try:
                await conn.execute(text(sql.strip()))
                logger.info("Migration OK: %s", name)
            except Exception as exc:
                # Log but don't crash — column may already exist on this driver
                logger.warning("Migration skipped (%s): %s", name, exc)
