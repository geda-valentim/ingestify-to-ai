"""strict_content_type=False on the app reaches JSON routes of included routers (FastAPI 0.104 behaviour)."""
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from api.main import app


class Payload(BaseModel):
    name: str


def test_json_body_without_content_type_is_still_parsed():
    router = APIRouter()

    @router.post("/_test/json-without-content-type")
    def echo(payload: Payload):
        return {"name": payload.name}

    first_new_route = len(app.routes)
    app.include_router(router)
    try:
        response = TestClient(app).post("/_test/json-without-content-type", content=b'{"name": "x"}')
    finally:
        del app.routes[first_new_route:]
        app.openapi_schema = None

    assert response.status_code == 200
    assert response.json() == {"name": "x"}
