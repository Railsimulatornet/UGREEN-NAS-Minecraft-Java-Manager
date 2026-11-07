"""Check release documentation without starting Docker, Minecraft or NAS jobs."""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).parents[1]
REPO = 'https://github.com/Railsimulatornet/UGREEN-NAS-Minecraft-Java-Manager/'


def test_markdown_links_point_to_existing_release_files():
    paths = [*ROOT.glob('*.md'), *(ROOT / 'docs').rglob('*.md')]
    for path in paths:
        source = path.read_text(encoding='utf-8')
        assert '/blob/nachbesserung-' not in source, path
        for target in re.findall(r'!?\[[^\]]*\]\(([^)\s]+)\)', source):
            target = unquote(target.strip('<>'))
            if target.startswith(REPO + 'blob/main/'):
                local = ROOT / target.removeprefix(REPO + 'blob/main/').split('#')[0]
            elif urlsplit(target).scheme or target.startswith('#'):
                continue
            else:
                local = path.parent / target.split('#')[0]
            assert local.is_file(), (path.relative_to(ROOT), target)


def test_release_tree_contains_user_documentation_without_internal_reports():
    assert not (ROOT / 'docs/abnahme').exists()
    assert sorted(p.name for p in (ROOT / 'docs/security').iterdir()) == [
        'IMAGE-SECURITY.md', 'image-baseline-1.0.0.json', 'image-baseline-1.0.1.json']
    assert not list((ROOT / 'docs').rglob('Pruefung.json'))
    assert (ROOT / 'LICENSE').is_file() and (ROOT / 'NOTICE.txt').is_file()
