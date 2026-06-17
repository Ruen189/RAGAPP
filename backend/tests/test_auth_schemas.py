import pytest
from pydantic import ValidationError

from app.schemas import RegisterRequest


def test_register_password_too_short():
    with pytest.raises(ValidationError) as exc:
        RegisterRequest(login="student", password="123456")
    assert "8 символов" in str(exc.value)


def test_register_password_without_letter():
    with pytest.raises(ValidationError) as exc:
        RegisterRequest(login="student", password="12345678")
    assert "букву" in str(exc.value)


def test_register_password_without_digit():
    with pytest.raises(ValidationError) as exc:
        RegisterRequest(login="student", password="abcdefgh")
    assert "цифру" in str(exc.value)


def test_register_password_ok():
    payload = RegisterRequest(login="student", password="student1")
    assert payload.password == "student1"
