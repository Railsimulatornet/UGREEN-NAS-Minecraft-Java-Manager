import importlib.util
from pathlib import Path


def module():
    spec = importlib.util.spec_from_file_location(
        'validation_scope', Path(__file__).parents[1] / '.github/scripts/validation_scope.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_documentation_scope_cannot_hide_runtime_or_packaging_changes():
    scope = module()
    assert scope.bounded_paths(['README.md', 'docs/Installation-DE.pdf', 'tests/test_release_links.py'])
    for path in ['mcj/auth.py', 'tools/install.py', 'guard/src/main/java/Guard.java',
                 'artifacts/guard.json', 'Dockerfile', 'requirements.txt', 'compose.yaml']:
        assert not scope.bounded_paths(['docs/INSTALLATION-DE.md', path])


def test_explicit_full_validation_always_overrides_documentation_selection(monkeypatch):
    monkeypatch.setenv('MCJ_FULL_VALIDATION', 'true')
    assert module().targeted() is False


def test_initial_commit_always_gets_full_automated_validation(monkeypatch):
    scope = module()
    monkeypatch.delenv('MCJ_FULL_VALIDATION', raising=False)
    def git(command, **kwargs):
        if command[1:3] == ['rev-list', '--max-parents=0']:
            return 'a' * 40 + '\n'
        if command[1:3] == ['rev-parse', 'HEAD']:
            return 'a' * 40 + '\n'
        raise AssertionError(command)
    monkeypatch.setattr(scope.subprocess, 'check_output', git)
    assert scope.targeted() is False


def test_later_documentation_commit_can_use_targeted_checks(monkeypatch):
    scope = module()
    monkeypatch.delenv('MCJ_FULL_VALIDATION', raising=False)
    def git(command, **kwargs):
        if command[1:3] == ['rev-list', '--max-parents=0']:
            return 'a' * 40 + '\n'
        if command[1:3] == ['rev-parse', 'HEAD']:
            return 'b' * 40 + '\n'
        if command[1:3] == ['diff', '--name-only']:
            return 'README.md\ndocs/INSTALLATION-DE.md\n'
        raise AssertionError(command)
    monkeypatch.setattr(scope.subprocess, 'check_output', git)
    assert scope.targeted() is True
