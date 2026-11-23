from pathlib import Path
import yaml

def test_push_and_tags_cannot_publish_images():
    workflow=yaml.safe_load((Path(__file__).parents[1]/'.github/workflows/image.yml').read_text(encoding='utf-8'))
    events=workflow.get('on',workflow.get(True))
    assert events['workflow_dispatch']['inputs']['publish_image']['default'] is False
    assert events['workflow_dispatch']['inputs']['installation_tags']['default'] is False
    gate=workflow['jobs']['publish']['if']
    assert "github.event_name == 'workflow_dispatch'" in gate
    assert 'inputs.publish_image == true' in gate
    assert workflow['jobs']['publish']['needs']=='build'
    assert events['push']['branches']==['main']
    assert events['workflow_dispatch']['inputs']['build_image']['default'] is False
    assert events['workflow_dispatch']['inputs']['full_validation']['default'] is False
    build_gate=workflow['jobs']['build']['if']
    assert "github.event_name == 'workflow_dispatch'" in build_gate
    assert 'inputs.build_image == true' in build_gate
    assert "github.event_name == 'pull_request'" in build_gate
    assert "github.event_name == 'push' && github.ref == 'refs/heads/main'" in build_gate
    assert "needs.scope.result == 'success'" in build_gate
    assert "needs.tests.result == 'success'" in build_gate
    assert "needs.scope.outputs.targeted == 'true' && needs.guard.result == 'skipped'" in build_gate
    assert 'github.event.pull_request.head.sha || github.sha' in workflow['env']['SOURCE_REVISION']
    for name in ('scope','tests','guard','build'):
        assert workflow['jobs'][name]['steps'][0]['with']['ref']=='${{ env.SOURCE_REVISION }}'
