# NeoFi Collaborative Event Management System

A RESTful API for an event scheduling application with collaborative editing features, built with FastAPI.

## Features

- 🔐 **Authentication & Authorization**
  - Token-based authentication with JWT
  - Role-based access control (Owner, Editor, Viewer)
  - Secure password hashing

- 📅 **Event Management**
  - CRUD operations for events
  - Recurring events support
  - Conflict detection
  - Batch operations

- 👥 **Collaboration**
  - Granular permissions system
  - Real-time notifications (WebSocket)
  - Edit history tracking

- 📝 **Version Control**
  - Full versioning system
  - Version rollback capability
  - Changelog with diff visualization
  - Atomic operations

## Prerequisites

1. **Python 3.11+**
   ```powershell
   winget install Python.Python.3.11
   ```

2. **PostgreSQL 15+**
   ```powershell
   winget install PostgreSQL.PostgreSQL
   ```
   After installation:
   - Create a database: `createdb neofi_events`

3. **Redis**
   ```powershell
   # Using WSL2 on Windows
   wsl --install
   wsl
   sudo apt-get update
   sudo apt-get install redis-server
   sudo service redis-server start
   ```

## Project Setup

1. **Environment Setup**
   Create a `.env` file in the project root:
   ```env
   DATABASE_URL=postgresql+asyncpg://postgres:your_password@localhost/neofi_events
   REDIS_URL=redis://localhost:6379/0
   SECRET_KEY=your-secret-key-here
   ACCESS_TOKEN_EXPIRE_MINUTES=30
   REFRESH_TOKEN_EXPIRE_DAYS=7
   ```

2. **Install Dependencies**
   ```powershell
   # Install zstandard first (required for some dependencies)
   pip install zstandard

   # Install Poetry
   pip install poetry

   # Initialize poetry (if not already done)
   poetry init

   # Install project dependencies
   poetry install
   ```

3. **Database Migrations**
   ```powershell
   # Initialize alembic (if not done)
   alembic init alembic

   # Run migrations
   alembic upgrade head
   ```

4. **Start the Application**
   ```powershell
   uvicorn app.main:app --reload
   ```

## API Endpoints

### Authentication
- POST `/api/auth/register` - Register new user
- POST `/api/auth/login` - Login and get token
- POST `/api/auth/refresh` - Refresh auth token
- POST `/api/auth/logout` - Logout user

### Event Management
- POST `/api/events` - Create event
- GET `/api/events` - List all accessible events
- GET `/api/events/{id}` - Get specific event
- PUT `/api/events/{id}` - Update event
- DELETE `/api/events/{id}` - Delete event
- POST `/api/events/batch` - Batch create events

### Collaboration
- POST `/api/events/{id}/share` - Share event
- GET `/api/events/{id}/permissions` - List permissions
- PUT `/api/events/{id}/permissions/{userId}` - Update permissions
- DELETE `/api/events/{id}/permissions/{userId}` - Remove access

### Version Control
- GET `/api/events/{id}/history/{versionId}` - Get version
- POST `/api/events/{id}/rollback/{versionId}` - Rollback
- GET `/api/events/{id}/changelog` - View changes
- GET `/api/events/{id}/diff/{versionId1}/{versionId2}` - Compare versions

### Health Check
- GET `/api/health` - Basic health check
- GET `/api/health/detailed` - Detailed system status

## Testing

Run the test suite:
```powershell
poetry run pytest
```

## Documentation

- API Documentation (Swagger): http://localhost:8000/docs 
- Alternative Documentation (ReDoc): http://localhost:8000/redoc

## Project Structure

```
neofi-backend-assignment/
├── alembic/              # Database migrations
├── app/
│   ├── core/            # Core functionality
│   ├── db/              # Database configuration
│   ├── middleware/      # Custom middleware
│   ├── routers/         # API routes
│   ├── utils/           # Utility functions
│   └── main.py         # Application entry point
├── tests/              # Test suite
└── logs/               # Application logs
```