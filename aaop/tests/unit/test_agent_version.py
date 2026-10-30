import tempfile

import pytest

from core.versioning.agent_version import AgentVersion


@pytest.fixture
def sample_agent():
    return AgentVersion(
        name="test-agent",
        major=1, minor=0, patch=0,
        config={"model_tier": "balanced", "temperature": 0.0},
        prompts={"system": "You are a test agent.", "user": "{{ query }}"},
        tools=["web_search"],
        changelog="## v1.0.0\n- Initial release",
        description="A test agent",
        tags=["test"],
    )


def test_version_string(sample_agent):
    assert sample_agent.version_string == "v1.0.0"


def test_save_and_load_roundtrip(sample_agent):
    with tempfile.TemporaryDirectory() as tmpdir:
        sample_agent.save(base_dir=tmpdir)
        loaded = AgentVersion.load("test-agent", "v1.0.0", base_dir=tmpdir)

    assert loaded.name == sample_agent.name
    assert loaded.version_string == sample_agent.version_string
    assert loaded.config == sample_agent.config
    assert loaded.prompts == sample_agent.prompts
    assert loaded.tools == sample_agent.tools


def test_bump_patch(sample_agent):
    next_ver = sample_agent.bump_patch("Fix typo in prompt")
    assert next_ver.version_string == "v1.0.1"
    assert next_ver.major == 1
    assert next_ver.minor == 0
    assert next_ver.patch == 1


def test_bump_minor(sample_agent):
    next_ver = sample_agent.bump_minor("Add new tool")
    assert next_ver.version_string == "v1.1.0"
    assert next_ver.patch == 0
