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
