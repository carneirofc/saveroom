from django.core import signing

import pytest
from freezegun import freeze_time

from baserow.api.download.exceptions import DownloadTokenExpired, DownloadTokenInvalid
from baserow.api.download.tokens import (
    BACKUP_DOWNLOAD,
    TABLE_EXPORT_DOWNLOAD,
    check_download_token_matches,
    sign_download_token,
    unsign_download_token,
)


class FakeRequest:
    def __init__(self, payload=None):
        if payload is not None:
            self.download_token_payload = payload


def test_a_token_round_trips():
    token = sign_download_token(7, TABLE_EXPORT_DOWNLOAD, 42)

    payload = unsign_download_token(token)

    assert payload.user_id == 7
    assert payload.type == TABLE_EXPORT_DOWNLOAD
    assert payload.id == 42


def test_an_expired_token_is_refused(settings):
    settings.BASEROW_EXPORT_DOWNLOAD_TOKEN_MAX_AGE_SECONDS = 600

    with freeze_time("2026-01-01 12:00:00"):
        token = sign_download_token(7, TABLE_EXPORT_DOWNLOAD, 42)

    with freeze_time("2026-01-01 12:10:01"):
        with pytest.raises(DownloadTokenExpired):
            unsign_download_token(token)


def test_a_tampered_token_is_refused():
    token = sign_download_token(7, TABLE_EXPORT_DOWNLOAD, 42)

    with pytest.raises(DownloadTokenInvalid):
        unsign_download_token(token[:-1] + ("a" if token[-1] != "a" else "b"))


def test_an_empty_token_is_refused():
    with pytest.raises(DownloadTokenInvalid):
        unsign_download_token("")


def test_a_token_signed_with_another_salt_is_refused():
    """
    The salt keeps a download link from being interchangeable with any other signed
    payload this instance hands out, such as the session payload.
    """

    foreign = signing.TimestampSigner(salt="baserow.some.other.purpose").sign_object(
        {"user_id": 7, "type": TABLE_EXPORT_DOWNLOAD, "id": 42}
    )

    with pytest.raises(DownloadTokenInvalid):
        unsign_download_token(foreign)


def test_a_malformed_payload_is_refused():
    malformed = signing.TimestampSigner(salt="baserow.export.download").sign_object(
        {"user_id": 7}
    )

    with pytest.raises(DownloadTokenInvalid):
        unsign_download_token(malformed)


def test_a_token_is_bound_to_its_object():
    payload = unsign_download_token(sign_download_token(7, BACKUP_DOWNLOAD, 42))

    check_download_token_matches(FakeRequest(payload), BACKUP_DOWNLOAD, 42)

    with pytest.raises(DownloadTokenInvalid):
        check_download_token_matches(FakeRequest(payload), BACKUP_DOWNLOAD, 43)


def test_a_token_is_bound_to_its_type():
    payload = unsign_download_token(sign_download_token(7, TABLE_EXPORT_DOWNLOAD, 42))

    with pytest.raises(DownloadTokenInvalid):
        check_download_token_matches(FakeRequest(payload), BACKUP_DOWNLOAD, 42)


def test_a_request_without_a_token_is_left_alone():
    """
    A request that authenticated with a JWT or an API client key carries no payload;
    its own permission checks already ran.
    """

    check_download_token_matches(FakeRequest(), BACKUP_DOWNLOAD, 42)
