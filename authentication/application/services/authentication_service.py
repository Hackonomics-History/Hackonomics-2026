from .login_service import LoginService
from .logout_service import LogoutService
from .oauth_service import OAuthService
from .refresh_service import RefreshService
from .signup_service import SignupService


class AuthenticationService:
    def __init__(self):
        self.login_service = LoginService()
        self.signup_service = SignupService()
        self.oauth_service = OAuthService()
        self.logout_service = LogoutService()
        self.refresh_service = RefreshService()
        # VerifyService removed — token verification is handled by JWKSMiddleware

    def login(self, email, password, device_id, remember_me):
        return self.login_service.login(email, password, device_id, remember_me)

    def google_login(self, code):
        return self.oauth_service.google_login(code)

    def signup(self, email, password):
        return self.signup_service.signup(email, password)

    def logout(self, refresh_token):
        return self.logout_service.logout(refresh_token)

    def refresh(self, refresh_token):
        return self.refresh_service.refresh(refresh_token)
