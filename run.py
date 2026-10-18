"""AI Powered Travel Companion - Application Runner.
Starts the FastAPI backend dev server with live reload.
Serves both API endpoints and the frontend application seamlessly.
"""

import sys
from pathlib import Path
import uvicorn

# Ensure backend directory is in Python path
ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings

if __name__ == "__main__":
    print(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"Server running at: http://{settings.HOST}:{settings.PORT}")
    print(f"Frontend accessible at: http://{settings.HOST}:{settings.PORT}/")
    print(f"Health check at: http://{settings.HOST}:{settings.PORT}/api/health")
    print(f"Mode: {'MOCK DATA (No API keys needed)' if settings.MOCK_MODE else 'LIVE'}")
    print("Press Ctrl+C to stop.")

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        reload_dirs=[str(BACKEND_DIR / "app")]
    )
