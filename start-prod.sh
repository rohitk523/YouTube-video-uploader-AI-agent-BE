#!/bin/bash

# YouTube Shorts Creator API Production Startup Script

echo "🚀 Starting YouTube Shorts Creator API (Production Mode)..."

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

# Create .env.prod if it doesn't exist
if [ ! -f ".env.prod" ]; then
    echo "⚙️ Creating .env.prod file from production template..."
    cp env.template.prod .env.prod
    echo "📝 Please edit .env.prod file with your production configuration!"
    echo "🔒 Production environment created with security optimizations"
    echo "⚡ Key production features:"
    echo "   - DEBUG=false for security"
    echo "   - LOG_LEVEL=INFO for performance"
    echo "   - Multiple workers for scalability"
    echo "   - Optimized timeouts and settings"
    echo "   - SSL/TLS configuration available"
    echo "   - Monitoring and error tracking support"
    echo ""
    echo "⚠️  IMPORTANT: Update .env.prod with:"
    echo "   - Strong SECRET_KEY (generate a random 32+ character string)"
    echo "   - Production database credentials"
    echo "   - Redis password for security"
    echo "   - Proper CORS origins"
    echo "   - API keys and tokens"
    echo ""
    exit 1
fi

# Validate critical production settings
echo "🔍 Validating production configuration..."

# Check if SECRET_KEY is set and not using default
if grep -q "SECRET_KEY=$" .env.prod || grep -q "SECRET_KEY=dev-secret" .env.prod; then
    echo "❌ SECURITY WARNING: SECRET_KEY is not set or using default value!"
    echo "   Please set a strong, random SECRET_KEY in .env.prod"
    exit 1
fi

# Check if DEBUG is properly set to false
if grep -q "DEBUG=true" .env.prod; then
    echo "❌ SECURITY WARNING: DEBUG is set to true in production!"
    echo "   Please set DEBUG=false in .env.prod"
    exit 1
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p uploads temp static logs

# Check if Docker services are running or local services
echo "🔍 Checking for services..."

# For production, we assume services are already configured
echo "⚡ Production Mode: Assuming services are properly configured"
echo "🐳 If using Docker, ensure services are running: docker-compose -f docker-compose.prod.yml up -d"

# Check if Redis is accessible
if ! redis-cli ping > /dev/null 2>&1; then
    echo "⚠️  Warning: Cannot connect to Redis. Please ensure Redis is running and accessible."
fi

# Check if PostgreSQL is accessible
if ! pg_isready > /dev/null 2>&1; then
    echo "⚠️  Warning: Cannot connect to PostgreSQL. Please ensure PostgreSQL is running and accessible."
fi

echo "✅ Production startup checks completed!"
echo "🌐 Starting FastAPI Production Server..."
echo "📖 API Documentation: http://localhost:8000/docs"
echo "🏥 Health Check: http://localhost:8000/api/v1/health"
echo "⚡ Production Mode: Optimized for performance and security"
echo "🔒 Security: Debug mode disabled, logging optimized"
echo ""

# Start the application with production settings
export ENVIRONMENT=production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --env-file .env.prod 