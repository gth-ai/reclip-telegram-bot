import pytest
import httpx
from unittest.mock import AsyncMock, patch

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from reclip_client import (
    get_info,
    start_download,
    poll_status,
    ReclipInfoError,
    ReclipDownloadError,
    ReclipServiceDown,
    ReclipError,
)


@pytest.fixture
def mock_response():
    def _make(status_code=200, json_data=None):
        from unittest.mock import MagicMock
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        if status_code >= 400:
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "error", request=MagicMock(), response=resp
            )
        return resp
    return _make


class TestGetInfo:
    @pytest.mark.asyncio
    async def test_success(self, mock_response):
        info = {
            "title": "Test Video",
            "thumbnail": "https://example.com/thumb.jpg",
            "duration": 120,
            "uploader": "TestUser",
            "extractor": "youtube",
            "formats": [{"id": "22", "label": "720p", "height": 720}],
        }
        resp = mock_response(200, info)
        with patch("reclip_client._client") as mock_client:
            client = AsyncMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=resp)
            mock_client.return_value = client

            result = await get_info("https://youtube.com/watch?v=test")
            assert result["title"] == "Test Video"
            assert result["extractor"] == "youtube"

    @pytest.mark.asyncio
    async def test_connection_error(self):
        with patch("reclip_client._client") as mock_client:
            client = AsyncMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client.return_value = client

            with pytest.raises(ReclipServiceDown):
                await get_info("https://youtube.com/watch?v=test")

    @pytest.mark.asyncio
    async def test_timeout(self):
        with patch("reclip_client._client") as mock_client:
            client = AsyncMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_client.return_value = client

            with pytest.raises(ReclipInfoError, match="timed out"):
                await get_info("https://youtube.com/watch?v=test")

    @pytest.mark.asyncio
    async def test_http_error(self, mock_response):
        resp = mock_response(400, {"error": "Unsupported URL"})
        with patch("reclip_client._client") as mock_client:
            client = AsyncMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=resp)
            mock_client.return_value = client

            with pytest.raises(ReclipInfoError):
                await get_info("https://invalid-site.com/nope")


class TestStartDownload:
    @pytest.mark.asyncio
    async def test_success(self, mock_response):
        resp = mock_response(200, {"job_id": "abc1234567"})
        with patch("reclip_client._client") as mock_client:
            client = AsyncMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=resp)
            mock_client.return_value = client

            job_id = await start_download("https://youtube.com/watch?v=test", "video", "22", "Test")
            assert job_id == "abc1234567"

    @pytest.mark.asyncio
    async def test_service_down(self):
        with patch("reclip_client._client") as mock_client:
            client = AsyncMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client.return_value = client

            with pytest.raises(ReclipServiceDown):
                await start_download("https://youtube.com/watch?v=test", "video", None, "Test")


class TestPollStatus:
    @pytest.mark.asyncio
    async def test_done(self, mock_response):
        data = {
            "status": "done",
            "filename": "test.mp4",
            "file_path": "/downloads/abc1234567.mp4",
            "progress": None,
        }
        resp = mock_response(200, data)
        with patch("reclip_client._client") as mock_client:
            client = AsyncMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.get = AsyncMock(return_value=resp)
            mock_client.return_value = client

            result = await poll_status("abc1234567")
            assert result["status"] == "done"
            assert result["file_path"] == "/downloads/abc1234567.mp4"

    @pytest.mark.asyncio
    async def test_downloading_with_progress(self, mock_response):
        data = {
            "status": "downloading",
            "progress": {"percent": 45.2, "downloaded_bytes": 23000000, "total_bytes": 51000000},
        }
        resp = mock_response(200, data)
        with patch("reclip_client._client") as mock_client:
            client = AsyncMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.get = AsyncMock(return_value=resp)
            mock_client.return_value = client

            result = await poll_status("abc1234567")
            assert result["status"] == "downloading"
            assert result["progress"]["percent"] == 45.2

    @pytest.mark.asyncio
    async def test_error(self, mock_response):
        data = {"status": "error", "error": "Download timed out (5 min limit)"}
        resp = mock_response(200, data)
        with patch("reclip_client._client") as mock_client:
            client = AsyncMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.get = AsyncMock(return_value=resp)
            mock_client.return_value = client

            result = await poll_status("abc1234567")
            assert result["status"] == "error"
