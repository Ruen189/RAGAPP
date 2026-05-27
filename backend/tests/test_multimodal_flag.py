from fastapi import HTTPException


def validate_multimodal(model_multimodal: bool, has_attachments: bool):
    if has_attachments and not model_multimodal:
        raise HTTPException(status_code=400, detail="Простите, я понимаю только текст")


def test_multimodal_disabled_rejects_attachments():
    try:
        validate_multimodal(False, True)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "только текст" in exc.detail
    else:
        assert False


def test_multimodal_enabled_allows_attachments():
    validate_multimodal(True, True)


def test_multimodal_disabled_without_attachments_is_ok():
    validate_multimodal(False, False)
