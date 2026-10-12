"""Automated tests for persistent Feedback/Reviews and PDF binary download (Section 23, 24).
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_feedback_submission_and_persistence():
    # Submit a review
    review_data = {
        "rating": 5,
        "comment": "Incredible door-to-door itinerary planner! Flight and train times matched perfectly.",
        "service_used": "Itinerary Planner"
    }
    res_post = client.post("/api/feedback", json=review_data)
    assert res_post.status_code == 201
    created = res_post.json()
    assert created["rating"] == 5
    assert "Incredible" in created["comment"]
    assert "id" in created

    # List reviews to verify persistent retrieval
    res_get = client.get("/api/feedback")
    assert res_get.status_code == 200
    all_feedback = res_get.json()
    assert isinstance(all_feedback, list)
    matching = [f for f in all_feedback if f["id"] == created["id"]]
    assert len(matching) == 1
    assert matching[0]["comment"] == review_data["comment"]


def test_feedback_invalid_rating():
    res = client.post("/api/feedback", json={"rating": 6, "comment": "Too high"})
    assert res.status_code in (422, 400)


def test_pdf_export_returns_actual_binary():
    payload = {
        "title": "3-Day Golden Temple Itinerary",
        "content": {
            "title": "3-Day Golden Temple Itinerary",
            "destination": "Amritsar",
            "source": "Delhi",
            "duration_days": 3,
            "outbound_transport": {
                "mode": "flight",
                "operator": "IndiGo 6E 2045",
                "departure_time": "06:15",
                "arrival_time": "07:25",
                "price": 3850
            },
            "return_transport": {
                "mode": "train",
                "operator": "Vande Bharat Express",
                "departure_time": "15:15",
                "arrival_time": "20:45",
                "price": 1200
            },
            "hotel": {
                "name": "Taj Swarna, Amritsar",
                "price": 7500,
                "total_price": 15000,
                "rating": 4.7
            },
            "days": [
                {
                    "day_number": 1,
                    "theme": "Sacred Heritage",
                    "estimated_day_cost": "₹3,000",
                    "morning": {
                        "time_window": "08:00 AM – 12:00 PM",
                        "title": "Golden Temple Sacred Darshan",
                        "description": "Visit Harmandir Sahib and Langar Hall.",
                        "transport_note": "Walk 5 mins"
                    },
                    "food_stop_lunch": {
                        "name": "Bhai Kulwant Singh Kulchian",
                        "cuisine": "Punjabi Vegetarian",
                        "recommendation": "Amritsari Aloo Pyaaz Kulcha with Chole"
                    }
                }
            ],
            "estimated_budget_total": "₹23,050 total estimate"
        }
    }

    res = client.post("/api/export/pdf", json=payload)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert "attachment" in res.headers["content-disposition"]
    # Check PDF magic bytes at the beginning of the file
    content = res.content
    assert content.startswith(b"%PDF-")
    assert len(content) > 1000  # Substantial binary PDF generated


def test_area_guide_pdf_and_history_shaped_itinerary_pdf():
    from app.services.pdf_service import pdf_service

    area = {
        "area_name": "Hall Bazaar", "region": "Amritsar", "character_summary": "Busy market quarter.",
        "quick_facts": {"walkability": "High", "vibe": "Lively"},
        "sections": {"food": {"title": "Food", "summary": "Kulcha lanes.", "highlights": ["Kulcha"]}},
        "advantages": ["Central"], "limitations": ["Crowded"], "suitability": ["Food lovers"],
        "source": "test",
    }
    pdf = pdf_service.generate_itinerary_pdf_bytes("Area Guide: Hall Bazaar", area)
    assert pdf.startswith(b"%PDF") and len(pdf) > 1500

    # History payload now stores the full itinerary at top level (days, costs, transport)
    trip = {"title": "Trip", "destination": "Amritsar", "source": "Delhi", "duration_days": 1,
            "selected_outbound_transport": {"mode": "flight", "operator": "IndiGo"}, "days": []}
    assert pdf_service.generate_itinerary_pdf_bytes("Trip", trip).startswith(b"%PDF")


def test_one_review_for_multiple_services_is_saved_per_service():
    from fastapi.testclient import TestClient
    from app.main import app

    c = TestClient(app)
    r = c.post("/api/feedback/multi", json={
        "rating": 4, "comment": "Multi-service review ZZZ",
        "services": ["Itinerary Planner", "Places Near You", "Itinerary Planner", "  "],
    })
    assert r.status_code == 201
    items = r.json()
    assert [i["service_used"] for i in items] == ["Itinerary Planner", "Places Near You"]  # de-duplicated
    assert {i["rating"] for i in items} == {4} and {i["comment"] for i in items} == {"Multi-service review ZZZ"}

    listed = [f for f in c.get("/api/feedback").json() if f["comment"] == "Multi-service review ZZZ"]
    assert len(listed) == 2

    assert c.post("/api/feedback/multi", json={"rating": 5, "comment": "ok ok", "services": []}).status_code == 422
    assert c.post("/api/feedback/multi", json={"rating": 5, "comment": "ok ok", "services": ["   "]}).status_code == 422
