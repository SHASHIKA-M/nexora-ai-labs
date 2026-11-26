"""Safety guarantees for real file workspaces."""
import pytest

from app.workspace import (
    WorkspaceError, list_files, projects_root, read_file, resolve_within, slugify, tree, write_file,
)


def test_slugify_produces_safe_folder_names():
    assert slugify("Online Shopping Platform") == "online-shopping-platform"
    assert slugify("  Über Cool!! Store  ") == "ber-cool-store"
    assert slugify("") == "project"
    assert len(slugify("x" * 200)) <= 60


def test_path_traversal_is_refused(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    for bad in ["../escape.txt", "a/../../escape.txt", "..", "C:/windows.txt", "/etc/passwd"]:
        with pytest.raises(WorkspaceError):
            resolve_within(root, bad)


def test_write_and_read_round_trip(isolated_environment):
    root = projects_root() / "round-trip"
    root.mkdir(parents=True, exist_ok=True)
    written = write_file(root, "backend/server.js", "console.log('hi');\n", agent_id="backend")
    assert written.path == "backend/server.js"
    assert written.lines == 1
    assert read_file(root, "backend/server.js") == "console.log('hi');\n"
    assert "backend/server.js" in [entry["path"] for entry in list_files(root)]


def test_oversized_file_is_rejected(isolated_environment):
    root = projects_root() / "oversized"
    root.mkdir(parents=True, exist_ok=True)
    with pytest.raises(WorkspaceError):
        write_file(root, "big.txt", "x" * (600 * 1024))


def test_tree_skips_dependency_folders(isolated_environment):
    root = projects_root() / "tree-test"
    (root / "node_modules" / "left-pad").mkdir(parents=True, exist_ok=True)
    write_file(root, "node_modules/left-pad/index.js", "module.exports = 1;\n")
    write_file(root, "src/app.js", "export const x = 1;\n")
    listing = tree(root)
    names = [child["name"] for child in listing["children"]]
    assert "node_modules" not in names
    assert "src" in names


def test_secret_scanner_finds_planted_credentials(isolated_environment):
    from app.workspace import scan_for_secrets

    root = projects_root() / "secret-scan"
    root.mkdir(parents=True, exist_ok=True)
    write_file(root, "config.js", 'const key = "mstrl_ABCDEFGHIJKLMNOPQRSTUVWX123";\n')
    write_file(root, "ok.js", 'const key = process.env.API_KEY || "";\n')
    findings = scan_for_secrets(root)
    assert any(finding["path"] == "config.js" for finding in findings)
    assert not any(finding["path"] == "ok.js" for finding in findings)
