# VerifyService has been removed.
#
# Token verification is now handled entirely by JWKSMiddleware, which
# validates the JWT locally using the Go BFF JWKS endpoint.
# Django no longer makes a network call to /auth/verify on every request.
