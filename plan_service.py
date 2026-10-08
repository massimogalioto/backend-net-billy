"""Centralized plan limits and tenant-scoped usage accounting."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Iterator

from database_service import ConfigurationError, _connection


@dataclass(frozen=True)
class PlanLimits:
    code: str
    name: str
    max_active_cte: int
    max_monthly_comparisons: int
    status: str


class UsageLimitError(RuntimeError):
    def __init__(self, resource: str, plan: PlanLimits, used: int, limit: int):
        self.resource, self.plan, self.used, self.limit = resource, plan, used, limit
        label = "CTE attive" if resource == "cte" else "confronti mensili"
        super().__init__(f"Hai raggiunto il limite di {limit} {label} previsto dal piano {plan.code}.")

    def payload(self) -> dict:
        return {"code": f"{self.resource}_limit_reached", "message": str(self),
                "used": self.used, "limit": self.limit, "plan": self.plan.code}


def _active_plan(cur, tenant_id: str) -> PlanLimits:
    cur.execute("""SELECT s.status, p.code, p.name, p.max_active_cte, p.max_monthly_comparisons
                   FROM subscriptions s JOIN plans p ON p.id = s.plan_id
                   WHERE s.tenant_id = %s AND s.status = 'active'
                     AND (s.current_period_start IS NULL OR s.current_period_start <= NOW())
                     AND (s.current_period_end IS NULL OR s.current_period_end > NOW())
                   ORDER BY s.created_at DESC, s.id DESC LIMIT 2""", (tenant_id,))
    rows = cur.fetchall()
    if not rows:
        raise ConfigurationError("Nessun piano attivo associato al tenant")
    if len(rows) > 1:
        raise ConfigurationError("Sono presenti più subscription attive per il tenant")
    row = rows[0]
    return PlanLimits(code=row["code"], name=row["name"],
                      max_active_cte=int(row["max_active_cte"]),
                      max_monthly_comparisons=int(row["max_monthly_comparisons"]),
                      status=row["status"])


def get_active_plan(tenant_id: str) -> PlanLimits:
    with _connection() as conn, conn.cursor() as cur:
        return _active_plan(cur, tenant_id)


def _lock_tenant(cur, tenant_id: str, resource: str) -> None:
    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"{resource}:{tenant_id}",))


def _count_active_cte(cur, tenant_id: str) -> int:
    cur.execute("""SELECT COUNT(*) AS count FROM cte_offers
                   WHERE tenant_id = %s
                     AND (valid_until IS NULL OR valid_until >= CURRENT_DATE)""", (tenant_id,))
    return int(cur.fetchone()["count"])


def count_active_cte(tenant_id: str) -> int:
    with _connection() as conn, conn.cursor() as cur:
        return _count_active_cte(cur, tenant_id)


def _offer_is_active(valid_until) -> bool:
    if valid_until is None:
        return True
    if isinstance(valid_until, str):
        valid_until = date.fromisoformat(valid_until)
    return valid_until >= date.today()


def ensure_active_cte_capacity(tenant_id: str, valid_until, *, conn=None) -> None:
    """Raise only when the *new* CTE would consume an active-plan slot."""
    if not _offer_is_active(valid_until):
        return
    if conn is None:
        with _connection() as own_conn:
            ensure_active_cte_capacity(tenant_id, valid_until, conn=own_conn)
        return
    with conn.cursor() as cur:
        _lock_tenant(cur, tenant_id, "cte")
        plan = _active_plan(cur, tenant_id)
        used = _count_active_cte(cur, tenant_id)
        if used >= plan.max_active_cte:
            raise UsageLimitError("cte", plan, used, plan.max_active_cte)


def _month_bounds_sql() -> str:
    return """created_at >= (date_trunc('month', NOW() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome')
              AND created_at < ((date_trunc('month', NOW() AT TIME ZONE 'Europe/Rome') + INTERVAL '1 month') AT TIME ZONE 'Europe/Rome')"""


def _count_monthly_comparisons(cur, tenant_id: str) -> int:
    cur.execute(f"SELECT COUNT(*) AS count FROM comparison_events WHERE tenant_id = %s AND {_month_bounds_sql()}", (tenant_id,))
    return int(cur.fetchone()["count"])


def count_monthly_comparisons(tenant_id: str) -> int:
    with _connection() as conn, conn.cursor() as cur:
        return _count_monthly_comparisons(cur, tenant_id)


@dataclass
class ComparisonSlot:
    conn: object
    tenant_id: str
    user_id: str
    plan: PlanLimits
    used: int

    def record_success(self, supply_type: str | None = None) -> None:
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO comparison_events (tenant_id, user_id, supply_type) VALUES (%s, %s, %s)",
                        (self.tenant_id, self.user_id, supply_type))


@contextmanager
def comparison_slot(tenant_id: str, user_id: str) -> Iterator[ComparisonSlot]:
    """Serialize one tenant's comparisons until success/failure is known.

    No event is inserted before the comparison completes; a failed operation exits
    without consuming quota, while the database advisory lock prevents overrun.
    """
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (f"comparison:{tenant_id}",))
            plan = _active_plan(cur, tenant_id)
            used = _count_monthly_comparisons(cur, tenant_id)
            if used >= plan.max_monthly_comparisons:
                raise UsageLimitError("comparison", plan, used, plan.max_monthly_comparisons)
        yield ComparisonSlot(conn, tenant_id, user_id, plan, used)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (f"comparison:{tenant_id}",))
            conn.commit()
        finally:
            conn.close()


def usage(tenant_id: str) -> dict:
    with _connection() as conn, conn.cursor() as cur:
        plan = _active_plan(cur, tenant_id)
        cte_used = _count_active_cte(cur, tenant_id)
        comparisons_used = _count_monthly_comparisons(cur, tenant_id)
    return {"plan": {"code": plan.code, "name": plan.name},
            "cte": {"used": cte_used, "limit": plan.max_active_cte,
                    "remaining": max(0, plan.max_active_cte - cte_used)},
            "comparisons": {"used": comparisons_used, "limit": plan.max_monthly_comparisons,
                            "remaining": max(0, plan.max_monthly_comparisons - comparisons_used),
                            "period": date.today().strftime("%Y-%m")}}
