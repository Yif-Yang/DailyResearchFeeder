from dailyresearchfeeder.cli import scaffold_project


def test_scaffold_project_creates_expected_files(tmp_path) -> None:
    destination = tmp_path / "workspace"

    results = scaffold_project(destination, write_env=True)

    assert results["config.yaml"] == "created"
    assert results[".env.example"] == "created"
    assert results[".env"] == "created"
    assert (destination / "config.yaml").exists()
    assert (destination / ".env.example").exists()
    assert (destination / ".env").exists()
    assert (destination / "user" / "keywords.txt").exists()
    assert (destination / "artifacts").is_dir()
    assert (destination / "runtime").is_dir()
    assert (destination / "state").is_dir()


def test_scaffold_project_does_not_overwrite_without_force(tmp_path) -> None:
    destination = tmp_path / "workspace"
    scaffold_project(destination)
    config_path = destination / "config.yaml"
    config_path.write_text("custom: true\n", encoding="utf-8")

    results = scaffold_project(destination)

    assert results["config.yaml"] == "skipped"
    assert config_path.read_text(encoding="utf-8") == "custom: true\n"