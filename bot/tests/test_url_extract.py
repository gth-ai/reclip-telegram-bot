import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from handlers import URL_REGEX


def test_simple_url():
    urls = URL_REGEX.findall("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert len(urls) == 1
    assert "youtube.com" in urls[0]


def test_url_in_text():
    urls = URL_REGEX.findall("check this out https://www.tiktok.com/@user/video/123 cool right?")
    assert len(urls) == 1
    assert "tiktok.com" in urls[0]


def test_multiple_urls():
    text = "https://youtube.com/watch?v=abc and also https://tiktok.com/@user/video/456"
    urls = URL_REGEX.findall(text)
    assert len(urls) == 2


def test_no_url():
    urls = URL_REGEX.findall("just some text without links")
    assert len(urls) == 0


def test_short_url():
    urls = URL_REGEX.findall("https://youtu.be/dQw4w9WgXcQ")
    assert len(urls) == 1


def test_instagram_reel():
    urls = URL_REGEX.findall("https://www.instagram.com/reel/ABC123/")
    assert len(urls) == 1
    assert "instagram.com" in urls[0]


def test_twitter_url():
    urls = URL_REGEX.findall("https://x.com/user/status/123456789")
    assert len(urls) == 1


def test_reddit_url():
    urls = URL_REGEX.findall("https://www.reddit.com/r/videos/comments/abc123/test/")
    assert len(urls) == 1


def test_url_with_query_params():
    urls = URL_REGEX.findall("https://www.youtube.com/watch?v=abc&list=PLxyz&index=3")
    assert len(urls) == 1
    assert "list=PLxyz" in urls[0]
