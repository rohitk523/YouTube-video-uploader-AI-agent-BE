# Docker Setup Guide

This guide explains how to run the YouTube Shorts Creator API with Docker services.

## Quick Start

1. **Start with the setup script:**
   ```bash
   ./start.sh
   ```
   When prompted, choose "y" to use Docker services.

2. **Or manually start services:**
   ```bash
   # Start only core services (PostgreSQL + Redis)
   docker-compose up -d
   
   # Start with management tools (pgAdmin + Redis Commander)
   docker-compose --profile tools up -d
   ```

## Environment Configuration

### For Docker Services

Update your `.env` file with Docker-specific settings:

```bash
# Uncomment and configure these for Docker
POSTGRES_DB=youtube_shorts
POSTGRES_USER=user
POSTGRES_PASSWORD=your_secure_password
POSTGRES_PORT=5432

REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password

# Update connection URLs to use Docker services
DATABASE_URL=postgresql://user:your_secure_password@localhost:5432/youtube_shorts
REDIS_URL=redis://:your_redis_password@localhost:6379

# Optional: Management tools
PGADMIN_EMAIL=admin@admin.com
PGADMIN_PASSWORD=admin_password
PGADMIN_PORT=8080
REDIS_COMMANDER_PORT=8081
```

## Available Services

### Core Services
- **PostgreSQL**: Database server (port 5432)
- **Redis**: Cache and background jobs (port 6379)

### Management Tools (Optional)
Start with: `docker-compose --profile tools up -d`

- **pgAdmin**: PostgreSQL management interface
  - URL: http://localhost:8080
  - Login: See PGADMIN_EMAIL/PGADMIN_PASSWORD in .env

- **Redis Commander**: Redis management interface
  - URL: http://localhost:8081

## Docker Commands

```bash
# Start core services
docker-compose up -d

# Start with management tools
docker-compose --profile tools up -d

# Stop all services
docker-compose down

# Stop and remove volumes (⚠️ deletes all data)
docker-compose down -v

# View logs
docker-compose logs
docker-compose logs postgres
docker-compose logs redis

# Check service status
docker-compose ps

# Restart a specific service
docker-compose restart postgres
```

## Data Persistence

Data is persisted in Docker volumes:
- `postgres_data`: PostgreSQL database files
- `redis_data`: Redis data files
- `pgadmin_data`: pgAdmin configuration

## Network Configuration

All services run on the `youtube-shorts-network` bridge network, allowing them to communicate with each other using service names.

## Health Checks

Both PostgreSQL and Redis include health checks to ensure services are ready before starting dependent services.

## Troubleshooting

### Services won't start
```bash
# Check logs
docker-compose logs

# Restart services
docker-compose restart

# Recreate services
docker-compose down && docker-compose up -d
```

### Port conflicts
Update port mappings in `.env` file:
```bash
POSTGRES_PORT=5433  # Instead of 5432
REDIS_PORT=6380     # Instead of 6379
```

### Database connection issues
Ensure your `DATABASE_URL` in `.env` matches your Docker configuration:
```bash
DATABASE_URL=postgresql://user:password@localhost:5432/youtube_shorts
```

### Performance issues
- Increase Docker Desktop memory allocation (Preferences > Resources)
- Consider using local services for development if Docker is too slow 