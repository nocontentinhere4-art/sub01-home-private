"""Protect official CLI sentence segmentation and actual motion duration provenance."""
import pytest
from tools.verify_private_kimodo_generation import cli_prompt_segments, measured_generation_timing


def test_two_six_second_prompts_are_twelve_seconds_at_actual_thirty_hz():
    timing = measured_generation_timing('Frames: 360\nFrame Time: 0.03333333333333333\n',
        360, 6, 'Walk forward. Keep walking.', 30)
    assert timing['cli_prompt_count'] == 2
    assert timing['requested_seconds_per_cli_prompt'] == 6
    assert timing['requested_total_seconds'] == 12
    assert timing['actual_sample_duration_seconds'] == 12
    assert timing['actual_bvh_fps'] == 30
    assert timing['actual_last_sample_time_seconds'] == pytest.approx(359/30)


def test_single_sentence_does_not_silently_concatenate_another_six_seconds():
    prompt = 'Walk forward continuously, keeping a steady pace.'
    assert cli_prompt_segments(prompt) == [prompt]
    timing = measured_generation_timing('Frames: 180\nFrame Time: 0.03333333333333333\n', 180, 6, prompt, 30)
    assert timing['actual_sample_duration_seconds'] == 6
    with pytest.raises(ValueError, match='segmented CLI request'):
        measured_generation_timing('Frames: 360\nFrame Time: 0.03333333333333333\n', 360, 6, prompt, 30)


@pytest.mark.parametrize('clock,frames,model', [('nan', 360, 30), ('0', 360, 30), ('0.016666666666666666', 360, 30), ('0.03333333333333333', 180, 30)])
def test_invalid_or_disagreeing_actual_clock_is_refused(clock, frames, model):
    with pytest.raises(ValueError):
        measured_generation_timing('Frames: 360\nFrame Time: '+clock+'\n', frames, 6, 'Walk. Keep walking.', model)
