"""
Optimized Sentiment Engine for EUR/USD.

Uses FinBERT (ProsusAI) optimized with ONNX Runtime and int8 quantization
to minimize memory usage and maximize inference speed on CPU.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger("euroscope.data.sentiment")

# Global instances for lazy loading
_onnx_model = None
_tokenizer = None

def get_sentiment_engine():
    """
    Lazy load the ONNX-optimized FinBERT engine.
    
    Returns:
        tuple (session, tokenizer) or (None, None) if loading fails.
    """
    global _onnx_model, _tokenizer
    
    if _onnx_model is None:
        try:
            import onnxruntime as ort
            import numpy as np
            from transformers import AutoTokenizer
            
            # Paths relative to this file
            base_dir = os.path.dirname(os.path.abspath(__file__))
            model_dir = os.path.join(base_dir, "models", "finbert_onnx_quantized")
            
            if not os.path.exists(model_dir):
                logger.warning(f"Optimized model not found at {model_dir}")
                return None, None
            
            onnx_path = os.path.join(model_dir, "model_quantized.onnx")
            zip_path = onnx_path + ".zip"
            
            # Auto-unzip if model is missing but zip exists
            if not os.path.exists(onnx_path) and os.path.exists(zip_path):
                logger.info(f"Unzipping model from {zip_path}...")
                import zipfile
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(model_dir)
            
            if not os.path.exists(onnx_path):
                logger.error(f"ONNX model file missing at {onnx_path}")
                return None, None

            logger.info(f"Loading Quantized FinBERT ONNX model from {onnx_path}...")
            _onnx_model = ort.InferenceSession(onnx_path)
            _tokenizer = AutoTokenizer.from_pretrained(model_dir)
            
        except ImportError:
            logger.error("onnxruntime not installed. Falling back.")
            return None, None
        except Exception as e:
            logger.error(f"Failed to load FinBERT ONNX: {e}")
            return None, None
            
    return _onnx_model, _tokenizer


def analyze_sentiment_onnx(text: str) -> dict:
    """
    Analyze sentiment using ONNX Runtime.
    
    Returns:
        {"sentiment": "bullish|bearish|neutral", "score": float}
    """
    model, tokenizer = get_sentiment_engine()
    
    if model is None:
        return {"sentiment": "neutral", "score": 0.0, "provider": "none"}
        
    try:
        import numpy as np
        
        # Tokenize (returns numpy arrays directly if specified)
        inputs = tokenizer(text, return_tensors="np", truncation=True, max_length=512)
        
        # Run inference using session
        # Inputs should match what the model expects (usually input_ids, attention_mask)
        ort_inputs = {k: v for k, v in inputs.items()}
        outputs = model.run(None, ort_inputs)
        
        # outputs[0] is typically the logits array [1, num_labels]
        logits = outputs[0]
        
        # Softmax using numpy
        e_x = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
        probs = e_x / e_x.sum(axis=-1, keepdims=True)
        
        # Get label with highest probability
        label_idx = np.argmax(probs, axis=-1)[0]
        conf = float(probs[0, label_idx])
        
        # Mapping from FinBERT config.json (Confirmed!):
        # 0: positive, 1: negative, 2: neutral
        if label_idx == 0: # Positive
            sentiment = "bullish"
            score = conf
        elif label_idx == 1: # Negative
            sentiment = "bearish"
            score = -conf
        else: # Neutral
            sentiment = "neutral"
            score = 0.0
            
        return {
            "sentiment": sentiment,
            "score": round(score, 3),
            "provider": "onnx_quantized_numpy"
        }
        
    except Exception as e:
        logger.error(f"ONNX inference error: {e}")
        return {"sentiment": "neutral", "score": 0.0, "provider": "error"}
