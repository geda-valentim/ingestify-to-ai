"""Datalake refusals answer in the request language (P-13 slice 3).

The routes answer `{"code", "message"}`; the 404 non-disclosure text stays text,
localized. Pydantic-validated texts are rendered at raise time.
"""

import pytest

from shared.i18n import LanguageMiddleware
from tests.test_iam_merged_routes import ALICE, client, db, mode, no_shadow_noise  # noqa: F401

PT = {"Accept-Language": "pt-BR"}


def _detail(response):
    return response.json()["detail"]


@pytest.fixture
def dl(client):  # noqa: F811
    tc = client(ALICE)
    tc.app.add_middleware(LanguageMiddleware)
    return tc


def _both(tc, path, body):
    return tc.post(path, json=body), tc.post(path, json=body, headers=PT)


def test_datalake_refusals_have_one_code_and_two_languages(dl):
    default, portuguese = _both(dl, "/datalakes/discover", {"provider": "s3"})
    assert default.status_code == portuguese.status_code == 422
    assert _detail(default) == {"code": "DATALAKE_CREDENTIALS_REQUIRED", "message": "Provide the provider credentials."}
    assert _detail(portuguese) == {"code": "DATALAKE_CREDENTIALS_REQUIRED", "message": "Informe as credenciais do provedor"}

    default, portuguese = _both(dl, "/datalakes/discover", {"provider": "gcs", "connection_id": "dl-a"})
    assert default.status_code == portuguese.status_code == 422
    assert _detail(default)["code"] == _detail(portuguese)["code"] == "DATALAKE_PROVIDER_IMMUTABLE"
    assert _detail(default)["message"] != _detail(portuguese)["message"]


def test_the_datalake_404_stays_text_and_is_localized(dl):
    default, portuguese = _both(dl, "/datalakes/discover", {"provider": "s3", "connection_id": "nope"})
    assert default.status_code == portuguese.status_code == 404
    assert _detail(default) == "Connection not found"
    assert _detail(portuguese) == "Conexão não encontrada"


def test_a_pydantic_validated_datalake_text_is_localized_at_raise_time(dl):
    body = {"provider": "s3", "connection_id": "dl-a", "bucket": "a/b"}
    default, portuguese = _both(dl, "/datalakes/discover", body)
    assert default.status_code == portuguese.status_code == 422
    assert "Invalid bucket." in default.text
    assert "Bucket inválido" in portuguese.text


