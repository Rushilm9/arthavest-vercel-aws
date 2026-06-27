import sys
import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.models import Users
from app.schemas.user import UserCreate, UserLogin, UserResponse, LoginResponse
from app.core.security import get_password_hash, verify_password
from app.core.config import get_db, logger

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED
)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Create a new user account and return the user (same shape as login, so the
    client is logged in immediately after signup). No JWT/session — matches the
    existing stub auth (passwords stored as-is via get_password_hash).
    """
    logger.info(f"Register attempt for email: {user_in.email}")

    existing = db.query(Users).filter(Users.email == user_in.email).first()
    if existing:
        logger.warning(f"Register failed: email already exists {user_in.email}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    user = Users(
        email=user_in.email,
        password_hash=get_password_hash(user_in.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(f"User {user.email} registered successfully.")
    return LoginResponse(message="Registration successful", user=user)


@router.post("/login", response_model=LoginResponse)
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    """
    Simple login returning user details (No JWT).
    """
    logger.info(f"Login attempt for email: {user_in.email}")

    # Authenticate user
    user = db.query(Users).filter(Users.email == user_in.email).first()
    if not user or not verify_password(user_in.password, user.password_hash):
        logger.warning(f"Login failed: Invalid credentials for {user_in.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    logger.info(f"User {user.email} logged in successfully.")
    return LoginResponse(message="Login successful", user=user)


@router.post("/logout")
def logout():
    """
    Since there is no JWT/session cookie being tracked on the backend for now,
    logout is just an endpoint the client can hit to signify dropping local state.
    """
    logger.info("A user logged out.")
    return {"message": "Logged out successfully"}
