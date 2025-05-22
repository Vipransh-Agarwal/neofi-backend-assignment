from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.session import get_db
from ..dependencies import get_current_user
import logging

router = APIRouter(prefix="/api/health", tags=["health"])

@router.get("/")
async def health_check():
    """Basic health check endpoint"""
    return {"status": "healthy"}

@router.get("/detailed")
async def detailed_health_check(db: AsyncSession = Depends(get_db)):
    """Detailed health check that verifies database connectivity"""
    try:
        # Test database connection
        await db.execute("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        logging.error(f"Database health check failed: {str(e)}")
        db_status = "unhealthy"

    return {
        "status": "healthy" if db_status == "healthy" else "unhealthy",
        "components": {
            "api": "healthy",
            "database": db_status
        }
    }

@router.get("/protected")
async def protected_health_check(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Protected health check endpoint with system metrics"""
    import psutil
    try:
        await db.execute("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        logging.error(f"Database health check failed: {str(e)}")
        db_status = "unhealthy"

    return {
        "status": "healthy" if db_status == "healthy" else "unhealthy",
        "components": {
            "api": "healthy",
            "database": db_status
        },
        "metrics": {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage('/').percent
        }
    }
