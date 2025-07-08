# BetterSaved Bot - Docker Deployment Guide

## Prerequisites
- Ubuntu server with SSH access
- Docker installed
- Git installed
- `client_secret.json` file (Google API credentials)

## Step-by-Step Deployment

1. **SSH into your instance**
   ```bash
   ssh ubuntu@your-instance-ip
   ```

2. **Create data directory and set permissions**
   ```bash
   mkdir -p ~/bot-data
   chmod 755 ~/bot-data
   # Place your client_secret.json in this directory
   ```

3. **Clone the repository**
   ```bash
   git clone -b test https://github.com/yourusername/BetterSaved.git bettersaved-bot-test
   cd bettersaved-bot-test
   ```
   or
   ```bash
   git clone -b main https://github.com/yourusername/BetterSaved.git bettersaved-bot-main
   cd bettersaved-bot-main
   ```

4. **Build the Docker image**
   ```bash
   docker build -t bettersaved:test .
   ```
   or
   ```bash
   docker build -t bettersaved:main .
   ```

5. **Run the container**
   ```bash
   docker run -d \
     --restart unless-stopped \
     --name bettersaved-test \
     -v ~/bot-data:/app/data \
     -v ~/bot-data/client_secret.json:/app/client_secret.json \
     -e TELEGRAM_TOKEN="your-telegram-token" \
     -e DB_PATH="/app/data/bettersaved_test.db" \
     -e GOOGLE_DRIVE_FOLDER="BetterSaved Test" \
     -e ENVIRONMENT="production" \
     bettersaved:test
   ```
   or
   ```bash
   docker run -d \
     --restart unless-stopped \
     --name bettersaved-main \
     -v ~/bot-data:/app/data \
     -v ~/bot-data/client_secret.json:/app/client_secret.json \
     -e TELEGRAM_TOKEN="your-telegram-token" \
     -e DB_PATH="/app/data/bettersaved.db" \
     -e GOOGLE_DRIVE_FOLDER="BetterSaved" \
     -e ENVIRONMENT="production" \
     bettersaved:main
   ```

6. **Verify the container is running**
   ```bash
   docker ps
   ```

## Managing the Application

### View Logs
```bash
docker logs -f bettersaved-test
```
or
```bash
docker logs -f bettersaved-main
```

### Stop the Container
```bash
docker stop bettersaved-test
docker rm bettersaved-test
```

### Update the Application
```bash
# Stop and remove existing container
docker stop bettersaved-test
docker rm bettersaved-test

# Update code
cd ~/bettersaved-bot-test
git pull

# Rebuild and run
docker build -t bettersaved:test .
# Then run with the same docker run command as above
```

## File Locations
- Database: `~/bot-data/bettersaved_test.db`
- Google API credentials: `~/bot-data/client_secret.json`
- Application logs: Inside container at `/app/logs/`

## Troubleshooting

### Permission Issues
```bash
sudo chown -R ubuntu:ubuntu ~/bot-data
chmod 755 ~/bot-data
```

### Check Container Status
```bash
docker ps -a
docker logs bettersaved-test
```

### Access Container Shell
```bash
docker exec -it bettersaved-test /bin/bash
```

### View Database (SQLite)
```bash
sqlite3 ~/bot-data/bettersaved_test.db
.tables  # View tables
.quit    # Exit
```

## Environment Variables
| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `TELEGRAM_TOKEN` | Your Telegram bot token | Yes | - |
| `DB_PATH` | Path to SQLite database file | No | `/app/data/bot_database.db` |
| `GOOGLE_DRIVE_FOLDER_NAME` | Name for Google Drive folder | No | `BetterSaved` |
| `ENVIRONMENT` | Runtime environment (`production`/`development`) | No | `production` |

## Notes
- The database and credentials are stored in `~/bot-data/` on the host machine
- All data in `~/bot-data` persists between container restarts
- The container runs as a non-root user for security
- Logs can be found inside the container at `/app/logs/`

## Easy Brach Updates
```bash
cd ~/bettersaved-bot-test # Change to your test directory
git pull origin test # Pull the latest changes from the test branch
docker build -t bettersaved:test . # Build the Docker image
docker stop bettersaved-test # Stop the existing container
docker rm bettersaved-test # Remove the existing container
docker run -d \
  --name bettersaved-test \
  -v ~/bot-data:/app/data \
  -v ~/bot-data/client_secret.json:/app/client_secret.json \
  -e TELEGRAM_TOKEN="8137172493:AAEIjNgom3IGeHbB_DyFEd7I4jH_JNH1Lns" \
  -e DB_PATH="/app/data/bettersaved_test.db" \
  -e GOOGLE_DRIVE_FOLDER="BetterSaved_Test" \
  -e ENVIRONMENT="production" \
  bettersaved:test
```