Start all services

docker-compose down
docker-compose up --build

Open your browser to: http://localhost:8080

 

# Check the mood-tagger logs
docker-compose logs mood-tagger

# Check if Redis is working
docker-compose logs redis

# Check gateway logs
docker-compose logs gateway

# Update the main.py to use AutoModelForImageTextToText instead
docker-compose stop mood-tagger
# Edit main.py to change the import and model loading
docker-compose up --build mood-tagger



Since you're only updating the gateway service, you can rebuild and restart just that container. Here are a few ways to do it:

## Method 1: Rebuild only the gateway service
```bash
docker-compose up --build gateway
```

## Method 2: Stop and rebuild just gateway
```bash
# Stop only the gateway container
docker-compose stop gateway

# Rebuild and start just the gateway
docker-compose up --build gateway
```

## Method 3: Force recreate gateway container
```bash
# Recreate just the gateway service
docker-compose up -d --force-recreate gateway
```

## Method 4: Build then run (if you want more control)
```bash
# Build just the gateway image
docker-compose build gateway

# Start/restart just the gateway
docker-compose up -d gateway
```

## To see logs for just the gateway:
```bash
docker-compose logs -f gateway
```

The other services (mood-tagger and thumb-svc) will keep running normally since they're already working. The gateway will reconnect to them automatically since they're all on the same Docker network (`svcnet`).

**Recommended approach:**
```bash
docker-compose up --build gateway
```
