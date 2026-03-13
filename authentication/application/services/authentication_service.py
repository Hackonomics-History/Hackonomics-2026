from .login_service import LoginService
from .logout_service import LogoutService
from .oauth_service import OAuthService
from .refresh_service import RefreshService
from .signup_service import SignupService
from .verify_service import VerifyService


class AuthenticationService:
    def __init__(self):
        self.login_service = LoginService()
        self.signup_service = SignupService()
        self.oauth_service = OAuthService()
        self.logout_service = LogoutService()
        self.refresh_service = RefreshService()
        self.verify_service = VerifyService()

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

    def verify(self, access_token):
        return self.verify_service.verify(access_token)
