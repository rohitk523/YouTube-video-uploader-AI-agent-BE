#!/bin/bash

# YouTube Shorts Creator API Development Startup Script

echo "🚀 Starting YouTube Shorts Creator API (Development Mode)..."

# Check if conda is installed
if ! command -v conda &> /dev/null; then
    echo "❌ Conda is not installed. Please install Anaconda or Miniconda first."
    echo "   Visit: https://docs.conda.io/en/latest/miniconda.html"
    exit 1
fi

# Check if virtual environment exists
if ! conda env list | grep -q "youtube-shorts-api"; then
    echo "📦 Creating conda environment with Python 3.11..."
    conda create -n youtube-shorts-api python=3.11 -y
fi

# Activate conda environment
echo "🔧 Activating conda environment..."
source $(conda info --base)/etc/profile.d/conda.sh
conda activate youtube-shorts-api

# Install dependencies
echo "📋 Installing dependencies..."
pip install -r requirements.txt

# Create .env.dev if it doesn't exist
if [ ! -f ".env.dev" ]; then
    echo "⚙️ Creating .env.dev file from development template..."
    cp env.template.dev .env.dev
    echo "📝 Please edit .env.dev file with your development configuration!"
    echo "💡 Development environment created with debug settings enabled"
    echo "🔧 Key development features:"
    echo "   - DEBUG=true for detailed error messages"
    echo "   - LOG_LEVEL=DEBUG for verbose logging"
    echo "   - Single worker for easier debugging"
    echo "   - Reduced timeouts for faster iteration"
    echo ""
    echo "📝 Don't forget to update the .env.dev file with proper API keys!"
    echo "🐳 You can also start services with Docker: docker-compose up -d"
    exit 1
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p uploads temp static logs

# Check if Docker services are running or local services
echo "🔍 Checking for services..."

# Check if we should use Docker or local services
echo "Choose your development setup:"
echo "1) Run everything locally (Redis + PostgreSQL + FastAPI)"
echo "2) Use Docker for infrastructure only (Redis + PostgreSQL)"
echo "3) Use Docker for everything (Redis + PostgreSQL + FastAPI Backend)"
read -p "Enter your choice (1/2/3): " choice

if [ "$choice" = "2" ]; then
    echo "🐳 Starting infrastructure services with Docker (Redis + PostgreSQL)..."
    docker-compose -f docker-compose.yml up -d postgres redis
    echo "⏳ Waiting for services to be ready..."
    sleep 10
elif [ "$choice" = "3" ]; then
    echo "🐳 Starting all services with Docker (including FastAPI backend)..."
    docker-compose -f docker-compose.yml up -d
    echo "✅ All services started! Backend is running at http://localhost:8000"
    echo "📖 API Documentation: http://localhost:8000/docs"
    echo "🏥 Health Check: http://localhost:8000/api/v1/health"
    echo "🔍 View logs: docker-compose logs -f backend"
    exit 0
else
    # Check if Redis is running locally
    if ! pgrep -x "redis-server" > /dev/null; then
        echo "❌ Redis is not running. Please start Redis first:"
        echo "   brew services start redis  # macOS with Homebrew"
        echo "   sudo systemctl start redis # Linux"
        echo "   redis-server               # Manual start"
        echo "   Or use Docker: docker-compose up -d"
        exit 1
    fi

    # Check if PostgreSQL is running locally
    if ! pg_isready > /dev/null 2>&1; then
        echo "❌ PostgreSQL is not running. Please start PostgreSQL first:"
        echo "   brew services start postgresql # macOS with Homebrew"
        echo "   sudo systemctl start postgresql # Linux"
        echo "   Or use Docker: docker-compose up -d"
        exit 1
    fi
fi

echo "✅ All dependencies checked!"
echo "🌐 Starting FastAPI Development Server..."
echo "📖 API Documentation: http://localhost:8000/docs"
echo "🏥 Health Check: http://localhost:8000/api/v1/health"
echo "🔧 Development Mode: Hot reload enabled"
echo "🐛 Debug Mode: Enabled for detailed error messages"
echo ""

# Start the application with development settings
export ENVIRONMENT=development
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --env-file .env.dev 