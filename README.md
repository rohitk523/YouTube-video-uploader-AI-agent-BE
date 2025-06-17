# YouTube Shorts Creator API 🚀

A powerful FastAPI backend for creating YouTube Shorts with AI-generated voiceovers using Google ADK integration.

## ✨ Features

- **🎬 Video Processing**: Upload and process videos for YouTube Shorts format
- **🗣️ AI Voiceover**: Generate natural-sounding voiceovers with multiple voice options
- **📺 YouTube Integration**: Automatic upload to YouTube with metadata
- **📊 Progress Tracking**: Real-time job progress monitoring
- **🔄 Background Processing**: Asynchronous video processing pipeline
- **🗄️ Database Integration**: PostgreSQL with async SQLAlchemy
- **📁 File Management**: Secure file upload and storage system
- **🔒 Security**: CORS protection and file validation
- **📈 Health Monitoring**: Comprehensive health checks and monitoring

## 🏗️ Architecture

### Tech Stack
- **Framework**: FastAPI 0.104+
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
│   └── upload.py          # File upload model
├── schemas/               # Pydantic schemas
│   ├── job.py            # Job-related schemas
│   └── upload.py         # Upload schemas
├── api/                   # API endpoints
│   ├── upload.py         # File upload endpoints
│   ├── jobs.py           # Job management
│   └── youtube.py        # YouTube operations
├── services/              # Business logic
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
- PostgreSQL 14+
- Redis 6+
- FFmpeg (for video processing)

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd youtube-shorts-backend
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Setup environment variables**

Choose your environment setup:

**Development Environment:**
```bash
# Use development startup script (recommended for development)
./start-dev.sh

# Or manually:
cp env.template.dev .env.dev
# Edit .env.dev with your development configuration
```

**Production Environment:**
```bash
# Use production startup script (for production deployment)
./start-prod.sh

# Or manually:
cp env.template.prod .env.prod
# Edit .env.prod with your production configuration
```

**Legacy (Single Environment):**
```bash
cp env.template .env
# Edit .env with your configuration
```

5. **Setup database**
```bash
# Create PostgreSQL database
createdb youtube_shorts

# Run migrations (if using Alembic)
alembic upgrade head
```

6. **Start Redis**
```bash
redis-server
```

7. **Run the application**
```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

## 📋 API Documentation

### Base URL
```
http://localhost:8000/api/v1
```

### Core Endpoints

#### 📁 File Upload
- `POST /upload/video` - Upload video file
- `POST /upload/transcript-text` - Submit transcript text
- `POST /upload/transcript-file` - Upload transcript file
- `GET /upload/{upload_id}` - Get upload info
- `DELETE /upload/{upload_id}` - Delete upload

#### 🎬 Job Management
- `POST /jobs/create` - Create YouTube Short job
- `GET /jobs/{job_id}` - Get job details
- `GET /jobs/{job_id}/status` - Get job status
- `GET /jobs` - List jobs (paginated)
- `DELETE /jobs/{job_id}` - Delete job

#### 📺 YouTube Operations
- `GET /youtube/voices` - List supported TTS voices
- `GET /youtube/download/{job_id}` - Download processed video
- `GET /youtube/info` - Get service capabilities

#### 🏥 Health & Info
- `GET /health` - Health check
- `GET /info` - API information

### Request Examples

#### Create a YouTube Short
```bash
curl -X POST "http://localhost:8000/api/v1/jobs/create" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "My Awesome Short",
    "description": "Created with AI",
    "voice": "alloy",
    "tags": ["ai", "shorts", "automation"],
    "video_file_id": "uuid-of-uploaded-video",
    "transcript_content": "Hello world! This is my AI-generated voiceover."
  }'
```

#### Check Job Status
```bash
curl "http://localhost:8000/api/v1/jobs/{job_id}/status"
```

#### Get Supported Voices
```bash
curl "http://localhost:8000/api/v1/youtube/voices"
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` |
| `OPENAI_API_KEY` | OpenAI API key for TTS | Required |
| `YOUTUBE_CLIENT_ID` | YouTube API client ID | Required |
| `YOUTUBE_CLIENT_SECRET` | YouTube API client secret | Required |
| `YOUTUBE_REFRESH_TOKEN` | YouTube API refresh token | Required |
| `MAX_FILE_SIZE_MB` | Maximum file upload size | `100` |
| `UPLOAD_DIRECTORY` | File upload directory | `./uploads` |
| `SECRET_KEY` | Application secret key | Required |
| `CORS_ORIGINS` | Allowed CORS origins | `*` |

### Supported File Types

**Video Files**: `.mp4`, `.mov`, `.avi`, `.mkv`
**Transcript Files**: `.txt`, `.md`

### TTS Voices
- `alloy` (default)
- `echo`
- `fable` 
- `onyx`
- `nova`
- `shimmer`

## 🔄 Processing Pipeline

1. **File Upload**: User uploads video and provides transcript
2. **Job Creation**: System creates processing job in database
3. **Background Processing**:
   - Video processing and formatting (60s duration)
   - TTS audio generation from transcript
   - Audio-video combination
   - YouTube upload with metadata
4. **Completion**: Job marked complete with YouTube URL

## 🚢 Deployment

### Render.com (Recommended)

1. **Fork this repository**

2. **Connect to Render**
   - Link your GitHub repository
   - Render will detect `render.yaml`

3. **Set Environment Variables**
   - Add your API keys in Render dashboard
   - Database and Redis will be auto-provisioned

4. **Deploy**
   - Push to main branch triggers deployment
   - Health checks ensure proper startup

### Docker Deployment

```bash
# Build image
docker build -t youtube-shorts-api .

# Run with environment file
docker run -p 8000:8000 --env-file .env youtube-shorts-api
```

### Manual Deployment

```bash
# Install production dependencies
pip install gunicorn

# Run with Gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

## 🧪 Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test file
pytest tests/test_api.py
```

## 📊 Monitoring

### Health Checks
- `GET /api/v1/health` - Application health
- Database connectivity check
- Upload directory accessibility check

### Logging
- Structured logging with timestamps
- Request/response logging
- Error tracking with stack traces
- Performance metrics

## 🔐 Security

- **File Validation**: Size limits, type checking, content validation
- **CORS Protection**: Configurable origins
- **Request Size Limits**: Prevents large payload attacks
- **File Cleanup**: Automatic cleanup of old files
- **Error Handling**: Secure error messages

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