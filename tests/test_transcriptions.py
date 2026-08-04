import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor

from census.models import ScheduleTranscription, TranscriptionRun
from tests.factories import (
    CensusScheduleFactory,
    ReligiousBodyFactory,
    ScheduleTranscriptionFactory,
    TranscriptionRunFactory,
)


@pytest.mark.django_db
def test_transcription_run_identity_cannot_change():
    run = TranscriptionRunFactory(key="stable-run", kind="agent")

    run.key = "renamed-run"
    with pytest.raises(ValidationError, match="key and kind are immutable"):
        run.save()


@pytest.mark.django_db
def test_schedule_transcription_cannot_be_changed_or_deleted():
    transcription = ScheduleTranscriptionFactory(data={"value": "original"})

    transcription.data = {"value": "changed"}
    with pytest.raises(ValidationError, match="immutable"):
        transcription.save()

    with pytest.raises(ValidationError, match="immutable"):
        transcription.delete()

    transcription.refresh_from_db()
    assert transcription.data == {"value": "original"}


@pytest.mark.django_db(transaction=True)
def test_schedule_and_run_pair_is_unique():
    transcription = ScheduleTranscriptionFactory()

    with pytest.raises(IntegrityError):
        ScheduleTranscription.objects.create(
            census_schedule=transcription.census_schedule,
            run=transcription.run,
            data={"duplicate": True},
        )


@pytest.mark.django_db
def test_snapshot_command_creates_one_immutable_output_per_run():
    schedule = CensusScheduleFactory(schedule_id="snapshot-example")
    ReligiousBodyFactory(census_record=schedule, name="Snapshot Church")

    call_command("snapshot_human_transcription", run_key="human-snapshot-test")
    call_command("snapshot_human_transcription", run_key="human-snapshot-test")

    run = TranscriptionRun.objects.get(key="human-snapshot-test")
    assert run.kind == "human_snapshot"
    assert ScheduleTranscription.objects.filter(run=run).count() == 1
    output = ScheduleTranscription.objects.get(run=run, census_schedule=schedule)
    assert output.data["schedule_fields"]["schedule_id"] == "snapshot-example"
    assert output.data["religious_bodies"][0]["name"] == "Snapshot Church"


@pytest.mark.django_db(transaction=True)
def test_transcription_migration_preserves_legacy_json_and_notes():
    old_target = [("census", "0022_alter_censusschedule_transcription_status_and_more")]
    new_target = [("census", "0023_transcription_runs")]
    executor = MigrationExecutor(connection)
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps
    OldSchedule = old_apps.get_model("census", "CensusSchedule")
    schedule = OldSchedule.objects.create(
        resource_id=987654,
        schedule_title="Migration test",
        schedule_id="migration-test",
        human_transcription={"source": "human", "value": 12},
        ai_transcription={"source": "agent", "value": 13},
        ai_notes="Uncertain handwriting",
    )

    executor = MigrationExecutor(connection)
    executor.migrate(new_target)
    new_apps = executor.loader.project_state(new_target).apps
    NewOutput = new_apps.get_model("census", "ScheduleTranscription")
    outputs = {
        output.run.key: output.data
        for output in NewOutput.objects.filter(
            census_schedule_id=schedule.pk
        ).select_related("run")
    }

    assert outputs == {
        "human-snapshot": {"source": "human", "value": 12},
        "legacy-agent-transcription": {
            "source": "agent",
            "value": 13,
            "ai_notes": "Uncertain handwriting",
        },
    }

    executor = MigrationExecutor(connection)
    executor.migrate(old_target)
    restored_apps = executor.loader.project_state(old_target).apps
    RestoredSchedule = restored_apps.get_model("census", "CensusSchedule")
    restored = RestoredSchedule.objects.get(pk=schedule.pk)
    assert restored.human_transcription == {"source": "human", "value": 12}
    assert restored.ai_transcription == {"source": "agent", "value": 13}
    assert restored.ai_notes == "Uncertain handwriting"

    MigrationExecutor(connection).migrate(new_target)
