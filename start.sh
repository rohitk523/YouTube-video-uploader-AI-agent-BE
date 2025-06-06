#!/bin/bash

# YouTube Shorts Creator API Startup Script

echo "🚀 Starting YouTube Shorts Creator API..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📋 Installing dependencies..."
pip install -r requirements.txt

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️ Creating .env file from template..."
    cp env.template .env
    echo "📝 Please edit .env file with your configuration before running the app!"
    exit 1
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p uploads temp static logs

# Check if Redis is running
if ! pgrep -x "redis-server" > /dev/null; then
    echo "❌ Redis is not running. Please start Redis first:"
    echo "   brew services start redis  # macOS with Homebrew"
    echo "   sudo systemctl start redis # Linux"
    echo "   redis-server               # Manual start"
    exit 1
fi

# Check if PostgreSQL is running
if ! pg_isready > /dev/null 2>&1; then
    echo "❌ PostgreSQL is not running. Please start PostgreSQL first:"
    echo "   brew services start postgresql # macOS with Homebrew"
    echo "   sudo systemctl start postgresql # Linux"
    exit 1
fi

echo "✅ All dependencies checked!"
echo "🌐 Starting FastAPI server..."
echo "📖 API Documentation: http://localhost:8000/docs"
echo "🏥 Health Check: http://localhost:8000/api/v1/health"
echo ""

# Start the application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 