"""Stand-in for feedparser in offline tests (tests replace parse())."""


def parse(*args, **kwargs):
    raise RuntimeError("network is not available in tests")
