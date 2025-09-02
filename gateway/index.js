const express = require('express');
const multer = require('multer');
const Redis = require('ioredis');
const { v4: uuidv4 } = require('uuid');
const path = require('path');

const app = express();
const port = 3000;

// Redis configuration
const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
const MOOD_TAGGER_QUEUE = process.env.MOOD_TAGGER_QUEUE || 'mood-analysis-queue';
const THUMBNAIL_QUEUE = process.env.THUMBNAIL_QUEUE || 'thumbnail-queue';

// Redis clients
const redis = new Redis(REDIS_URL);
const subscriber = new Redis(REDIS_URL);

// In-memory storage for pending requests
const pendingRequests = new Map();

// Request timeout (60 seconds)
const REQUEST_TIMEOUT = 60000;

// Use multer for in-memory file storage
const upload = multer({ storage: multer.memoryStorage() });

// Serve the static frontend
app.use(express.static(path.join(__dirname, 'web')));

// Health check
app.get('/health', async (req, res) => {
    try {
        await redis.ping();
        res.json({ 
            status: 'ok', 
            service: 'gateway',
            redis: 'connected',
            pendingRequests: pendingRequests.size
        });
    } catch (error) {
        res.status(503).json({ 
            status: 'error', 
            service: 'gateway',
            redis: 'disconnected',
            error: error.message
        });
    }
});

// Subscribe to result channels
async function setupSubscriptions() {
    try {
        await subscriber.subscribe('mood-results', 'thumbnail-results');
        console.log('Subscribed to result channels');
        
        subscriber.on('message', (channel, message) => {
            try {
                const result = JSON.parse(message);
                const { requestId, success, data, error } = result;
                
                console.log(`Received result from ${channel} for request ${requestId}`);
                
                if (pendingRequests.has(requestId)) {
                    const request = pendingRequests.get(requestId);
                    
                    if (success) {
                        if (channel === 'mood-results') {
                            request.moodData = data;
                        } else if (channel === 'thumbnail-results') {
                            request.thumbnailData = data;
                        }
                    } else {
                        request.errors = request.errors || [];
                        request.errors.push({ service: channel.replace('-results', ''), error });
                    }
                    
                    // Check if we have both results or timeout
                    checkRequestComplete(requestId);
                }
            } catch (error) {
                console.error('Error processing message:', error);
            }
        });
    } catch (error) {
        console.error('Failed to setup subscriptions:', error);
    }
}

function checkRequestComplete(requestId) {
    const request = pendingRequests.get(requestId);
    if (!request) return;
    
    const hasErrors = request.errors && request.errors.length > 0;
    const hasMoodData = request.moodData !== undefined;
    const hasThumbnailData = request.thumbnailData !== undefined;
    
    // Complete if we have both results or if timeout occurred
    if ((hasMoodData && hasThumbnailData) || hasErrors || request.timedOut) {
        clearTimeout(request.timeout);
        
        const response = {
            ...request.moodData,
            ...request.thumbnailData
        };
        
        if (hasErrors) {
            response.warnings = request.errors;
        }
        
        request.res.json(response);
        pendingRequests.delete(requestId);
        
        console.log(`Request ${requestId} completed - mood: ${hasMoodData}, thumbnail: ${hasThumbnailData}, errors: ${hasErrors}`);
    }
}

// Queue job with retry mechanism
async function queueJob(queueName, jobData, retries = 3) {
    for (let attempt = 1; attempt <= retries; attempt++) {
        try {
            await redis.lpush(queueName, JSON.stringify(jobData));
            console.log(`Queued job ${jobData.requestId} to ${queueName} (attempt ${attempt})`);
            return true;
        } catch (error) {
            console.error(`Failed to queue job (attempt ${attempt}):`, error);
            if (attempt === retries) {
                throw error;
            }
            // Wait before retry
            await new Promise(resolve => setTimeout(resolve, 1000 * attempt));
        }
    }
    return false;
}

// Main analyze endpoint
app.post('/analyze', upload.single('image'), async (req, res) => {
    if (!req.file) {
        return res.status(400).json({ error: 'No image file uploaded.' });
    }
    
    const requestId = uuidv4();
    console.log(`Processing image analysis request ${requestId}: ${req.file.originalname}`);

    try {
        const fileBuffer = req.file.buffer;
        const fileName = req.file.originalname;
        
        // Convert buffer to base64 for queue transmission
        const imageBase64 = fileBuffer.toString('base64');
        
        // Store request context
        const requestContext = {
            res,
            moodData: undefined,
            thumbnailData: undefined,
            errors: [],
            timedOut: false
        };
        
        // Set timeout
        requestContext.timeout = setTimeout(() => {
            console.log(`Request ${requestId} timed out`);
            requestContext.timedOut = true;
            
            if (pendingRequests.has(requestId)) {
                const partial = {
                    ...requestContext.moodData,
                    ...requestContext.thumbnailData,
                    warning: 'Request timed out - some services may be unavailable'
                };
                
                res.status(202).json(partial);
                pendingRequests.delete(requestId);
            }
        }, REQUEST_TIMEOUT);
        
        pendingRequests.set(requestId, requestContext);
        
        // Queue jobs to both services
        const moodJob = {
            requestId,
            fileName,
            imageData: imageBase64,
            timestamp: Date.now()
        };
        
        const thumbnailJob = {
            requestId,
            fileName,
            imageData: imageBase64,
            timestamp: Date.now()
        };
        
        // Queue both jobs concurrently
        await Promise.allSettled([
            queueJob(MOOD_TAGGER_QUEUE, moodJob),
            queueJob(THUMBNAIL_QUEUE, thumbnailJob)
        ]);
        
        console.log(`Queued analysis jobs for request ${requestId}`);
        
    } catch (error) {
        console.error("Error in gateway:", error);
        
        // Clean up pending request
        if (pendingRequests.has(requestId)) {
            clearTimeout(pendingRequests.get(requestId).timeout);
            pendingRequests.delete(requestId);
        }
        
        res.status(500).json({ error: 'Failed to process image analysis request.' });
    }
});

// Graceful shutdown
process.on('SIGTERM', async () => {
    console.log('Shutting down gracefully...');
    
    // Complete pending requests with timeout
    for (const [requestId, request] of pendingRequests.entries()) {
        clearTimeout(request.timeout);
        request.res.status(503).json({ error: 'Service shutting down' });
    }
    pendingRequests.clear();
    
    await redis.quit();
    await subscriber.quit();
    process.exit(0);
});

app.listen(port, async () => {
    console.log(`Gateway listening on port ${port}`);
    console.log(`Redis URL: ${REDIS_URL}`);
    console.log(`Mood Queue: ${MOOD_TAGGER_QUEUE}`);
    console.log(`Thumbnail Queue: ${THUMBNAIL_QUEUE}`);
    
    await setupSubscriptions();
    console.log('Gateway ready with queue integration');
});