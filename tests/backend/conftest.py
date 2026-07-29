"""
Pytest configuration and fixtures for backend API tests.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add server directory to path
server_path = Path(__file__).parent.parent.parent / "server"
sys.path.insert(0, str(server_path))

from main import app
from mock_data import submitted_orders


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_submitted_orders():
    """Keep runtime-submitted restocking orders from leaking between tests.

    submitted_orders is a module-level list, so a POST in one test would
    otherwise survive for the whole pytest process and make order-number
    assertions depend on test ordering. Clear on both sides of the yield so a
    test that raises cannot poison the next one, and always clear in place:
    rebinding would leave main.py holding the original list.
    """
    submitted_orders.clear()
    yield
    submitted_orders.clear()


@pytest.fixture
def sample_inventory_item():
    """Sample inventory item for testing."""
    return {
        "id": "1",
        "sku": "PCB-001",
        "name": "Single Layer PCB Assembly",
        "category": "Circuit Boards",
        "warehouse": "San Francisco",
        "quantity_on_hand": 450,
        "reorder_point": 200,
        "unit_cost": 24.99,
        "location": "Warehouse A-12",
        "last_updated": "2025-09-30T10:30:00"
    }


@pytest.fixture
def sample_restock_request():
    """Sample restocking order request body for testing."""
    return {
        "budget": 22000,
        "items": [
            {"item_sku": "WDG-001", "quantity": 375},
            {"item_sku": "GSK-203", "quantity": 450},
            {"item_sku": "CTL-330", "quantity": 66}
        ]
    }


@pytest.fixture
def sample_order():
    """Sample order for testing."""
    return {
        "id": "1",
        "order_number": "ORD-2025-0001",
        "customer": "MegaCorp Industries",
        "items": [
            {
                "sku": "SPR-602",
                "name": "Compression Spring",
                "quantity": 981,
                "unit_price": 89.5
            }
        ],
        "status": "Delivered",
        "warehouse": "Tokyo",
        "category": "Sensors",
        "order_date": "2025-01-08T10:19:00",
        "expected_delivery": "2025-01-21T10:19:00",
        "total_value": 87799.5,
        "actual_delivery": "2025-01-20T10:19:00"
    }
