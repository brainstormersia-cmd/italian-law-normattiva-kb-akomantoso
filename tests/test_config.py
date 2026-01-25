import pytest

from normativa_processor.core.config import ProcessingConfig


def test_processing_config_validation():
    with pytest.raises(ValueError):
        ProcessingConfig(min_chunk_tokens=100, target_chunk_tokens=50, max_chunk_tokens=150)

    with pytest.raises(ValueError):
        ProcessingConfig(min_chunk_tokens=5)

    with pytest.raises(ValueError):
        ProcessingConfig(overlap_ratio=0.9)
