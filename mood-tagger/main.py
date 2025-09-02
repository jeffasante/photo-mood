import io
import json
import base64
import asyncio
import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from transformers import AutoProcessor, AutoModelForImageTextToText
from PIL import Image
import redis.asyncio as redis
import os
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
QUEUE_NAME = os.getenv('QUEUE_NAME', 'mood-analysis-queue')
RESULT_CHANNEL = 'mood-results'
WORKER_ID = f"mood-worker-{os.getpid()}"

# Initialize FastAPI app
app = FastAPI(title="Mood Tagger API", version="1.0.0")

# Global variables
model = None
processor = None
redis_client = None
worker_task = None

def load_model():
    """Load the lightweight SmolVLM model"""
    global model, processor
    try:
        logger.info("Loading SmolVLM-256M-Instruct model...")
        
        model_name = "HuggingFaceTB/SmolVLM-256M-Instruct"
        processor = AutoProcessor.from_pretrained(model_name)
        model = AutoModelForImageTextToText.from_pretrained(model_name)
        
        logger.info("SmolVLM model loaded successfully!")
        return True
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        return False


def extract_mood_tags(caption):
    """
    Extract mood-related tags from the generated caption.
    """
    mood_mappings = {
        'sunny': ['bright', 'cheerful', 'warm'],
        'bright': ['happy', 'vibrant', 'energetic'],
        'dark': ['moody', 'mysterious', 'dramatic'],
        'colorful': ['joyful', 'lively', 'playful'],
        'peaceful': ['calm', 'serene', 'tranquil'],
        'beautiful': ['elegant', 'lovely', 'aesthetic'],
        'green': ['natural', 'fresh', 'organic'],
        'blue': ['cool', 'calm', 'peaceful'],
        'red': ['passionate', 'bold', 'energetic'],
        'yellow': ['cheerful', 'sunny', 'bright'],
        'orange': ['warm', 'vibrant', 'enthusiastic'],
        'purple': ['mystical', 'luxurious', 'dreamy'],
        'black': ['moody', 'minimalist', 'bold'],
        'white': ['clean', 'peaceful', 'pure'],
        'water': ['refreshing', 'fluid', 'clean'],
        'flower': ['delicate', 'beautiful', 'natural'],
        'sunset': ['romantic', 'warm', 'golden'],
        'sunrise': ['hopeful', 'gentle', 'fresh'],
        'rain': ['melancholic', 'calm', 'moody'],
        'snow': ['quiet', 'cold', 'magical'],
        'storm': ['chaotic', 'powerful', 'intense'],
        'city': ['urban', 'dynamic', 'modern'],
        'mountain': ['majestic', 'strong', 'elevated'],
        'beach': ['relaxing', 'tropical', 'carefree'],
        'forest': ['natural', 'mysterious', 'earthy'],
        'desert': ['vast', 'dry', 'isolated'],
        'sky': ['open', 'free', 'airy'],
        'smile': ['happy', 'joyful', 'positive'],
        'laugh': ['cheerful', 'carefree', 'uplifting'],
        'cry': ['emotional', 'sad', 'touching'],
        'child': ['innocent', 'joyful', 'pure'],
        'baby': ['cute', 'gentle', 'tender'],
        'dog': ['friendly', 'loyal', 'playful'],
        'cat': ['elegant', 'mysterious', 'independent'],
        'bird': ['free', 'graceful', 'light'],
        'food': ['appetizing', 'delicious', 'satisfying'],
        'drink': ['refreshing', 'inviting', 'cool'],
        'old': ['vintage', 'nostalgic', 'classic'],
        'new': ['modern', 'fresh', 'contemporary'],
        'vintage': ['nostalgic', 'retro', 'classic'],
        'abstract': ['artistic', 'imaginative', 'creative'],
        'minimal': ['clean', 'simple', 'focused'],
        'crowd': ['busy', 'chaotic', 'lively'],
        'alone': ['solitary', 'quiet', 'introspective'],
        'dance': ['energetic', 'expressive', 'joyful'],
        'music': ['rhythmic', 'soulful', 'emotional'],
        'light': ['hopeful', 'bright', 'glowing'],
        'shadow': ['dark', 'mysterious', 'introspective'],
        'fire': ['intense', 'hot', 'powerful'],
        'night': ['quiet', 'romantic', 'mysterious']
    }

    caption_lower = caption.lower()
    tags = set()

    for keyword, associated_moods in mood_mappings.items():
        if keyword in caption_lower:
            tags.update(associated_moods[:2])  # Add up to 2 moods per keyword

    if not tags:
        if any(word in caption_lower for word in ['beautiful', 'nice', 'good', 'lovely']):
            tags.update(['pleasant', 'positive'])
        elif any(word in caption_lower for word in ['sitting', 'standing', 'lying']):
            tags.update(['calm', 'relaxed'])
        else:
            tags.update(['neutral', 'balanced'])

    return list(tags)[:6]



async def process_image(job_data):
    """Process a single image analysis job"""
    try:
        request_id = job_data['requestId']
        file_name = job_data['fileName']
        image_data = job_data['imageData']
        
        logger.info(f"[{WORKER_ID}] Processing image: {file_name} (request: {request_id})")
        
        # Decode base64 image
        image_bytes = base64.b64decode(image_data)
        pil_image = Image.open(io.BytesIO(image_bytes))
        
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')
        
        # Generate caption using SmolVLM
        messages = [
            {
                "role": "user", 
                "content": [
                    {"type": "image"},
                    {"type": "text", "text": "Describe this image and its mood in detail."}
                ]
            }
        ]
        

        # generated_ids = model.generate(
        #     **inputs,
        #     max_new_tokens=50,  # Reduced from 100
        #     do_sample=False,  # Faster than sampling
        #     num_beams=1,  # Faster than beam search
        #     temperature=None,  # Not used when do_sample=False
        #     pad_token_id=processor.tokenizer.eos_token_id,
        # )

        prompt = processor.apply_chat_template(messages, add_generation_prompt=True)
        inputs = processor(text=prompt, images=pil_image, return_tensors="pt")
        # generated_ids = model.generate(**inputs, max_new_tokens=100, do_sample=True, temperature=0.7)
        generated_ids = model.generate(
            **inputs,
            max_new_tokens=50,  # Reduced from 100
            do_sample=False,  # Faster than sampling
            num_beams=1,  # Faster than beam search
            temperature=None,  # Not used when do_sample=False
            pad_token_id=processor.tokenizer.eos_token_id,
        )
        generated_tokens = generated_ids[0][inputs['input_ids'].shape[1]:]
        caption = processor.decode(generated_tokens, skip_special_tokens=True)
        
        # Extract mood tags
        tags = extract_mood_tags(caption)
        if not tags:
            tags = ['artistic', 'visual', 'expressive']
        
        result = {
            'requestId': request_id,
            'success': True,
            'data': {
                'tags': tags,
                'caption': caption
            },
            'worker': WORKER_ID,
            'processedAt': datetime.now().isoformat()
        }
        
        logger.info(f"[{WORKER_ID}] Successfully processed {file_name}: {len(tags)} tags generated")
        return result
        
    except Exception as e:
        logger.error(f"[{WORKER_ID}] Error processing image: {str(e)}")
        return {
            'requestId': job_data.get('requestId', 'unknown'),
            'success': False,
            'error': str(e),
            'worker': WORKER_ID,
            'processedAt': datetime.now().isoformat()
        }

async def queue_worker():
    """Main queue worker loop"""
    global redis_client
    
    logger.info(f"[{WORKER_ID}] Starting queue worker for {QUEUE_NAME}")
    
    while True:
        try:
            # Block and wait for jobs (30 second timeout)
            result = await redis_client.brpop(QUEUE_NAME, timeout=30)
            
            if result:
                queue_name, job_data = result
                
                try:
                    job = json.loads(job_data)
                    logger.info(f"[{WORKER_ID}] Received job: {job['requestId']}")
                    
                    # Process the job
                    result = await process_image(job)
                    
                    # Publish result
                    await redis_client.publish(RESULT_CHANNEL, json.dumps(result))
                    logger.info(f"[{WORKER_ID}] Published result for {result['requestId']}")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"[{WORKER_ID}] Invalid job data: {e}")
                except Exception as e:
                    logger.error(f"[{WORKER_ID}] Error processing job: {e}")
            
        except asyncio.CancelledError:
            logger.info(f"[{WORKER_ID}] Worker cancelled")
            break
        except Exception as e:
            logger.error(f"[{WORKER_ID}] Worker error: {e}")
            await asyncio.sleep(5)  # Wait before retrying

@app.on_event("startup")
async def startup_event():
    """Initialize model and start worker on startup"""
    global redis_client, worker_task
    
    # Load ML model
    success = load_model()
    if not success:
        logger.error("Failed to load model on startup")
        return
    
    # Connect to Redis
    try:
        redis_client = redis.from_url(REDIS_URL)
        await redis_client.ping()
        logger.info(f"Connected to Redis: {REDIS_URL}")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return
    
    # Start queue worker
    worker_task = asyncio.create_task(queue_worker())
    logger.info(f"[{WORKER_ID}] Queue worker started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global redis_client, worker_task
    
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    
    if redis_client:
        await redis_client.close()
    
    logger.info(f"[{WORKER_ID}] Shutdown complete")

@app.get("/")
def read_root():
    """Health check endpoint"""
    return {"status": "ok", "service": "mood-tagger", "worker": WORKER_ID}

@app.get("/health")
async def health_check():
    """Detailed health check"""
    try:
        if redis_client:
            await redis_client.ping()
            redis_status = "connected"
        else:
            redis_status = "disconnected"
    except:
        redis_status = "error"
    
    return {
        "status": "healthy" if model is not None and redis_status == "connected" else "unhealthy",
        "service": "mood-tagger",
        "worker": WORKER_ID,
        "model_loaded": model is not None,
        "redis": redis_status,
        "queue": QUEUE_NAME
    }

# Legacy endpoint for direct calls (fallback)
@app.post("/tags")
async def create_tags_direct():
    """Direct endpoint - returns message about queue-based processing"""
    return JSONResponse(
        status_code=200,
        content={
            "message": "This service now processes requests via message queue",
            "worker": WORKER_ID,
            "queue": QUEUE_NAME
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)