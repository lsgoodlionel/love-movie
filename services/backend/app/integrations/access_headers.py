from dataclasses import dataclass

from pydantic import SecretStr


@dataclass(frozen=True)
class AccessHeaders:
    client_id: SecretStr
    client_secret: SecretStr

    @classmethod
    def empty(cls) -> "AccessHeaders":
        return cls(SecretStr(""), SecretStr(""))

    def as_dict(self) -> dict[str, str]:
        client_id = self.client_id.get_secret_value()
        client_secret = self.client_secret.get_secret_value()
        if not client_id and not client_secret:
            return {}
        return {
            "CF-Access-Client-Id": client_id,
            "CF-Access-Client-Secret": client_secret,
        }

    def secret_values(self) -> tuple[str, ...]:
        return tuple(
            value
            for value in (self.client_id.get_secret_value(), self.client_secret.get_secret_value())
            if value
        )
