from drf_spectacular.extensions import OpenApiAuthenticationExtension

from authentication.adapters.django.jwt_authentication import JWTAuthentication


# For Swagger UI
class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = JWTAuthentication
    name = "CookieAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": "access_token",
            "description": "JWT stored in httpOnly cookie 'access_token'.",
        }
