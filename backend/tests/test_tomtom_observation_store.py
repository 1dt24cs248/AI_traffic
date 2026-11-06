import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.tomtom_traffic import TomTomRoadSegment, TomTomTrafficObservation
from app.schemas.tomtom import CurrentTrafficFlow
from app.traffic.observation_store import persist_tomtom_observation


def make_flow(
    *,
    latitude=12.9756,
    longitude=77.6068,
    observation_time=datetime(2026, 10, 20, 6, 0, tzinfo=timezone.utc),
    retrieved_at=datetime(2026, 10, 20, 6, 1, tzinfo=timezone.utc),
    current_speed=31.5,
):
    return CurrentTrafficFlow(
        latitude=latitude,
        longitude=longitude,
        current_speed=current_speed,
        free_flow_speed=50.0,
        current_travel_time_seconds=120,
        confidence=0.82,
        road_closure=False,
        source="TomTom Traffic Flow API",
        observation_time=observation_time,
        retrieved_at=retrieved_at,
    )


class FakeQuery:
    def __init__(self, session, model):
        self.session = session
        self.model = model
        self.filters = {}
        self.hide_existing = False

    def filter_by(self, **filters):
        self.filters = filters
        return self

    def first(self):
        if self.hide_existing:
            return None
        rows = self.session.persisted + self.session.pending
        return next(
            (
                row
                for row in rows
                if isinstance(row, self.model)
                and all(getattr(row, key) == value for key, value in self.filters.items())
            ),
            None,
        )


class FakeSession:
    def __init__(self, *, fail_commit=False):
        self.persisted = []
        self.pending = []
        self.fail_commit = fail_commit
        self.rolled_back = False
        self.closed = False
        self.committed = False

    def query(self, model):
        return FakeQuery(self, model)

    def add(self, row):
        self.pending.append(row)

    def flush(self):
        for row in self.pending:
            if row.id is None:
                row.id = uuid4()

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("simulated database failure")
        self.persisted.extend(self.pending)
        self.pending.clear()
        self.committed = True

    def rollback(self):
        self.pending.clear()
        self.rolled_back = True

    def close(self):
        self.closed = True


class FakeSessionFactory:
    def __init__(self, *, fail_commit=False):
        self.sessions = []
        self.fail_commit = fail_commit

    def __call__(self):
        session = FakeSession(fail_commit=self.fail_commit)
        if self.sessions:
            session.persisted = self.sessions[0].persisted
        self.sessions.append(session)
        return session


class ConflictOnceSession(FakeSession):
    def query(self, model):
        query = FakeQuery(self, model)
        if model is TomTomTrafficObservation:
            query.hide_existing = True
        return query

    def commit(self):
        raise IntegrityError("insert", {}, RuntimeError("unique constraint conflict"))


class ConflictOnceSessionFactory:
    def __init__(self, segment, observation):
        self.sessions = []
        self.persisted = [segment, observation]

    def __call__(self):
        if not self.sessions:
            session = ConflictOnceSession()
        else:
            session = FakeSession()
        session.persisted = self.persisted
        self.sessions.append(session)
        return session


def test_successful_insert_preserves_provenance_and_distinct_timestamps():
    sessions = FakeSessionFactory()
    observed_at = datetime(2026, 10, 20, 6, 0, tzinfo=timezone.utc)
    retrieved_at = observed_at + timedelta(minutes=1)

    result = persist_tomtom_observation(
        make_flow(observation_time=observed_at, retrieved_at=retrieved_at),
        provider_segment_reference="provider-road-segment-1",
        session_factory=sessions,
    )

    segment, observation = sessions.sessions[0].persisted
    assert result.inserted is True
    assert result.segment_identity_status == "unverified"
    assert observation.provider_observed_at == observed_at
    assert observation.retrieved_at == retrieved_at
    assert observation.provider_observed_at != observation.retrieved_at
    assert observation.requested_latitude == 12.9756
    assert observation.requested_longitude == 77.6068
    assert observation.current_speed == 31.5
    assert observation.speed_unit == "km/h"
    assert observation.travel_time_unit == "seconds"
    assert observation.source == "TomTom Traffic Flow API"
    assert observation.source_endpoint.endswith("/flowSegmentData/absolute/10/json")
    assert segment.provider_segment_reference == "provider-road-segment-1"
    assert sessions.sessions[0].committed is True
    assert sessions.sessions[0].closed is True

    later_flow = make_flow(
        observation_time=observed_at + timedelta(minutes=5),
        retrieved_at=retrieved_at + timedelta(minutes=5),
        current_speed=27.0,
    )
    second = persist_tomtom_observation(
        later_flow,
        provider_segment_reference="provider-road-segment-1",
        session_factory=sessions,
    )
    assert second.inserted is True
    observations = [
        row
        for row in sessions.sessions[1].persisted
        if isinstance(row, TomTomTrafficObservation)
    ]
    assert len(observations) == 2
    assert [row.current_speed for row in observations] == [31.5, 27.0]


def test_missing_provider_timestamp_remains_null():
    sessions = FakeSessionFactory()
    retrieved_at = datetime(2026, 10, 20, 6, 1, tzinfo=timezone.utc)

    persist_tomtom_observation(
        make_flow(observation_time=None, retrieved_at=retrieved_at),
        provider_segment_reference="stable-ref-no-provider-time",
        session_factory=sessions,
    )
    persist_tomtom_observation(
        make_flow(
            observation_time=None,
            retrieved_at=retrieved_at + timedelta(minutes=1),
            current_speed=27.0,
        ),
        provider_segment_reference="stable-ref-no-provider-time",
        session_factory=sessions,
    )

    observations = [
        row
        for row in sessions.sessions[1].persisted
        if isinstance(row, TomTomTrafficObservation)
    ]
    assert len(observations) == 2
    assert all(row.provider_observed_at is None for row in observations)
    assert [row.retrieved_at for row in observations] == [
        retrieved_at,
        retrieved_at + timedelta(minutes=1),
    ]
    assert [row.current_speed for row in observations] == [31.5, 27.0]


def test_repeated_observation_is_idempotent_for_provider_segment_and_timestamp():
    sessions = FakeSessionFactory()
    flow = make_flow()

    first = persist_tomtom_observation(
        flow,
        provider_segment_reference="stable-ref-123",
        session_factory=sessions,
    )
    duplicate = persist_tomtom_observation(
        flow,
        provider_segment_reference="stable-ref-123",
        session_factory=sessions,
    )

    assert first.inserted is True
    assert duplicate.inserted is False
    assert duplicate.observation_id == first.observation_id
    assert len(
        [
            row
            for row in sessions.sessions[1].persisted
            if isinstance(row, TomTomTrafficObservation)
        ]
    ) == 1


def test_concurrent_unique_conflict_returns_existing_without_overwriting():
    observed_at = datetime(2026, 10, 20, 6, 0, tzinfo=timezone.utc)
    segment = TomTomRoadSegment(
        id=uuid4(),
        provider="tomtom",
        provider_segment_reference="stable-ref-concurrent",
        identity_status="unverified",
        identity_version="unverified-v1",
        mapping_version="unmapped-v1",
    )
    prior = TomTomTrafficObservation(
        id=uuid4(),
        segment_id=segment.id,
        provider="tomtom",
        source="TomTom Traffic Flow API",
        source_endpoint="/traffic/services/4/flowSegmentData/absolute/10/json",
        provenance_version="tomtom-flow-v4",
        requested_latitude=12.9756,
        requested_longitude=77.6068,
        coordinate_system="EPSG:4326",
        provider_observed_at=observed_at,
        retrieved_at=observed_at + timedelta(minutes=1),
        current_speed=19.0,
        free_flow_speed=50.0,
        travel_time_seconds=120,
        confidence=0.82,
        road_closure=False,
        speed_unit="km/h",
        travel_time_unit="seconds",
    )
    sessions = ConflictOnceSessionFactory(segment, prior)

    result = persist_tomtom_observation(
        make_flow(observation_time=observed_at, current_speed=31.5),
        provider_segment_reference="stable-ref-concurrent",
        session_factory=sessions,
    )

    assert result.inserted is False
    assert result.observation_id == prior.id
    assert result.segment_id == segment.id
    assert sessions.sessions[0].rolled_back is True
    assert sessions.sessions[0].closed is True
    assert sessions.sessions[1].closed is True
    assert len(
        [
            row
            for row in sessions.persisted
            if isinstance(row, TomTomTrafficObservation)
        ]
    ) == 1


@pytest.mark.parametrize(
    "flow",
    [
        make_flow(latitude=91),
        make_flow(longitude=-181),
        make_flow(latitude=float("nan")),
        make_flow(current_speed=-1),
        make_flow(current_speed=float("inf")),
        make_flow().model_copy(update={"free_flow_speed": -1}),
        make_flow().model_copy(update={"free_flow_speed": float("inf")}),
    ],
)
def test_invalid_coordinates_and_speeds_are_rejected_before_session_creation(flow):
    sessions = FakeSessionFactory()

    with pytest.raises(ValueError):
        persist_tomtom_observation(flow, session_factory=sessions)

    assert sessions.sessions == []


def test_invalid_units_and_provenance_are_rejected():
    sessions = FakeSessionFactory()

    with pytest.raises(ValueError, match="speed"):
        persist_tomtom_observation(
            make_flow(),
            speed_unit="mph",
            session_factory=sessions,
        )
    with pytest.raises(ValueError, match="TomTom Traffic Flow API"):
        persist_tomtom_observation(
            make_flow().model_copy(update={"source": "synthetic"}),
            session_factory=sessions,
        )

    assert sessions.sessions == []


def test_database_failure_rolls_back_and_closes_independent_session():
    sessions = FakeSessionFactory(fail_commit=True)

    with pytest.raises(RuntimeError, match="simulated database failure"):
        persist_tomtom_observation(make_flow(), session_factory=sessions)

    assert sessions.sessions[0].rolled_back is True
    assert sessions.sessions[0].closed is True
    assert sessions.sessions[0].persisted == []


def test_provisional_segments_are_not_forecast_eligible():
    sessions = FakeSessionFactory()

    result = persist_tomtom_observation(make_flow(), session_factory=sessions)

    segment = next(
        row
        for row in sessions.sessions[0].persisted
        if isinstance(row, TomTomRoadSegment)
    )
    assert result.segment_identity_status == "provisional"
    assert segment.provider_segment_reference is None
    assert segment.is_forecast_eligible is False


def test_segment_without_a_validated_mapping_is_not_forecast_eligible():
    segment = TomTomRoadSegment(
        provider_segment_reference="provider-segment-ref",
        identity_status="verified",
        mapping_version="unmapped-v1",
    )

    assert segment.is_forecast_eligible is False


def test_request_coordinates_do_not_create_a_reusable_segment_identity():
    sessions = FakeSessionFactory()
    first = persist_tomtom_observation(
        make_flow(),
        session_factory=sessions,
    )
    second = persist_tomtom_observation(
        make_flow(
            observation_time=datetime(2026, 10, 20, 6, 5, tzinfo=timezone.utc),
        ),
        session_factory=sessions,
    )

    assert first.segment_id != second.segment_id
    assert first.segment_identity_status == "provisional"
    assert second.segment_identity_status == "provisional"


def test_migration_is_additive_and_does_not_mutate_existing_tables():
    migration_path = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "versions"
        / "20261020_02_tomtom_observations.py"
    )
    migration_source = migration_path.read_text(encoding="utf-8")
    tree = ast.parse(migration_source)
    revision_values = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"revision", "down_revision"}
    }
    assert revision_values == {
        "revision": "20261020_02",
        "down_revision": "20261019_01",
    }

    migration_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
    ]
    operation_names = {node.func.attr for node in migration_calls}
    assert operation_names == {
        "create_table",
        "create_index",
        "get_bind",
        "get_context",
    }

    created_tables = {
        ast.literal_eval(call.args[0])
        for call in migration_calls
        if call.func.attr == "create_table"
    }
    model_tables = {
        TomTomRoadSegment.__tablename__: TomTomRoadSegment.__table__,
        TomTomTrafficObservation.__tablename__: TomTomTrafficObservation.__table__,
    }
    assert created_tables == set(model_tables)
    for create_table in (
        call for call in migration_calls if call.func.attr == "create_table"
    ):
        table_name = ast.literal_eval(create_table.args[0])
        migration_columns = {
            ast.literal_eval(column.args[0])
            for column in create_table.args[1:]
            if isinstance(column, ast.Call)
            and isinstance(column.func, ast.Attribute)
            and isinstance(column.func.value, ast.Name)
            and column.func.value.id == "sa"
            and column.func.attr == "Column"
        }
        assert migration_columns == set(model_tables[table_name].columns.keys())

    created_at_columns = [table.c.created_at for table in model_tables.values()]
    assert len(created_at_columns) == 2
    assert all(column.nullable is False for column in created_at_columns)
    assert all(column.default is not None for column in created_at_columns)
    assert all(
        column.server_default is not None
        and str(column.server_default.arg) == "now()"
        for column in created_at_columns
    )
    migration_created_at_columns = [
        column
        for call in migration_calls
        if call.func.attr == "create_table"
        for column in call.args[1:]
        if isinstance(column, ast.Call)
        and isinstance(column.func, ast.Attribute)
        and isinstance(column.func.value, ast.Name)
        and column.func.value.id == "sa"
        and column.func.attr == "Column"
        and ast.literal_eval(column.args[0]) == "created_at"
    ]
    assert len(migration_created_at_columns) == 2
    assert all(
        any(
            keyword.arg == "server_default"
            and ast.unparse(keyword.value) == "sa.func.now()"
            for keyword in column.keywords
        )
        for column in migration_created_at_columns
    )

    assert created_tables == {
        "tomtom_road_segments",
        "tomtom_traffic_observations",
    }
    migration_foreign_keys = [
        ast.literal_eval(call.args[0])
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "sa"
        and call.func.attr == "ForeignKey"
    ]
    model_foreign_keys = [
        element.target_fullname
        for element in TomTomTrafficObservation.__table__.foreign_keys
    ]
    assert migration_foreign_keys == model_foreign_keys == ["tomtom_road_segments.id"]
    indexed_tables = {
        ast.literal_eval(call.args[1])
        for call in migration_calls
        if call.func.attr == "create_index"
    }
    assert indexed_tables == {"tomtom_traffic_observations"}
    assert '"ix_tomtom_observation_retrieved_at"' in migration_source
    assert '"ix_tomtom_observation_segment_observed_at"' not in migration_source

    assert "ix_tomtom_observation_segment_observed_at" not in {
        index.name
        for index in TomTomTrafficObservation.__table__.indexes
    }
    assert {
        index.name
        for index in TomTomTrafficObservation.__table__.indexes
    } == {"ix_tomtom_observation_retrieved_at"}
    observation_unique_constraints = {
        constraint.name
        for constraint in TomTomTrafficObservation.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert observation_unique_constraints == {
        "uq_tomtom_observation_segment_observed_at"
    }

    downgrade = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade"
    )
    assert any(
        isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and isinstance(node.exc.func, ast.Name)
        and node.exc.func.id == "NotImplementedError"
        for node in ast.walk(downgrade)
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
        for node in ast.walk(downgrade)
    )
