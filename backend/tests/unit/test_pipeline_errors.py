from app.pipeline.errors import classify_error
import sqlalchemy.exc

def test_classify_error():
    assert classify_error(Exception("429 Too Many Requests")) == "rate_limit"
    assert classify_error(Exception("Read timed out.")) == "timeout"
    assert classify_error(sqlalchemy.exc.OperationalError("statement", {}, None)) == "db_write"
    assert classify_error(ValueError("Some unknown error")) == "unknown"
    assert classify_error(Exception("No data found for symbol RELIANCE.NS")) == "empty_data"
