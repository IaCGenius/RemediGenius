"""Regression: a keyless launcher must not seed a ready-looking model."""
import sys
from pathlib import Path
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_workstation

SEED = (Path(__file__).resolve().parents[1] / 'profiles/ce/desk/config.yaml').read_text(encoding='utf-8')


def test_keyless_seed_omits_model():
    value = yaml.safe_load(native_workstation.seed_config(SEED, '', 'deepseek-v4.1-flash', 'https://example/v1'))
    assert 'model' not in value


def test_keyed_seed_fills_model():
    value = yaml.safe_load(native_workstation.seed_config(SEED, 'secret', 'deepseek-v4.1-flash', 'https://example/v1'))
    assert value['model']['default'] == 'deepseek-v4.1-flash'
    assert value['model']['base_url'] == 'https://example/v1'