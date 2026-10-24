"""GET /search must say "unavailable" when Elasticsearch fails, never "no results"."""

from unittest.mock import MagicMock

import pytest

from shared.elasticsearch_client import ElasticsearchClient, SearchUnavailable
from api import routes
from tests.test_live_transcription import world  # noqa: F401


def test_search_answers_503_when_elasticsearch_fails(world):  # noqa: F811
    world.es.search_jobs.side_effect = SearchUnavailable('es down')
    response = world.client.get('/search', params={'query': 'text'})
    assert response.status_code == 503
    assert response.json()['detail']['code'] == 'SEARCH_UNAVAILABLE'


def test_search_answers_503_when_the_client_cannot_even_be_created(world, monkeypatch):  # noqa: F811
    def down():
        raise ConnectionError('es down')
    monkeypatch.setattr(routes, 'get_es_client', down)
    response = world.client.get('/search', params={'query': 'text'})
    assert response.status_code == 503
    assert response.json()['detail']['code'] == 'SEARCH_UNAVAILABLE'


def test_search_jobs_raises_instead_of_returning_no_results():
    client = ElasticsearchClient.__new__(ElasticsearchClient)
    client.client = MagicMock()
    client.client.search.side_effect = ConnectionError('es down')
    with pytest.raises(SearchUnavailable):
        client.search_jobs('x', 'user')
