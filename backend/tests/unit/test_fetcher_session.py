import os
import pytest
from unittest.mock import patch
from app.pipeline.fetcher import session

def test_session_configuration():
    assert session.__class__.__name__ == 'CachedSession'
    assert session.cache.__class__.__name__ == 'SQLiteCache'
    
    # Check TTLs (Testing the underlying dict pattern)
    urls_expire_dict = dict(session.settings.urls_expire_after)
    assert '*/v8/finance/chart/^NSEI*' in urls_expire_dict
    assert urls_expire_dict['*/v8/finance/chart/^NSEI*'] == 60
    assert urls_expire_dict['*'] == 86400

    # Check Retries
    adapter = session.get_adapter("https://")
    retry = adapter.max_retries
    assert retry.total == 5
    assert retry.backoff_factor == 2
    assert 429 in retry.status_forcelist
    assert retry.respect_retry_after_header is True
    
    # Check allowed methods (urllib3 v2+ uses allowed_methods)
    assert 'GET' in retry.allowed_methods
