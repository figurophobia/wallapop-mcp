"""Photo inputs: local paths pass through; URLs and base64 data URLs become local JPEG files."""
import base64

import pytest

import wallapop_mcp.mcp_server as mcp_server
from wallapop_mcp import photo_inputs

JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 32


def test_local_path_is_unchanged(tmp_path):
    assert photo_inputs.materialize_photo("/srv/a.jpg", tmp_path / "x.jpg") == "/srv/a.jpg"


def test_base64_jpeg_is_written(tmp_path):
    ref = "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()
    path = photo_inputs.materialize_photo(ref, tmp_path / "x.jpg")
    assert open(path, "rb").read() == JPEG


@pytest.mark.parametrize("ref, error", [
    ("data:image/png;base64," + base64.b64encode(JPEG).decode(), "data:image/jpeg"),
    ("data:image/jpeg;base64,!!!", "base64"),
    ("data:image/jpeg;base64," + base64.b64encode(b"GIF89a").decode(), "JPEG"),
    ("http://127.0.0.1/a.jpg", "public"),
    ("http://192.168.1.10/a.jpg", "public"),
    ("https://user:pw@example.com/a.jpg", "plain"),
])
def test_bad_inputs_are_refused(tmp_path, ref, error):
    with pytest.raises(ValueError, match=error):
        photo_inputs.materialize_photo(ref, tmp_path / "x.jpg")


def test_url_photo_is_downloaded(tmp_path, monkeypatch):
    monkeypatch.setattr(photo_inputs, "_check_public_host", lambda host: None)
    monkeypatch.setattr(photo_inputs, "_fetch", lambda url: JPEG)
    path = photo_inputs.materialize_photo("https://example.com/a.jpg", tmp_path / "x.jpg")
    assert open(path, "rb").read() == JPEG


def test_publish_item_materializes_remote_photos(monkeypatch):
    captured = {}

    class Client:
        token = "t"

        def publish(self, **kwargs):
            captured["paths"] = kwargs["photo_paths"]
            captured["bytes"] = [open(p, "rb").read() for p in kwargs["photo_paths"][1:]]
            captured["shipping_allowed"] = kwargs["shipping_allowed"]
            from wallapop_mcp.http import Response
            return Response(200, {"id": "abc123def456"}, True, False)

    monkeypatch.setattr(mcp_server, "_client", Client())
    data_url = "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()
    result = mcp_server.publish_item("T", "D", 10.0, "10311", "good", ["/srv/cover.jpg", data_url], shipping_allowed=False)
    assert result["ok"] is True
    assert captured["paths"][0] == "/srv/cover.jpg" and captured["bytes"] == [JPEG]
    assert captured["shipping_allowed"] is False


def test_publish_item_bad_photo_creates_nothing(monkeypatch):
    class Client:
        token = "t"

        def publish(self, **kwargs):
            raise AssertionError("must not publish")

    monkeypatch.setattr(mcp_server, "_client", Client())
    result = mcp_server.publish_item("T", "D", 10.0, "10311", "good", ["data:image/jpeg;base64,!!!"])
    assert result["ok"] is False and "photo 1" in result["error"]
