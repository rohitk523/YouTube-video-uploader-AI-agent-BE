# Backend Context and Architecture

This backend service is part of a YouTube video uploader AI agent, designed to automate the process of uploading videos to YouTube, potentially with AI-generated content like transcripts and voiceovers.

## Key Technologies:

*   **Web Framework:** FastAPI (for building robust and high-performance APIs)
*   **Asynchronous Programming:** Uvicorn (ASGI server for FastAPI)
*   **Database:** PostgreSQL (via `asyncpg` driver)
*   **ORM/Migrations:** SQLAlchemy and Alembic (for database interactions and schema management)
*   **Data Validation:** Pydantic (for data parsing and validation)
*   **Authentication:** `python-jose` and `passlib` (for JWT-based authentication and password hashing)
*   **Background Tasks:** Celery with Redis (for asynchronous job processing, e.g., video encoding, YouTube uploads)
*   **Cloud Storage:** Boto3 (for interacting with AWS S3 for file storage)
*   **AI/External APIs:**
    *   OpenAI (for Text-to-Speech (TTS) services)
    *   Google API Python Client (`google-api-python-client`, `google-auth`, `google-auth-oauthlib`) (for YouTube API interactions, including OAuth2)
*   **Observability:** Langfuse (for tracing and monitoring AI applications)
*   **Utilities:** `python-dotenv`, `httpx`, `aiofiles`

## Architecture Overview:

The backend follows a layered architecture, typical for modern web applications, with a focus on asynchronous processing to handle potentially long-running tasks like video uploads and AI processing.

1.  **API Layer (FastAPI):**
    *   Handles incoming HTTP requests (e.g., video upload requests, job status checks).
    *   Defines API endpoints for various functionalities like authentication, video management, job creation, and YouTube interactions.
    *   Uses Pydantic for request and response data validation.

2.  **Services Layer:**
    *   Contains business logic and orchestrates interactions with other components.
    *   Examples include `video_service.py`, `youtube_service.py`, `ai_transcript_service.py`, `s3_service.py`, `job_service.py`.
    *   Responsible for tasks like video processing, interacting with external APIs (YouTube, OpenAI), and managing file storage.

3.  **Repository Layer:**
    *   Abstracts database interactions.
    *   Provides methods for CRUD (Create, Read, Update, Delete) operations on database models (e.g., `video_repository.py`).
    *   Uses SQLAlchemy for ORM capabilities.

4.  **Database (PostgreSQL):**
    *   Persists application data, including video metadata, user information, and job statuses.
    *   Managed with SQLAlchemy and Alembic for migrations.

5.  **Background Task Queue (Celery with Redis):**
    *   Offloads long-running or resource-intensive tasks from the main API thread.
    *   Redis acts as the message broker for Celery.
    *   Tasks include video encoding, uploading to YouTube, generating transcripts, and TTS processing.

6.  **File Storage (AWS S3):**
    *   Used for storing large files such as raw video uploads, processed videos, and other media assets.
    *   Integrated via the Boto3 library.

7.  **Authentication:**
    *   Implements JWT (JSON Web Token) based authentication for securing API endpoints.
    *   Users authenticate to receive a token, which is then used for subsequent requests.

8.  **Observability (Langfuse):**
    *   Integrated to provide tracing and monitoring capabilities, especially for AI-related operations, helping to debug and optimize AI workflows.

This architecture ensures scalability, responsiveness, and maintainability by separating concerns and leveraging asynchronous processing for demanding operations.