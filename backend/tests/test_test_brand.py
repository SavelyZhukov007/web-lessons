import json

from tools.build import pwa


def test_beta_brand_is_only_applied_to_test_build(tmp_path, monkeypatch):
    monkeypatch.delenv('KIPCLUB_TEST_BUILD', raising=False)
    production = pwa.build_pwa(tmp_path / 'production')
    monkeypatch.setenv('KIPCLUB_TEST_BUILD', '1')
    beta = pwa.build_pwa(tmp_path / 'beta')
    prod_manifest = json.loads((production / 'manifest.webmanifest').read_text(encoding='utf-8'))
    beta_manifest = json.loads((beta / 'manifest.webmanifest').read_text(encoding='utf-8'))
    assert prod_manifest['short_name'] == 'KipClub'
    assert beta_manifest['short_name'] == 'KipClub Beta'
    assert (production / 'icons/icon-192.png').read_bytes() != (beta / 'icons/icon-192.png').read_bytes()
    assert '?v=beta1' in (beta / 'index.html').read_text(encoding='utf-8')
