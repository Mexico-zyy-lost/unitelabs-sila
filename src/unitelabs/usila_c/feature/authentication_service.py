import typing_extensions as typing
from sila import FeatureIdentifier
from unitelabs.cdk.features.core import authentication_service


class AuthenticationService(authentication_service.AuthenticationService):
    @typing.override
    async def validate(self, username: str, password: str, scope: list[FeatureIdentifier]) -> bool:
        return (username, password) == ("test", "test")
