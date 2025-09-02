package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/disintegration/imaging"
	"github.com/gin-gonic/gin"
	"github.com/go-redis/redis/v8"
)

// Configuration
var (
	redisURL     = getEnv("REDIS_URL", "redis://localhost:6379")
	queueName    = getEnv("QUEUE_NAME", "thumbnail-queue")
	resultChannel = "thumbnail-results"
	workerID     = fmt.Sprintf("thumb-worker-%d", os.Getpid())
)

// Job represents a thumbnail job
type Job struct {
	RequestID string `json:"requestId"`
	FileName  string `json:"fileName"`
	ImageData string `json:"imageData"`
	Timestamp int64  `json:"timestamp"`
}

// Result represents the job result
type Result struct {
	RequestID   string      `json:"requestId"`
	Success     bool        `json:"success"`
	Data        interface{} `json:"data,omitempty"`
	Error       string      `json:"error,omitempty"`
	Worker      string      `json:"worker"`
	ProcessedAt string      `json:"processedAt"`
}

// ThumbnailData represents the thumbnail response data
type ThumbnailData struct {
	Thumbnail     string                 `json:"thumbnail"`
	OriginalSize  map[string]interface{} `json:"original_size"`
	ThumbnailSize map[string]interface{} `json:"thumbnail_size"`
}

var (
	rdb    *redis.Client
	ctx    = context.Background()
	router *gin.Engine
)

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func initRedis() error {
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return fmt.Errorf("failed to parse Redis URL: %v", err)
	}

	rdb = redis.NewClient(opt)

	// Test connection
	_, err = rdb.Ping(ctx).Result()
	if err != nil {
		return fmt.Errorf("failed to connect to Redis: %v", err)
	}

	log.Printf("[%s] Connected to Redis: %s", workerID, redisURL)
	return nil
}

func processImage(job Job) Result {
	log.Printf("[%s] Processing image: %s (request: %s)", workerID, job.FileName, job.RequestID)

	// Decode base64 image
	imageBytes, err := base64.StdEncoding.DecodeString(job.ImageData)
	if err != nil {
		return Result{
			RequestID:   job.RequestID,
			Success:     false,
			Error:       fmt.Sprintf("Failed to decode image: %v", err),
			Worker:      workerID,
			ProcessedAt: time.Now().Format(time.RFC3339),
		}
	}

	// Decode image
	img, err := imaging.Decode(bytes.NewReader(imageBytes))
	if err != nil {
		return Result{
			RequestID:   job.RequestID,
			Success:     false,
			Error:       fmt.Sprintf("Failed to decode image: %v", err),
			Worker:      workerID,
			ProcessedAt: time.Now().Format(time.RFC3339),
		}
	}

	originalWidth := img.Bounds().Dx()
	originalHeight := img.Bounds().Dy()

	// Resize to 200px width, preserving aspect ratio
	thumbnail := imaging.Resize(img, 200, 0, imaging.Lanczos)
	thumbnailWidth := thumbnail.Bounds().Dx()
	thumbnailHeight := thumbnail.Bounds().Dy()

	// Encode as PNG
	buf := new(bytes.Buffer)
	if err := imaging.Encode(buf, thumbnail, imaging.PNG); err != nil {
		return Result{
			RequestID:   job.RequestID,
			Success:     false,
			Error:       fmt.Sprintf("Failed to encode thumbnail: %v", err),
			Worker:      workerID,
			ProcessedAt: time.Now().Format(time.RFC3339),
		}
	}

	// Base64 encode
	b64String := base64.StdEncoding.EncodeToString(buf.Bytes())

	data := ThumbnailData{
		Thumbnail: b64String,
		OriginalSize: map[string]interface{}{
			"width":  originalWidth,
			"height": originalHeight,
		},
		ThumbnailSize: map[string]interface{}{
			"width":  thumbnailWidth,
			"height": thumbnailHeight,
		},
	}

	log.Printf("[%s] Successfully processed %s (size: %d bytes)", workerID, job.FileName, buf.Len())

	return Result{
		RequestID:   job.RequestID,
		Success:     true,
		Data:        data,
		Worker:      workerID,
		ProcessedAt: time.Now().Format(time.RFC3339),
	}
}

func queueWorker() {
	log.Printf("[%s] Starting queue worker for %s", workerID, queueName)

	for {
		// Block and wait for jobs (30 second timeout)
		queueResult := rdb.BRPop(ctx, 30*time.Second, queueName)
		if queueResult.Err() != nil {
			if queueResult.Err() == redis.Nil {
				// Timeout, continue polling
				continue
			}
			log.Printf("[%s] Queue error: %v", workerID, queueResult.Err())
			time.Sleep(5 * time.Second)
			continue
		}

		jobData := queueResult.Val()[1] // [1] is the job data, [0] is the queue name

		var job Job
		if err := json.Unmarshal([]byte(jobData), &job); err != nil {
			log.Printf("[%s] Invalid job data: %v", workerID, err)
			continue
		}

		log.Printf("[%s] Received job: %s", workerID, job.RequestID)

		// Process the job
		jobResult := processImage(job)

		// Publish result
		resultJSON, err := json.Marshal(jobResult)
		if err != nil {
			log.Printf("[%s] Failed to marshal result: %v", workerID, err)
			continue
		}

		if err := rdb.Publish(ctx, resultChannel, resultJSON).Err(); err != nil {
			log.Printf("[%s] Failed to publish result: %v", workerID, err)
		} else {
			log.Printf("[%s] Published result for %s", workerID, jobResult.RequestID)
		}
	}
}

func setupRoutes() {
	gin.SetMode(gin.ReleaseMode)
	router = gin.Default()

	// Health check endpoints
	router.GET("/", healthCheck)
	router.GET("/health", healthCheck)

	// Legacy endpoint for direct calls (fallback)
	router.POST("/resize", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"message": "This service now processes requests via message queue",
			"worker":  workerID,
			"queue":   queueName,
		})
	})
}

func healthCheck(c *gin.Context) {
	// Check Redis connection
	_, err := rdb.Ping(ctx).Result()
	redisStatus := "connected"
	if err != nil {
		redisStatus = "disconnected"
	}

	status := "healthy"
	if redisStatus != "connected" {
		status = "unhealthy"
	}

	c.JSON(http.StatusOK, gin.H{
		"status":  status,
		"service": "thumb-svc",
		"worker":  workerID,
		"redis":   redisStatus,
		"queue":   queueName,
	})
}

func main() {
	// Initialize Redis
	if err := initRedis(); err != nil {
		log.Fatal(err)
	}

	// Setup HTTP routes
	setupRoutes()

	// Start queue worker in background
	go queueWorker()

	// Start HTTP server in background
	server := &http.Server{
		Addr:    ":5002",
		Handler: router,
	}

	go func() {
		log.Printf("Thumbnail service starting on :5002")
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatal("Failed to start server:", err)
		}
	}()

	log.Printf("[%s] Queue worker started", workerID)

	// Wait for interrupt signal to gracefully shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Printf("[%s] Shutting down gracefully...", workerID)

	// Shutdown HTTP server
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := server.Shutdown(ctx); err != nil {
		log.Printf("Server forced to shutdown: %v", err)
	}

	// Close Redis connection
	if err := rdb.Close(); err != nil {
		log.Printf("Error closing Redis: %v", err)
	}

	log.Printf("[%s] Shutdown complete", workerID)
}