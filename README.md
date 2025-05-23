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
   ```bash
   # Verify Python installation
   python --version  # On Windows
   python3 --version # On macOS/Linux
   ```

2. **PostgreSQL 15+**
   - Download and install from [PostgreSQL Official Website](https://www.postgresql.org/download/)
   - Create database:
     ```bash
     # Windows (Using psql)
     psql -U postgres -c "CREATE DATABASE neofi_events"
     
     # macOS/Linux
     createdb neofi_events
     # OR
     psql -U postgres -c "CREATE DATABASE neofi_events"
     ```

3. **Redis**
   - Windows: Follow [How to Install and Use Redis on Windows](https://redis.io/blog/install-redis-windows-11/)
   - macOS: `brew install redis`
   - Linux: `sudo apt-get install redis-server`
   - Start the redis server in separate terminal (For Windows it will be in wsl terminal)

4. **Postman**
   - Download and install from [Download Postman](https://www.postman.com/downloads/)

## Project Setup

1. **Clone Repo**

    ```env
   git clone https://github.com/Vipransh-Agarwal/neofi-backend-assignment.git
   ```
   > You could have done this at very start as well, but no issues, do it now

2. **Environment Setup**

   Update the `.env` file in the project root:
   ```env
   # Windows
   DATABASE_URL=postgresql+asyncpg://postgres:<YOUR_POSTGRES_PASSWORD>@localhost/neofi_events
   SECRET_KEY=<YOUR_SECRET_KEY>

   # macOS/Linux - same format
   DATABASE_URL=postgresql+asyncpg://postgres:<YOUR_POSTGRES_PASSWORD>@localhost/neofi_events
   # ... rest remains the same
   ```

   > **Important**: Replace `<YOUR_POSTGRES_PASSWORD>` with your actual PostgreSQL password and `<YOUR_SECRET_KEY>` with a secure random string. Never commit these values to version control.

4. **Install Dependencies**

   Make sure to first create and activate a python virtual environment. Also check and update the terminal environment as well as update `.env` file with your DATABASE_URL and SECRET_KEY, the one you made `.env` file with.

   Example:
   ```env
   # Windows
   $env:DATABASE_URL = "postgresql+asyncpg://postgres:<YOUR_POSTGRES_PASSWORD>@localhost/neofi_events"
   $env:SECRET_KEY = "<YOUR_SECRET_KEY>"

   # macOS/Linux
   export DATABASE_URL="postgresql+asyncpg://postgres:<YOUR_POSTGRES_PASSWORD>@localhost/neofi_events"
   export SECRET_KEY = "<YOUR_SECRET_KEY>"
   ```
   This will set up environment keys in your local terminal as well

   To check if the environment variables are correctly set:
   ```env
   # Windows
   $env:DATABASE_URL
   $env:SECRET_KEY

   # macOS/Linux
   echo $env:DATABASE_URL
   echo $env:SECRET_KEY
   ```

   Moving On, go inside repo directory `neofi-backend-assignment`, run following commands:
   ```env
   # Windows
   cd .\neofi-backend-assignment\

   # macOS/Linux
   cd ./neofi-backend-assignment/
   ```
   > Make sure you are inside `neofi-backend-assignment` directory, otherwise `poetry` commands may not work
   
   Now run the following commands
   ### Windows
   ```powershell
   # Install Python dependencies
   pip install zstandard
   pip install poetry
   
   # Install project dependencies
   poetry install --no-root
   ```

   ### macOS/Linux
   ```bash
   # Install Python dependencies
   pip3 install zstandard
   pip3 install poetry
   
   # Install project dependencies
   poetry install --no-root
   ```
   > **Important**: If you see an error like: ```pyproject.toml changed significantly since poetry.lock was last generated. Run `poetry lock` to fix the lock file.```, then do not panic, application will still work. First run `poetry lock`, as the error says, then run `poetry install --no-root` again

6. **Database Migrations**
   ```bash
   # Run migrations
   poetry run alembic upgrade head
   ```

7. **Start the Application**
   ```bash
   # Windows/macOS/Linux
   poetry run uvicorn app.main:app --reload
   ```
   > **Important**: If you see a bunch of errors that says something like: ```raise ConnectionError(self._error_message(e))
redis.exceptions.ConnectionError: Error Multiple exceptions: [Errno 10061] Connect call failed ('::1', 6379, 0, 0), [Errno 10061] Connect call failed ('127.0.0.1', 6379) connecting to localhost:6379.```, then your `redis` is not up. Run `redis-server` in a separate termial (wsl for windows) and then come back to main terminal and run `poetry run uvicorn app.main:app --reload` again
 
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

### WebSocket Testing
- Go to: http://localhost:8000/test

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
└── logs/               # Application logs
```
