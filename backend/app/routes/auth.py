from fastapi import Depends, HTTPException, APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.auth_service import (
    register_user,
    login_user,
    refresh_access_token,
    logout_user,
    EmailAlreadyExists,
    InvalidCredentials,
    InvalidToken,
    updateprofile,
    updatepassword,
    deleteuser
)
from app.db.session import get_db
from app.schemas.user import (
    UserAccept,
    UserResponse,
    UserLogin,
    UserTokens,
    RefreshRequest,
    AccessTokenResponse,
    UserUpdate,
    PasswordUpdate,
)
from app.core.dependencies import get_current_user 
from app.db.models import User
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(user: UserAccept, db: AsyncSession = Depends(get_db)):
    try:
        new_user = await register_user(db, user.name, user.email, user.password)
    except EmailAlreadyExists as e:
        raise HTTPException(status_code=409, detail=str(e))
    return new_user


@router.post("/login", response_model=UserTokens)
async def login(user: UserLogin, db: AsyncSession = Depends(get_db)):
    try:
        user_tokens = await login_user(db, user.email, user.password)
    except InvalidCredentials as e:
        raise HTTPException(status_code=401, detail=str(e))
    return user_tokens


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        result = await refresh_access_token(db, payload.refresh_token)
    except InvalidToken as e:
        raise HTTPException(status_code=401, detail=str(e))
    return result


@router.post("/logout", status_code=204)
async def logout(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        await logout_user(db, payload.refresh_token)
    except InvalidToken as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user:User=Depends(get_current_user)):
    return current_user

@router.put("/profile", response_model=UserResponse)
async def update_profile(payload: UserUpdate, current_user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    try:
        updated_user=await updateprofile(db,current_user.id,payload.name,payload.email)
    except EmailAlreadyExists as e:
        raise HTTPException(status_code=409, detail=str(e))
    return updated_user

@router.put("/profile/password", response_model=UserResponse)
async def update_password(payload: PasswordUpdate, current_user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db))->User:
    try:
        updated_user=await updatepassword(db,current_user.id,payload.current_password,payload.new_password)
    except InvalidCredentials as e:
        raise HTTPException(status_code=401, detail=str(e))
    return updated_user

@router.delete("/profile", status_code=204)
async def delete_profile(current_user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    try:
        await deleteuser(db,current_user.id)
    except InvalidCredentials as e:
        raise HTTPException(status_code=401, detail=str(e))