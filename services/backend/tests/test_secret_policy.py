from app.core.config import Settings


def test_settings_repr_hides_access_secret() -> None:
    secret = "do-not-print-this-secret"
    settings = Settings(
        cf_access_client_id="client-id",
        cf_access_client_secret=secret,
    )

    assert secret not in repr(settings)
    assert settings.cf_access_client_secret.get_secret_value() == secret
