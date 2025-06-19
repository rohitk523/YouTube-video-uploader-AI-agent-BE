# YouTube Shorts Creator API 🚀

A powerful FastAPI backend for creating YouTube Shorts with AI-generated voiceovers using OAuth 2.0 authentication and Google ADK integration.

## ✨ Features

- **🔐 OAuth 2.0 Authentication**: Secure, standards-compliant authentication with scope-based authorization
- **🎬 Video Processing**: Upload and process videos for YouTube Shorts format
- **🗣️ AI Voiceover**: Generate natural-sounding voiceovers with multiple voice options
- **📺 YouTube Integration**: Automatic upload to YouTube with metadata
- **📊 Progress Tracking**: Real-time job progress monitoring
- **🔄 Background Processing**: Asynchronous video processing pipeline
- **🗄️ Database Integration**: PostgreSQL with async SQLAlchemy
- **📁 File Management**: Secure file upload and storage system
- **🔒 Security**: OAuth 2.0, CORS protection and file validation
- **📈 Health Monitoring**: Comprehensive health checks and monitoring

## 🏗️ Architecture

### Tech Stack
- **Framework**: FastAPI 0.104+
- **Authentication**: OAuth 2.0 with JWT tokens and scope-based authorization
- **Database**: PostgreSQL with AsyncPG
- **ORM**: SQLAlchemy 2.0+ (async)
- **Background Jobs**: Celery + Redis
- **File Storage**: Local filesystem with cleanup
- **AI Integration**: Google ADK 1.1.1
- **Deployment**: Render.com ready

### Project Structure
```
app/
├── __init__.py
├── main.py                 # FastAPI app entry point
├── config.py               # Configuration management
├── database.py             # Database setup and connection
├── models/                 # SQLAlchemy models
│   ├── job.py             # Job tracking model
│   ├── user.py            # User authentication model
│   └── upload.py          # File upload model
├── schemas/               # Pydantic schemas
│   ├── auth.py           # OAuth 2.0 authentication schemas
│   ├── job.py            # Job-related schemas
│   └── upload.py         # Upload schemas
├── api/                   # API endpoints
│   ├── oauth.py          # OAuth 2.0 authentication endpoints
│   ├── upload.py         # File upload endpoints
│   ├── jobs.py           # Job management
│   └── youtube.py        # YouTube operations
├── services/              # Business logic
│   ├── auth.py           # Authentication service
│   ├── file_service.py   # File handling
│   ├── job_service.py    # Job management
│   └── youtube_service.py # YouTube integration
├── core/                  # Core functionality
│   ├── middleware.py     # CORS, security, logging
│   └── dependencies.py   # FastAPI dependencies
└── agents/               # Google ADK integration
    └── youtube_agent.py  # Enhanced YouTube agent
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 14+ (or Docker)
- Redis 6+ (or Docker)
- FFmpeg (for video processing)

### 🎯 Easy Setup (Recommended)

**Just run our startup scripts!** 🚀

1. **Clone the repository**
```bash
git clone <repository-url>
cd YouTube-video-uploader-AI-agent-BE
```

2. **Start Development Environment**
```bash
# Make script executable (if needed)
chmod +x start-dev.sh

# Run the development script
./start-dev.sh
```

**That's it!** The script will:
- ✅ Create conda environment with Python 3.11
- ✅ Install all dependencies
- ✅ Create `.env.dev` from template
- ✅ Set up directories
- ✅ Give you deployment options (local vs Docker)
- ✅ Start the application

### 🐳 Development Options

The `start-dev.sh` script offers three deployment modes:

1. **Local Everything** - Run Redis, PostgreSQL, and FastAPI locally
2. **Docker Infrastructure** - Use Docker for Redis/PostgreSQL, FastAPI locally
3. **Full Docker** - Everything in containers

### 🛠️ Manual Setup (Alternative)

If you prefer manual setup, here are both virtual environment options:

#### Option 1: Using Conda (Recommended)
```bash
# Create conda environment
conda create -n youtube-shorts-api python=3.11 -y
conda activate youtube-shorts-api

# Install dependencies
pip install -r requirements.txt
```

#### Option 2: Using venv
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

#### Manual Environment Setup
```bash
# Copy environment template
cp env.template.dev .env.dev
# Edit .env.dev with your configuration

# Create directories
mkdir -p uploads temp static logs

# Start services (if running locally)
redis-server  # In separate terminal
# PostgreSQL should be running

# Run application
uvicorn app.main:app --reload --env-file .env.dev
```

### 📋 API Documentation

### Base URL
```
http://localhost:8000/api/v1
```

### Authentication (OAuth 2.0)

First, register and get tokens:

```bash
# Register a new user
curl -X POST "http://localhost:8000/api/v1/oauth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "secure123",
    "username": "myuser"
  }'

# Get access token (alternative method)
curl -X POST "http://localhost:8000/api/v1/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&username=user@example.com&password=secure123&scope=read write upload youtube"
```

### Core Endpoints

#### 🔐 Authentication (OAuth 2.0)
- `POST /oauth/register` - Register new user
- `POST /oauth/token` - Get access tokens
- `GET /oauth/userinfo` - Get user profile
- `PUT /oauth/profile` - Update user profile
- `POST /oauth/change-password` - Change password
- `POST /oauth/logout` - User logout

#### 📁 File Upload (Requires Authentication)
- `POST /upload/video` - Upload video file
- `POST /upload/transcript-text` - Submit transcript text
- `POST /upload/transcript-file` - Upload transcript file
- `GET /upload/{upload_id}` - Get upload info

#### 🎬 Job Management (Requires Authentication)
- `POST /jobs/create` - Create YouTube Short job
- `GET /jobs/{job_id}` - Get job details
- `GET /jobs/{job_id}/status` - Get job status
- `GET /jobs` - List jobs (paginated)

#### 📺 YouTube Operations (Requires Authentication)
- `GET /youtube/voices` - List supported TTS voices
- `GET /youtube/download/{job_id}` - Download processed video
- `GET /youtube/info` - Get service capabilities

#### 🏥 Health & Info
- `GET /health` - Health check
- `GET /` - API information

### Request Examples

#### Create a YouTube Short (Authenticated)
```bash
# Get your access token first, then:
curl -X POST "http://localhost:8000/api/v1/jobs/create" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "title": "My Awesome Short",
    "description": "Created with AI",
    "voice": "alloy",
    "tags": ["ai", "shorts", "automation"],
    "video_file_id": "uuid-of-uploaded-video",
    "transcript_content": "Hello world! This is my AI-generated voiceover."
  }'
```

## 🔧 Configuration

### Environment Variables

The startup script automatically creates `.env.dev` from `env.template.dev`. Key variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` |
| `SECRET_KEY` | JWT secret key | Required |
| `OPENAI_API_KEY` | OpenAI API key for TTS | Required |
| `YOUTUBE_CLIENT_ID` | YouTube API client ID | Required |
| `YOUTUBE_CLIENT_SECRET` | YouTube API client secret | Required |
| `YOUTUBE_REFRESH_TOKEN` | YouTube API refresh token | Required |
| `MAX_FILE_SIZE_MB` | Maximum file upload size | `100` |
| `CORS_ORIGINS_STR` | Allowed CORS origins | `http://localhost:3000,http://localhost:8080` |

### OAuth 2.0 Scopes

| Scope | Description |
|-------|-------------|
| `read` | Read access to user data |
| `write` | Write access to user data |
| `upload` | Upload files and create content |
| `youtube` | Access to YouTube operations |
| `admin` | Administrative access (superusers only) |

## 🚢 Production Deployment

### Using Production Script
```bash
# Make script executable
chmod +x start-prod.sh

# Run production script
./start-prod.sh
```

### Render.com (Recommended)

1. **Fork this repository**
2. **Connect to Render** - Link your GitHub repository
3. **Set Environment Variables** in Render dashboard
4. **Deploy** - Push to main branch triggers deployment

## 🔄 Processing Pipeline

1. **Authentication**: User registers/logs in via OAuth 2.0
2. **File Upload**: User uploads video and provides transcript (authenticated)
3. **Job Creation**: System creates processing job in database
4. **Background Processing**:
   - Video processing and formatting (60s duration)
   - TTS audio generation from transcript
   - Audio-video combination
   - YouTube upload with metadata
5. **Completion**: Job marked complete with YouTube URL

## 🧪 Testing

Test the OAuth 2.0 system:
```bash
# Run the OAuth test script
python test_oauth.py
```

## 📊 API Access

### Interactive Documentation
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **Health Check**: `http://localhost:8000/api/v1/health`

### Authentication Flow
1. Register user → Get access token
2. Use token in `Authorization: Bearer TOKEN` header
3. Access protected endpoints with appropriate scopes

## 🔐 Security Features

- **OAuth 2.0 Compliance**: RFC 6749 standard implementation
- **JWT Tokens**: Secure access and refresh tokens
- **Scope-based Authorization**: Fine-grained permission control
- **File Validation**: Size limits, type checking, content validation
- **CORS Protection**: Configurable origins
- **Request Size Limits**: Prevents large payload attacks

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Create an issue in this repository
- Check the API documentation at `/docs`
- Review the health check endpoint `/api/v1/health`

## 🔮 Roadmap

- [ ] WebSocket support for real-time progress updates
- [ ] Multiple video format support
- [ ] Batch processing capabilities
- [ ] Advanced video editing features
- [ ] Integration with more TTS providers
- [ ] Video thumbnail generation
- [ ] Analytics and usage tracking

---

Built with ❤️ using FastAPI and Google ADK



while IFS= read -r line; do [[ $line =~ ^[[:space:]]*# ]] || [[ -z $line ]] || export "$line"; done < .env.prod