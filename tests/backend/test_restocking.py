"""
Tests for restocking API endpoints.
"""
from datetime import datetime

import pytest


class TestRestockRecommendationsEndpoints:
    """Test suite for restocking recommendation endpoints."""

    def test_get_all_recommendations(self, client):
        """Test getting all restocking recommendations."""
        response = client.get("/api/restock/recommendations")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        first = data[0]
        for field in [
            "item_sku", "item_name", "category", "warehouse", "trend", "period",
            "current_demand", "forecasted_demand", "current_stock", "target_stock",
            "shortfall", "recommended_quantity", "unit_cost", "line_cost",
            "lead_time_days", "priority_score"
        ]:
            assert field in first

    def test_recommendations_sorted_by_priority(self, client):
        """Test that recommendations are returned highest priority first."""
        response = client.get("/api/restock/recommendations")
        data = response.json()

        scores = [item["priority_score"] for item in data]
        assert scores == sorted(scores, reverse=True)

    def test_recommendation_line_cost_calculation(self, client):
        """Test that line cost equals quantity times unit cost."""
        response = client.get("/api/restock/recommendations")
        data = response.json()

        for item in data:
            calculated = item["recommended_quantity"] * item["unit_cost"]
            assert abs(item["line_cost"] - calculated) < 0.01

    def test_recommendation_shortfall_calculation(self, client):
        """Test that shortfall equals target stock minus current stock."""
        response = client.get("/api/restock/recommendations")
        data = response.json()

        for item in data:
            assert item["shortfall"] == item["target_stock"] - item["current_stock"]
            assert item["recommended_quantity"] == item["shortfall"]

    def test_recommendations_exclude_covered_items(self, client):
        """Test that items already stocked past target are not recommended."""
        response = client.get("/api/restock/recommendations")
        data = response.json()

        for item in data:
            assert item["recommended_quantity"] > 0

        # BRG-102 is stocked above its target, so it should never appear
        skus = [item["item_sku"] for item in data]
        assert "BRG-102" not in skus

    def test_recommendation_target_stock_uses_integer_ceiling(self, client):
        """Test that target stock uses integer ceiling, not float arithmetic.

        math.ceil(450 * 1.1) returns 496 and math.ceil(600 * 1.1) returns 661
        because of float representation. The correct values are 495 and 660.
        """
        response = client.get("/api/restock/recommendations")
        data = response.json()

        by_sku = {item["item_sku"]: item for item in data}
        assert by_sku["WDG-001"]["target_stock"] == 495
        assert by_sku["GSK-203"]["target_stock"] == 660

    def test_get_recommendations_by_warehouse(self, client):
        """Test filtering recommendations by warehouse."""
        response = client.get("/api/restock/recommendations?warehouse=Tokyo")
        assert response.status_code == 200

        data = response.json()
        assert len(data) > 0

        for item in data:
            assert item["warehouse"] == "Tokyo"

    def test_get_recommendations_by_category(self, client):
        """Test filtering recommendations by category, case-insensitively."""
        response = client.get("/api/restock/recommendations?category=power supplies")
        assert response.status_code == 200

        data = response.json()
        assert len(data) > 0

        for item in data:
            assert item["category"].lower() == "power supplies"

    def test_get_recommendations_with_all_filter(self, client):
        """Test that 'all' filters are ignored."""
        unfiltered = client.get("/api/restock/recommendations").json()
        filtered = client.get(
            "/api/restock/recommendations?warehouse=all&category=all"
        ).json()

        assert len(filtered) == len(unfiltered)

    def test_recommendation_lead_times_in_range(self, client):
        """Test that lead times fall in the same 7 to 14 day band as orders."""
        response = client.get("/api/restock/recommendations")
        data = response.json()

        for item in data:
            assert isinstance(item["lead_time_days"], int)
            assert 7 <= item["lead_time_days"] <= 14


class TestRestockOrderSubmissionEndpoints:
    """Test suite for restocking order submission endpoints."""

    def test_get_submitted_orders_empty_by_default(self, client):
        """Test that no restocking orders exist before any are submitted."""
        response = client.get("/api/restock/orders")
        assert response.status_code == 200

        data = response.json()
        assert data == []

    def test_submit_restock_order_creates_order(self, client, sample_restock_request):
        """Test submitting a restocking order."""
        response = client.post("/api/restock/orders", json=sample_restock_request)
        assert response.status_code == 201

        order = response.json()
        assert order["order_number"].startswith("RST-")
        assert order["status"] == "Submitted"
        assert len(order["items"]) == len(sample_restock_request["items"])
        assert order["budget"] == sample_restock_request["budget"]

    def test_submitted_order_item_structure(self, client, sample_restock_request):
        """Test that submitted order items match the shape of regular order items."""
        response = client.post("/api/restock/orders", json=sample_restock_request)
        order = response.json()

        for item in order["items"]:
            assert "sku" in item
            assert "name" in item
            assert "quantity" in item
            assert "unit_price" in item
            assert "lead_time_days" in item
            assert isinstance(item["quantity"], int)
            assert isinstance(item["unit_price"], (int, float))

    def test_submitted_order_total_value_calculation(self, client):
        """Test that total value matches the sum of its line items."""
        response = client.post("/api/restock/orders", json={
            "budget": 30000,
            "items": [
                {"item_sku": "WDG-001", "quantity": 375},
                {"item_sku": "GSK-203", "quantity": 450}
            ]
        })
        order = response.json()

        calculated = sum(
            item["quantity"] * item["unit_price"] for item in order["items"]
        )
        assert abs(order["total_value"] - calculated) < 0.01

    def test_submitted_order_uses_server_side_pricing(self, client):
        """Test that unit prices come from the forecast, not the request."""
        forecasts = client.get("/api/demand").json()
        expected_cost = next(
            f["unit_cost"] for f in forecasts if f["item_sku"] == "WDG-001"
        )

        response = client.post("/api/restock/orders", json={
            "items": [{"item_sku": "WDG-001", "quantity": 10}]
        })
        order = response.json()

        assert order["items"][0]["unit_price"] == expected_cost

    def test_submitted_order_expected_delivery_matches_lead_time(self, client, sample_restock_request):
        """Test that expected delivery is the order date plus the lead time."""
        response = client.post("/api/restock/orders", json=sample_restock_request)
        order = response.json()

        date_format = "%Y-%m-%dT%H:%M:%S"
        order_date = datetime.strptime(order["order_date"], date_format)
        expected_delivery = datetime.strptime(order["expected_delivery"], date_format)

        assert (expected_delivery - order_date).days == order["lead_time_days"]

    def test_submitted_order_lead_time_is_max_of_items(self, client):
        """Test that order lead time is the slowest line item's lead time."""
        response = client.post("/api/restock/orders", json={
            "items": [
                {"item_sku": "FLT-405", "quantity": 100},
                {"item_sku": "MTR-304", "quantity": 5}
            ]
        })
        order = response.json()

        assert order["lead_time_days"] == max(
            item["lead_time_days"] for item in order["items"]
        )

    def test_submit_nonexistent_sku(self, client):
        """Test submitting an order for an item that doesn't exist."""
        response = client.post("/api/restock/orders", json={
            "items": [{"item_sku": "NOPE-999", "quantity": 5}]
        })
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_submit_empty_items(self, client):
        """Test that an order with no items is rejected."""
        response = client.post("/api/restock/orders", json={"items": []})
        assert response.status_code == 400

    def test_submit_zero_quantity(self, client):
        """Test that a non-positive quantity fails validation."""
        response = client.post("/api/restock/orders", json={
            "items": [{"item_sku": "WDG-001", "quantity": 0}]
        })
        assert response.status_code == 422

    def test_order_numbers_increment(self, client, sample_restock_request):
        """Test that submitted orders get sequential numbers."""
        first = client.post("/api/restock/orders", json=sample_restock_request).json()
        second = client.post("/api/restock/orders", json=sample_restock_request).json()

        assert first["order_number"].endswith("-0001")
        assert second["order_number"].endswith("-0002")
        assert first["id"] == "1"
        assert second["id"] == "2"

    def test_submitted_order_appears_in_list(self, client, sample_restock_request):
        """Test that a submitted order is returned by the list endpoint."""
        created = client.post("/api/restock/orders", json=sample_restock_request).json()

        response = client.get("/api/restock/orders")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["order_number"] == created["order_number"]

    def test_submitted_orders_do_not_pollute_orders_endpoint(self, client, sample_restock_request):
        """Test that restocking orders stay out of the regular orders list."""
        before = len(client.get("/api/orders").json())

        client.post("/api/restock/orders", json=sample_restock_request)

        after = client.get("/api/orders").json()
        assert len(after) == before
        assert all(not o["order_number"].startswith("RST-") for o in after)

    def test_submitted_orders_do_not_pollute_quarterly_report(self, client, sample_restock_request):
        """Test that restocking orders do not affect quarterly reporting."""
        before = client.get("/api/reports/quarterly").json()

        client.post("/api/restock/orders", json=sample_restock_request)

        after = client.get("/api/reports/quarterly").json()
        assert after == before
