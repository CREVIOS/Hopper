from app.models.vm_image import VmImageRow
from app.services import image_service


class FakeDB:
    def __init__(self):
        self.commits = 0
        self.cleared_default = 0

    async def execute(self, stmt):
        # The only execute() the pure logic issues is the _clear_default UPDATE.
        self.cleared_default += 1

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        pass


def _img(template="ubuntu", is_default=True) -> VmImageRow:
    return VmImageRow(
        template=template, display_name="Ubuntu", image="hopper/vm-ubuntu:22.04",
        description="Base", is_active=True, is_default=is_default,
    )


async def test_update_applies_only_provided_fields():
    row = _img()
    db = FakeDB()
    await image_service.update_image(db, row, {"image": "hopper/vm-ubuntu:24.04", "display_name": None})
    assert row.image == "hopper/vm-ubuntu:24.04"
    assert row.display_name == "Ubuntu"  # None skipped
    assert db.commits == 1


async def test_update_ignores_template_change():
    row = _img()
    db = FakeDB()
    await image_service.update_image(db, row, {"template": "hacked", "description": "New"})
    assert row.template == "ubuntu"
    assert row.description == "New"


async def test_setting_default_clears_others_first():
    row = _img(template="python-ml", is_default=False)
    db = FakeDB()
    await image_service.update_image(db, row, {"is_default": True})
    assert row.is_default is True
    assert db.cleared_default == 1  # _clear_default ran before setting this one


async def test_deactivate_also_clears_default():
    row = _img(is_default=True)
    db = FakeDB()
    await image_service.deactivate_image(db, row)
    assert row.is_active is False
    assert row.is_default is False
