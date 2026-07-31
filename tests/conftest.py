import pytest
from fastapi.testclient import TestClient

from app.adapters import LocalActionExecutor, LocalGrafanaAdapter
from app.api import create_app
from app.service import CutlineService


@pytest.fixture
def service():
    return CutlineService(LocalGrafanaAdapter(), LocalActionExecutor())


@pytest.fixture
def client(service):
    return TestClient(create_app(service))


async def advance_to_approval(service):
    await service.investigate()
    return service.decide(approve=True, approver="Maya Chen")


async def advance_to_verification(service, key="test-execution"):
    await advance_to_approval(service)
    return await service.execute(key)
