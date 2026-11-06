from app.api import geocoding_routes
from app.geocoding import nominatim_client


def test_reverse_geocode_returns_display_name(monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"display_name": "Majestic, Bengaluru, Karnataka, India"}

    monkeypatch.setattr(nominatim_client, "_wait_for_rate_limit", lambda: None)
    monkeypatch.setattr(nominatim_client.requests, "get", lambda *args, **kwargs: Response())

    assert nominatim_client.reverse_geocode(12.9767, 77.5713) == "Majestic, Bengaluru, Karnataka, India"


def test_reverse_geocode_returns_none_when_provider_has_no_address(monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"place_id": 123}

    monkeypatch.setattr(nominatim_client, "_wait_for_rate_limit", lambda: None)
    monkeypatch.setattr(nominatim_client.requests, "get", lambda *args, **kwargs: Response())

    assert nominatim_client.reverse_geocode(12.9767, 77.5713) is None


def test_reverse_geocode_route_returns_display_name(monkeypatch):
    monkeypatch.setattr(
        geocoding_routes,
        "reverse_geocode",
        lambda latitude, longitude: "Rajajinagar, Bengaluru, India",
    )
    result = geocoding_routes.geocode_reverse(
        latitude=13.0,
        longitude=77.55,
        current_user=object(),
    )
    assert result.display_name == "Rajajinagar, Bengaluru, India"


def test_reverse_geocode_rejects_out_of_range_coordinates():
    import pytest

    with pytest.raises(ValueError, match="valid range"):
        nominatim_client.reverse_geocode(91, 77.55)
