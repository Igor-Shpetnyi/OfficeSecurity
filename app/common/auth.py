import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import Settings

security = HTTPBasic()


def require_admin(settings: Settings):
    def _check(credentials: HTTPBasicCredentials = Depends(security)) -> None:
        valid_user = secrets.compare_digest(credentials.username, settings.admin_basic_auth_user)
        valid_pass = secrets.compare_digest(credentials.password, settings.admin_basic_auth_password)
        if not (valid_user and valid_pass):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )

    return _check
