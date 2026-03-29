# DjangoUserRepository has been removed.
#
# Identity is now resolved from the JWT by JWKSMiddleware.
# Django no longer queries the auth_user table for authentication.
# The Go BFF is the single source of truth for user identity.
