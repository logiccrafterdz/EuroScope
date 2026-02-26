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
        tuple (model, tokenizer) or (None, None) if loading fails.
    """
    global _onnx_model, _tokenizer
    
    if _onnx_model is None:
        try:
            from optimum.onnxruntime import ORTModelForSequenceClassification
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

            logger.info(f"Loading Quantized FinBERT ONNX model from {model_dir}...")
            _onnx_model = ORTModelForSequenceClassification.from_pretrained(
                model_dir, 
                file_name="model_quantized.onnx"
            )
            _tokenizer = AutoTokenizer.from_pretrained(model_dir)
            
        except ImportError:
            logger.error("optimum/onnxruntime not installed. Falling back.")
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
        # Tokenize and run inference
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        outputs = model(**inputs)
        
        # Process output (FinBERT labels: 0: neutral, 1: positive, 2: negative)
        import torch
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
        
        conf, label_idx = torch.max(probs, dim=-1)
        conf = conf.item()
        label_idx = label_idx.item()
        
        # Mapping from FinBERT config.json:
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
            "provider": "onnx_quantized"
        }
        
    except Exception as e:
        logger.error(f"ONNX inference error: {e}")
        return {"sentiment": "neutral", "score": 0.0, "provider": "error"}
