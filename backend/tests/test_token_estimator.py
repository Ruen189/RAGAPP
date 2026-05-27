from app.services.token_estimator import TokenEstimator


def test_token_estimator_non_zero():
    assert TokenEstimator.count("abc") >= 1


def test_token_estimator_empty():
    assert TokenEstimator.count("") == 0


def test_token_estimator_scales_with_text():
    short = TokenEstimator.count("короткий текст")
    long = TokenEstimator.count("длинный текст " * 200)
    assert long > short
