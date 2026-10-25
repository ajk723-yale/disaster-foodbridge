"""P42: the API key can come from the project folder's .env or its parent's; nothing else is searched."""
import os

from src import config


def test_env_files_are_the_project_folder_then_its_parent(tmp_path):
    project = tmp_path / "course" / "final_project"
    assert config.env_files(str(project)) == [str(project / ".env"), str(tmp_path / "course" / ".env")]


def test_key_from_parent_project_wins_and_shell_wins(tmp_path, monkeypatch):
    course = tmp_path / "course"
    project = course / "final_project"
    project.mkdir(parents=True)
    (course / ".env").write_text("PORTKEY_API_KEY=from-parent\nP42_ONLY_PARENT=parent\n")
    monkeypatch.delenv("PORTKEY_API_KEY", raising=False)
    monkeypatch.delenv("P42_ONLY_PARENT", raising=False)
    assert config.load_env(str(project)) == [str(course / ".env")]
    assert os.environ["PORTKEY_API_KEY"] == "from-parent"             # parent folder only

    (project / ".env").write_text("PORTKEY_API_KEY=from-project\n")
    monkeypatch.delenv("PORTKEY_API_KEY")
    config.load_env(str(project))
    assert os.environ["PORTKEY_API_KEY"] == "from-project"            # project folder wins over parent
    assert os.environ["P42_ONLY_PARENT"] == "parent"                  # parent still fills other names

    monkeypatch.setenv("PORTKEY_API_KEY", "from-shell")
    config.load_env(str(project))
    assert os.environ["PORTKEY_API_KEY"] == "from-shell"              # shell always wins


def test_no_env_file_is_not_an_error(tmp_path, monkeypatch):
    assert config.load_env(str(tmp_path / "a" / "b")) == []


def test_env_example_has_no_real_secret():
    text = open(os.path.join(config.PROJECT_ROOT, ".env.example")).read()
    assert "PORTKEY_API_KEY=your-portkey-api-key-here" in text
    values = [line.split("=", 1)[1].strip() for line in text.splitlines()
              if line.startswith("PORTKEY_API_KEY=")]
    assert values == ["your-portkey-api-key-here"]
