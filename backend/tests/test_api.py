import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main.settings, 'database_path', str(tmp_path / 'test.sqlite3'))
    monkeypatch.setattr(main.settings, 'smtp_host', '')
    monkeypatch.setattr(main.settings, 'smtp_from', '')
    monkeypatch.setattr(main.settings, 'demo_mode', True)
    with TestClient(main.app) as c:
        yield c

@pytest.fixture
def asset(client):
    return client.get('/api/config').json()['defaults']

def enable_smtp(monkeypatch):
    monkeypatch.setattr(main.settings, 'smtp_host', 'smtp.example.test')
    monkeypatch.setattr(main.settings, 'smtp_from', 'it@example.test')

def test_preview_and_history(client, asset):
    result = client.post('/api/preview', json=asset)
    assert result.status_code == 200
    assert asset['url'] in result.json()['body']
    assert 'No physical laptop' in result.json()['body']
    assert client.get('/api/history').json()[0]['action'] == 'PREVIEWED'
    assert client.get('/api/history/export').text.startswith('id,created_at,')

def test_invalid_email(client, asset):
    asset['email'] = 'invalid'
    assert client.post('/api/preview', json=asset).status_code == 422

def test_demo_restriction(client, asset):
    asset['asset_tag'] = 'OTHER'
    assert client.post('/api/preview', json=asset).status_code == 403

def test_sending_disabled(client, asset):
    assert client.post('/api/send', json=asset).status_code == 503
    assert client.get('/api/history').json() == []

def test_smtp_send_and_duplicate(client, asset, monkeypatch):
    enable_smtp(monkeypatch)
    with patch('main.smtplib.SMTP') as transport:
        assert client.post('/api/send', json=asset).status_code == 200
        smtp = transport.return_value.__enter__.return_value
        smtp.starttls.assert_called_once()
        smtp.send_message.assert_called_once()
        asset['email'] = asset['email'].upper()
        assert client.post('/api/send', json=asset).status_code == 409
        smtp.send_message.assert_called_once()
    assert client.get('/api/history').json()[0]['action'] == 'SEND_REQUESTED'

def test_smtp_failure_blocks_retry(client, asset, monkeypatch):
    enable_smtp(monkeypatch)
    with patch('main.smtplib.SMTP', side_effect=OSError('offline')):
        assert client.post('/api/send', json=asset).status_code == 502
        assert client.post('/api/send', json=asset).status_code == 409
    assert client.get('/api/history').json()[0]['action'] == 'DELIVERY_UNKNOWN'

def test_database_persistence(client, asset):
    client.post('/api/preview', json=asset)
    main.initialize_database()
    assert len(client.get('/api/history').json()) == 1

def test_csv_formula_escape(client, asset):
    asset['model'] = '=1+1'
    assert client.post('/api/preview', json=asset).status_code == 200
    assert "'=1+1" in client.get('/api/history/export').text
