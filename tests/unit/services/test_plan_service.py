from app.models.vm_plan import VmPlanRow
from app.services import plan_service


class FakeDB:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        pass


def _plan() -> VmPlanRow:
    return VmPlanRow(
        name="small", display_name="Small", cpu="1", memory="2Gi", disk="5Gi",
        credits_per_hour=1.0, workspace_gb=20, is_active=True,
    )


async def test_update_plan_applies_only_provided_fields():
    plan = _plan()
    db = FakeDB()

    await plan_service.update_plan(db, plan, {"credits_per_hour": 3.5, "cpu": None})

    assert plan.credits_per_hour == 3.5
    assert plan.cpu == "1"  # None is skipped, not written
    assert db.commits == 1


async def test_update_plan_ignores_name_change():
    plan = _plan()
    db = FakeDB()

    await plan_service.update_plan(db, plan, {"name": "hacked", "display_name": "Renamed"})

    assert plan.name == "small"  # PK is immutable
    assert plan.display_name == "Renamed"


async def test_deactivate_plan_sets_inactive():
    plan = _plan()
    db = FakeDB()

    await plan_service.deactivate_plan(db, plan)

    assert plan.is_active is False
    assert db.commits == 1
