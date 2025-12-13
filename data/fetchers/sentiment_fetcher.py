"""
Sentiment Fetcher - Análisis de sentimiento con FinBERT
Integración: CryptoPanic (Prioridad) + NewsAPI (Backup 28 días)
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
import time

# FinBERT imports
try:
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    FINBERT_AVAILABLE = True
except (ImportError, OSError, Exception) as e:
    # ImportError: Paquetes no instalados
    # OSError: PyTorch DLL loading error en Windows
    # Exception: Cualquier otro error de inicialización
    FINBERT_AVAILABLE = False
    logging.warning(f"FinBERT no disponible: {type(e).__name__}: {e}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SentimentFetcher:
    
    def __init__(self, 
                 news_api_key: Optional[str] = None,
                 cryptopanic_key: Optional[str] = None,
                 min_confidence: float = 0.90):
        
        self.news_api_key = news_api_key
        self.cryptopanic_key = cryptopanic_key
        self.min_confidence = min_confidence
        
        self.finbert_model = None
        self.finbert_tokenizer = None
        
        if FINBERT_AVAILABLE:
            self._load_finbert()
    
    def _load_finbert(self):
        try:
            logger.info("Cargando modelo FinBERT...")
            model_name = "ProsusAI/finbert"
            self.finbert_tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.finbert_model = AutoModelForSequenceClassification.from_pretrained(model_name)
            self.finbert_model.eval()
            logger.info("✓ FinBERT cargado")
        except Exception as e:
            logger.error(f"Error cargando FinBERT: {e}")

    def fetch_from_cryptopanic(self, currencies: str = 'ETH') -> pd.DataFrame:
        """Descarga noticias desde CryptoPanic"""
        if not self.cryptopanic_key:
            return pd.DataFrame()
            
        logger.info("Descargando noticias de CryptoPanic...")
        url = "https://cryptopanic.com/api/v1/posts/"
        all_posts = []
        
        params = {
            'auth_token': self.cryptopanic_key,
            'currencies': currencies,
            'kind': 'news',
            'filter': 'important'  # Solo noticias importantes
        }
        
        try:
            # Descargar varias páginas para tener historial
            for _ in range(5):
                response = requests.get(url, params=params, timeout=10)
                data = response.json()
                
                if 'results' in data:
                    all_posts.extend(data['results'])
                
                if data.get('next'):
                    url = data['next']
                    params = {} # params ya están en la url 'next'
                    time.sleep(1) # Respetar rate limit
                else:
                    break
            
            df = pd.DataFrame([{
                'timestamp': pd.to_datetime(p['published_at']),
                'title': p.get('title', ''),
                'source': p.get('domain', p.get('source', {}).get('domain', 'unknown'))
            } for p in all_posts if p.get('title')])
            
            # Convertir timezone a naive
            if not df.empty and df['timestamp'].dt.tz is not None:
                df['timestamp'] = df['timestamp'].dt.tz_localize(None)
                
            logger.info(f"✓ {len(df)} noticias de CryptoPanic")
            return df
            
        except Exception as e:
            logger.error(f"Error CryptoPanic: {e}")
            return pd.DataFrame()

    def fetch_from_newsapi(self, keywords: List[str], days: int = 28) -> pd.DataFrame:
        """Descarga NewsAPI (Limitado a 28 días para plan gratis)"""
        if not self.news_api_key:
            return pd.DataFrame()

        # FIX: Forzar máximo 28 días para evitar error 426
        safe_days = min(days, 28)
        logger.info(f"Descargando NewsAPI (últimos {safe_days} días)...")
        
        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                'q': ' OR '.join(keywords),
                'from': (datetime.now() - timedelta(days=safe_days)).strftime('%Y-%m-%d'),
                'language': 'en',
                'sortBy': 'publishedAt',
                'apiKey': self.news_api_key,
                'pageSize': 100
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            # Si aún así falla, retornar vacío sin romper
            if response.status_code == 426:
                logger.warning("NewsAPI: Upgrade Required. Saltando NewsAPI.")
                return pd.DataFrame()
                
            response.raise_for_status()
            data = response.json()
            
            df = pd.DataFrame([{
                'timestamp': pd.to_datetime(a['publishedAt']),
                'title': a['title'],
                'source': a['source']['name']
            } for a in data.get('articles', [])])
            
            if not df.empty and df['timestamp'].dt.tz is not None:
                df['timestamp'] = df['timestamp'].dt.tz_localize(None)
                
            logger.info(f"✓ {len(df)} noticias de NewsAPI")
            return df
            
        except Exception as e:
            logger.error(f"Error NewsAPI: {e}")
            return pd.DataFrame()

    def analyze_sentiment(self, text: str) -> Dict[str, float]:
        """Calcula score con FinBERT"""
        if not self.finbert_model:
            # Simulación simple si FinBERT falla
            return {'score': 0.0, 'confidence': 0.0}
            
        try:
            inputs = self.finbert_tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
            with torch.no_grad():
                outputs = self.finbert_model(**inputs)
                probs = torch.nn.functional.softmax(outputs.logits, dim=-1).numpy()[0]
            
            # [Pos, Neg, Neu] -> Score = Pos - Neg
            score = probs[0] - probs[1]
            return {'score': float(score), 'confidence': float(probs.max())}
        except:
            return {'score': 0.0, 'confidence': 0.0}

    def get_sentiment_dataset(self, days: int = 28) -> pd.DataFrame:
        """Pipeline principal"""
        
        # 1. Descargar de ambas fuentes
        df_crypto = self.fetch_from_cryptopanic()
        df_news = self.fetch_from_newsapi(['ethereum', 'ETH'], days)
        
        # 2. Combinar
        df = pd.concat([df_crypto, df_news]).drop_duplicates(subset=['title'])
        if df.empty:
            logger.warning("No se encontraron noticias. Usando dataset vacío.")
            return pd.DataFrame(columns=['FinBERT_Score'])
            
        # 3. Analizar con FinBERT
        logger.info(f"Analizando {len(df)} noticias con FinBERT...")
        scores = []
        for txt in df['title']:
            scores.append(self.analyze_sentiment(txt))
            
        df['sentiment_score'] = [s['score'] for s in scores]
        df['confidence'] = [s['confidence'] for s in scores]
        
        # 4. Filtrar y Agregar
        df = df[df['confidence'] >= self.min_confidence].copy()
        
        if df.empty:
             return pd.DataFrame(columns=['FinBERT_Score'])

        df.set_index('timestamp', inplace=True)
        agg = df.resample('4h').agg({'sentiment_score': 'mean'})  # Fix: 'H' -> 'h'
        agg.rename(columns={'sentiment_score': 'FinBERT_Score'}, inplace=True)
        agg.fillna(0, inplace=True)
        
        return agg