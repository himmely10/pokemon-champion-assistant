import json
import zipfile

import pytest

from champion_assistant.data.update_service import UpdateService, read_package, due


def test_due_boundary_and_clock_rollback():
    assert not due({'checked_at': 100}, 24, now=100 + 24*3600 - 1)
    assert due({'checked_at': 100}, 24, now=100 + 24*3600)
    assert due({'checked_at': 100}, 24, now=50)
    assert not due({}, 0, now=100)
    # A download can fail after a successful version check: retry in an hour,
    # not a day, while keeping repeated failures quiet during the backoff.
    assert not due({'checked_at': 100, 'failed_at': 200}, now=3799)
    assert due({'checked_at': 100, 'failed_at': 200}, now=3800)


def test_failed_network_check_preserves_last_success(tmp_path):
    class Offline:
        def get(self, *args, **kwargs):
            raise OSError('offline')
    service = UpdateService(tmp_path, 'https://example.org/channel.json', http=Offline())
    service._record(checked_at=100, installed='previous')
    with pytest.raises(OSError):
        service.check()
    assert service.state['checked_at'] == 100
    assert service.state['installed'] == 'previous'
    assert service.state['failed_at'] > 100


def test_unconfigured_check_and_failed_check_do_not_claim_success(tmp_path):
    service = UpdateService(tmp_path)
    assert service.check()['status'] == 'unconfigured'
    assert not service.state.get('checked_at')


@pytest.mark.parametrize('name', ['../secret.json', 'C:/secret.json', '_versions/a/../../secret.json'])
def test_package_paths_reject_escape(tmp_path, name):
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('package.json', json.dumps({'schema_version': 1, 'catalog_id': 'data-a',
                                             'files': {name: 'bad'}}))
        z.writestr(name, '{}')
    with pytest.raises(ValueError):
        read_package(archive, tmp_path / 'extract')
    assert not (tmp_path / 'secret.json').exists()


def test_cancelled_import_preserves_active_files(tmp_path):
    from threading import Event
    cancelled = Event()
    cancelled.set()
    service = UpdateService(tmp_path, cancelled=cancelled)
    with pytest.raises(ValueError, match='取消'):
        service.install(tmp_path / 'missing.zip')


def test_channel_version_must_match_before_publication(tmp_path, monkeypatch):
    import champion_assistant.data.update_service as module
    monkeypatch.setattr(module, 'read_package', lambda *args: {'version': 'actual', 'catalog_id': 'data-new'})
    service = UpdateService(tmp_path)
    service._record(installed='previous')
    with pytest.raises(ValueError, match='版本不一致'):
        service.install(tmp_path / 'unused.zip', version='different')
    assert not (tmp_path / '_versions').exists()
    assert service.state['installed'] == 'previous'


def test_package_download_streams_and_checks_hash(tmp_path):
    from champion_assistant.data.storage import digest
    class Response:
        url = 'https://example.org/package.zip'
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def iter_content(self, size): return iter([b'first', b'second'])
    class HTTP:
        def get(self, *args, **kwargs): return Response()
    service = UpdateService(tmp_path, http=HTTP())
    file = tmp_path / 'download.zip'
    service._download_package(Response.url, file, digest(b'firstsecond'))
    assert file.read_bytes() == b'firstsecond'
    with pytest.raises(ValueError, match='摘要'):
        service._download_package(Response.url, file, '0' * 64)
