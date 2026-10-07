"""Read availability must not be mistaken for write availability at Live admission."""
from unittest.mock import MagicMock

import pytest

from shared.elasticsearch_client import ElasticsearchClient


@pytest.fixture
def client():
    wrapper = ElasticsearchClient.__new__(ElasticsearchClient)
    wrapper.client = MagicMock()
    scoped = wrapper.client.options.return_value
    scoped.indices.get_settings.return_value = {}
    scoped.cluster.get_settings.return_value = {"persistent": {}, "transient": {}}
    return wrapper, scoped


def test_unblocked_index_is_ready_without_writing_a_probe_document(client):
    wrapper, scoped = client
    assert wrapper.job_results_write_ready()
    wrapper.client.options.assert_called_once_with(request_timeout=2, max_retries=0)
    scoped.indices.get_settings.assert_called_once_with(index='job_results', flat_settings=True)
    scoped.index.assert_not_called()


@pytest.mark.parametrize('flag', ['write', 'read_only', 'read_only_allow_delete'])
@pytest.mark.parametrize('value,expected', [('true', False), (True, False), ('false', True), (False, True)])
def test_index_blocks(client, flag, value, expected):
    wrapper, scoped = client
    scoped.indices.get_settings.return_value = {
        'job_results': {'settings': {f'index.blocks.{flag}': value}}
    }
    assert wrapper.job_results_write_ready() is expected


@pytest.mark.parametrize('flag', ['read_only', 'read_only_allow_delete'])
def test_cluster_block_and_transient_override(client, flag):
    wrapper, scoped = client
    scoped.cluster.get_settings.return_value = {'persistent': {f'cluster.blocks.{flag}': 'true'}}
    assert not wrapper.job_results_write_ready()
    scoped.cluster.get_settings.return_value['transient'] = {f'cluster.blocks.{flag}': 'false'}
    assert wrapper.job_results_write_ready()


@pytest.mark.parametrize('service', ['indices', 'cluster'])
def test_missing_index_or_unreachable_cluster_fails_closed(client, service):
    wrapper, scoped = client
    getattr(scoped, service).get_settings.side_effect = RuntimeError('unavailable')
    assert not wrapper.job_results_write_ready()


def test_index_failure_is_logged_without_document_or_exception_contents(client, caplog):
    wrapper, _ = client
    wrapper.client.index.side_effect = RuntimeError('private document from server')
    assert not wrapper.store_job_result('job', 'private transcript')
    assert 'job_id=job' in caplog.text
    assert 'RuntimeError' in caplog.text
    assert 'private' not in caplog.text
