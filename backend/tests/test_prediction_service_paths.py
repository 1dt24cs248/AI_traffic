from pathlib import Path

from app.prediction.service import _resolve_pems08_model_dir


def test_configured_model_directory_takes_precedence(tmp_path):
    configured = tmp_path / "mounted-models"

    assert _resolve_pems08_model_dir(Path("service.py"), str(configured)) == configured.resolve()


def test_workspace_layout_resolves_external_ml_directory(tmp_path):
    service_file = (
        tmp_path / "workspace" / "repository" / "backend" / "app"
        / "prediction" / "service.py"
    )

    assert _resolve_pems08_model_dir(service_file) == (
        tmp_path / "workspace" / "ml" / "models" / "pems08"
    )


def test_shallow_container_layout_does_not_index_missing_parent(tmp_path):
    container_root = tmp_path.parent
    service_file = container_root / "app" / "app" / "prediction" / "service.py"

    assert _resolve_pems08_model_dir(service_file) == (
        Path(service_file.anchor) / "ml" / "models" / "pems08"
    )
