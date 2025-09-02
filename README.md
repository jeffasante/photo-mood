# Photo Mood

AI-powered image analysis application that extracts mood tags and generates thumbnails using microservices architecture.

## Overview

Photo Mood analyzes uploaded images to determine their emotional essence through computer vision. The application generates mood-based tags from image content and creates optimized thumbnails, all powered by a distributed microservices backend.

## Architecture

The application consists of three independent microservices:

- **Gateway Service** (Node.js + Express) - API orchestration and frontend serving
- **Mood Tagger Service** (Python + FastAPI) - AI-powered mood analysis using SmolVLM-256M
- **Thumbnail Service** (Go + Gin) - High-performance image resizing

## Features

- Drag and drop image upload interface
- AI-powered mood tag extraction from image content
- Automatic thumbnail generation (200px width, optimized)
- Real-time image analysis with visual feedback
- Responsive web interface with clean design
- Microservices architecture for scalability

## Technology Stack

### Frontend
- Vanilla JavaScript
- CSS3 with Manrope typography
- HTML5 drag-and-drop API

### Backend Services
- **Gateway**: Node.js, Express, Multer, Axios
- **AI Analysis**: Python, FastAPI, SmolVLM-256M-Instruct, Transformers
- **Image Processing**: Go, Gin framework, Imaging library

### Infrastructure
- Docker & Docker Compose
- GitHub Actions CI/CD
- Container orchestration with custom networking

## Quick Start

### Prerequisites
- Docker Desktop installed
- Git installed
- 8GB+ RAM recommended (for AI model)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/jeffasante/photo-mood
cd photo-mood
```

2. Start all services:
```bash
docker-compose up --build
```

3. Open your browser to:
```
http://localhost:8080
```

The application will automatically download the AI model on first run (approximately 513MB).

## Development

### Running Individual Services

For development, you can run services independently:

#### Gateway Service
```bash
cd gateway
npm install
npm start
# Runs on http://localhost:3000
```

#### Mood Tagger Service
```bash
cd mood-tagger
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 5001
# Runs on http://localhost:5001
```

#### Thumbnail Service
```bash
cd thumb-svc
go mod tidy
go run main.go
# Runs on http://localhost:5002
```

## API Endpoints

### Gateway Service (Port 8080)
- `GET /` - Frontend interface
- `POST /analyze` - Image analysis endpoint
- `GET /health` - Service health check

### Mood Tagger Service (Port 5001)
- `POST /tags` - Generate mood tags from image
- `GET /health` - Service health check

### Thumbnail Service (Port 5002)
- `POST /resize` - Generate thumbnail from image
- `GET /health` - Service health check

## Configuration

### Environment Variables

The gateway service accepts these environment variables:

```bash
MOOD_TAGGER_URL=http://mood-tagger:5001
THUMB_SVC_URL=http://thumb-svc:5002
```

### File Limitations

- Maximum file size: 10MB
- Supported formats: JPG, PNG, GIF
- Processing time: 5-15 seconds (CPU-based AI inference)

## Performance Notes

- AI model runs on CPU for broader compatibility
- First-time model loading takes approximately 30 seconds
- Subsequent requests process in 5-15 seconds
- Thumbnail generation is near-instantaneous (sub-second)

## Deployment

### Local Development
```bash
docker-compose up --build
```

### Production Deployment
1. Update environment variables in docker-compose.yml
2. Configure reverse proxy (nginx recommended)
3. Set up SSL certificates
4. Scale services as needed:
```bash
docker-compose up --scale mood-tagger=3 --scale thumb-svc=2
```

## CI/CD Pipeline

The project includes GitHub Actions workflow for:
- Automated testing
- Docker image building
- Container registry publishing
- Security scanning with Trivy


## Credits

Built by Jeff Asante  
Portfolio: https://jeffasante.github.io/

Powered by microservices architecture with modern AI and cloud-native technologies.