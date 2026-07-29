from linodl.gui.tasks import TaskInputSnapshot, TaskStatus, TaskStore
from linodl.models.novel import Chapter, VerificationResult, Volume


def test_task_store_returns_none_when_version_is_unchanged():
    store = TaskStore()

    first_version, first_records = store.snapshot_versioned()
    same_version, unchanged = store.snapshot_versioned(first_version)

    assert same_version == first_version
    assert first_records == []
    assert unchanged is None


def test_task_version_changes_after_create_and_transition():
    store = TaskStore()
    version_0, _ = store.snapshot_versioned()
    task = store.create(
        "read catalog",
        TaskInputSnapshot(kind="catalog", url="https://example.test"),
    )
    version_1, _ = store.snapshot_versioned(version_0)
    store.transition(task.id, TaskStatus.RUNNING, "reading", progress=0.25)
    version_2, records = store.snapshot_versioned(version_1)

    assert version_0 < version_1 < version_2
    assert records[0].progress == 0.25


def test_to_primitive_serializes_nested_dataclasses_and_enums():
    from linodl.desktop.serialization import to_primitive

    volume = Volume(
        name="Volume one",
        chapters=[Chapter(index=1, url="/1.html", title="Prologue", is_illustration=False)],
    )

    payload = to_primitive(volume)

    assert payload["name"] == "Volume one"
    assert payload["text_count"] == 1
    assert payload["chapters"][0]["title"] == "Prologue"


def test_to_primitive_includes_volume_and_verification_derived_fields():
    from linodl.desktop.serialization import to_primitive

    volume = Volume(
        name="Illustrated volume",
        chapters=[Chapter(index=0, url="/cover.jpg", title="Cover", is_illustration=True)],
    )
    result = VerificationResult()

    assert to_primitive(volume)["illus_count"] == 1
    assert to_primitive(result)["is_clean"] is True
    assert to_primitive(result)["issue_count"] == 0


def test_to_primitive_redacts_every_serialized_string():
    from linodl.desktop.serialization import to_primitive

    payload = to_primitive(
        {
            "detail": "token=top-secret",
            "nested": ("password=hunter2",),
            "status": TaskStatus.RUNNING,
        }
    )

    assert payload == {
        "detail": "token=***",
        "nested": ["password=***"],
        "status": "running",
    }
