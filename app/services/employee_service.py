"""Employee service — lookup and creation helpers."""

import logging
import re

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee

logger = logging.getLogger(__name__)

# Pattern to detect phone-number-style names (e.g. "+919150016161")
_PHONE_NAME_RE = re.compile(r"^[\+\d\s\-()]+$")


def _is_phone_name(name: str) -> bool:
    """Return True if the name looks like a phone number, not a real name."""
    return bool(_PHONE_NAME_RE.match(name.strip()))


def normalize_phone_number(phone_number: str) -> str:
    """Normalize phone number to E.164-like format for India (+91).

    Rules:
    - Remove spaces/hyphens/parentheses.
    - If it starts with "+", keep as-is after cleanup.
    - If it is a 10-digit local number, prefix with "+91".
    - Otherwise return the cleaned value unchanged.
    """
    cleaned = re.sub(r"[\s\-()]", "", phone_number.strip())

    if cleaned.startswith("+"):
        return cleaned
    if re.fullmatch(r"\d{10}", cleaned):
        return f"+91{cleaned}"
    return cleaned


async def get_or_create_employee(
    db: AsyncSession,
    name: str,
    phone_number: str | None = None,
    company_id: int | None = None,
) -> Employee:
    """Find an employee by name (case-insensitive). Create if not found.

    Also checks by phone number first to avoid creating duplicates when
    an employee was auto-registered with a placeholder name.
    """
    # Step 1: Check by phone number first to catch auto-registered records
    if phone_number:
        phone_stmt = select(Employee).where(Employee.phone_number == phone_number)
        phone_result = await db.execute(phone_stmt)
        phone_employee = phone_result.scalars().first()

        if phone_employee:
            # If found by phone but has a placeholder name, update to real name
            if _is_phone_name(phone_employee.name) or phone_employee.name.startswith("Employee_"):
                old_name = phone_employee.name
                phone_employee.name = name.strip()
                await db.flush()
                logger.info(
                    "Updated employee name: '%s' → '%s' (id=%s)",
                    old_name, phone_employee.name, phone_employee.id,
                )
            return phone_employee

    # Step 2: Check by name (case-insensitive)
    name_stmt = select(Employee).where(
        sa_func.lower(Employee.name) == name.strip().lower()
    )
    name_result = await db.execute(name_stmt)
    employee = name_result.scalars().first()

    if employee:
        # Attach phone if missing
        if phone_number and not employee.phone_number:
            employee.phone_number = phone_number
            await db.flush()
        logger.info("Found existing employee: %s (id=%s)", employee.name, employee.id)
        return employee

    # Step 3: Create new employee with the real name
    employee = Employee(
        name=name.strip(),
        phone_number=phone_number,
        company_id=company_id,
    )
    db.add(employee)
    await db.flush()
    await db.refresh(employee)
    logger.info("Created new employee: %s (id=%s)", employee.name, employee.id)
    return employee


async def find_employee_by_name(
    db: AsyncSession,
    name: str,
    company_id: int | None = None,
) -> Employee | None:
    """Look up an employee by name (case-insensitive). Returns None if not found."""
    stmt = select(Employee).where(
        sa_func.lower(Employee.name) == name.strip().lower()
    )
    if company_id is not None:
        stmt = stmt.where(Employee.company_id == company_id)
    result = await db.execute(stmt)
    return result.scalars().first()


async def get_employee_by_phone(
    db: AsyncSession,
    phone_number: str,
) -> Employee | None:
    """Look up an employee by phone number.

    Tries exact normalized match first, then a suffix match to handle
    stored numbers that are missing the + prefix or country code.
    """
    normalized = normalize_phone_number(phone_number)
    logger.info("get_employee_by_phone: raw=%r normalized=%r", phone_number, normalized)

    # Exact match
    stmt = select(Employee).where(Employee.phone_number == normalized)
    result = await db.execute(stmt)
    employee = result.scalars().first()
    if employee:
        logger.info("get_employee_by_phone: exact match id=%s name=%r", employee.id, employee.name)
        return employee

    # Fallback: match on the last 10 digits (handles +91XXXXXXXXXX vs 91XXXXXXXXXX vs XXXXXXXXXX)
    suffix = re.sub(r"\D", "", normalized)[-10:]
    if len(suffix) == 10:
        stmt2 = select(Employee).where(Employee.phone_number.like(f"%{suffix}"))
        result2 = await db.execute(stmt2)
        employee2 = result2.scalars().first()
        if employee2:
            logger.info(
                "get_employee_by_phone: suffix-match id=%s name=%r (stored=%r vs incoming=%r)",
                employee2.id, employee2.name, employee2.phone_number, normalized,
            )
            return employee2

    logger.warning("get_employee_by_phone: NO match for normalized=%r", normalized)
    return None


async def get_all_employee_names(db: AsyncSession) -> list[str]:
    """Return all employee names, filtering out phone-number placeholders."""
    stmt = select(Employee.name)
    result = await db.execute(stmt)
    return [
        row[0] for row in result.all()
        if row[0] and not _is_phone_name(row[0]) and not row[0].startswith("Employee_")
    ]
