from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import torch
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    PatchTSTForPrediction,
    TimeSeriesTransformerForPrediction,
)
from transformers.utils import logging as hf_logging


@dataclass(frozen=True)
class SentimentSignal:
    label: str
    confidence: float


@dataclass(frozen=True)
class ForecastSignal:
    mean: float
    std: float


@dataclass(frozen=True)
class AnomalySignal:
    score: float


class ModelRegistry:
    _instance: Optional["ModelRegistry"] = None

    def __init__(
        self,
        sentiment_model_id: str,
        trend_model_id: str,
        anomaly_model_id: str,
        device: str = "cpu",
        max_length: int = 256,
    ) -> None:
        hf_logging.set_verbosity_error()
        self._device = device
        self._max_length = max_length

        self._sent_tokenizer = AutoTokenizer.from_pretrained(sentiment_model_id)
        self._sent_model = AutoModelForSequenceClassification.from_pretrained(
            sentiment_model_id, ignore_mismatched_sizes=True
        ).to(device)

        self._trend_model = TimeSeriesTransformerForPrediction.from_pretrained(
            trend_model_id, ignore_mismatched_sizes=True
        ).to(device)

        self._anomaly_model = PatchTSTForPrediction.from_pretrained(
            anomaly_model_id, ignore_mismatched_sizes=True
        ).to(device)

    @classmethod
    def get(
        cls,
        sentiment_model_id: str,
        trend_model_id: str,
        anomaly_model_id: str,
        device: str = "cpu",
        max_length: int = 256,
    ) -> "ModelRegistry":
        if cls._instance is None:
            cls._instance = cls(
                sentiment_model_id=sentiment_model_id,
                trend_model_id=trend_model_id,
                anomaly_model_id=anomaly_model_id,
                device=device,
                max_length=max_length,
            )
        return cls._instance

    def score_sentiment(self, text: str) -> SentimentSignal:
        encoded = self._sent_tokenizer(
            text,
            max_length=self._max_length,
            truncation=True,
            return_tensors="pt",
        ).to(self._device)
        with torch.inference_mode():
            outputs = self._sent_model(**encoded)
            probs = torch.softmax(outputs.logits, dim=-1).squeeze().cpu().numpy()
        label_idx = int(np.argmax(probs))
        label = self._sent_model.config.id2label.get(label_idx, str(label_idx))
        confidence = float(np.max(probs))
        return SentimentSignal(label=label.lower(), confidence=confidence)

    def forecast_trend(self, series: Sequence[float]) -> ForecastSignal:
        values = np.asarray(series, dtype=np.float32)
        if values.size < 2:
            return ForecastSignal(mean=float(values[-1]), std=0.0)
        lags = getattr(self._trend_model.config, "lags_sequence", None) or []
        max_lag = max(lags) if lags else 0
        if values.size <= max_lag:
            mean = float(np.mean(values))
            std = float(np.std(values))
            return ForecastSignal(mean=mean, std=std)
        past_values = torch.tensor(values[None, :], device=self._device)
        context_len = past_values.shape[1]
        pred_len = int(self._trend_model.config.prediction_length)
        past_time_features = torch.linspace(0.0, 1.0, context_len, device=self._device)[None, :, None]
        future_time_features = torch.linspace(1.0, 1.0 + pred_len / max(context_len, 1), pred_len, device=self._device)[
            None, :, None
        ]
        past_observed_mask = torch.ones_like(past_values)
        with torch.inference_mode():
            outputs = self._trend_model.generate(
                past_values=past_values,
                past_time_features=past_time_features,
                past_observed_mask=past_observed_mask,
                future_time_features=future_time_features,
            )
            prediction = outputs.sequences.squeeze().cpu().numpy()
        return ForecastSignal(mean=float(np.mean(prediction)), std=float(np.std(prediction)))

    def score_anomaly(self, series: Sequence[float]) -> AnomalySignal:
        values = np.asarray(series, dtype=np.float32)
        if values.size < 2:
            return AnomalySignal(score=0.0)
        required_len = (
            getattr(self._anomaly_model.config, "context_length", None)
            or getattr(self._anomaly_model.config, "input_length", None)
            or getattr(self._anomaly_model.config, "sequence_length", None)
            or 0
        )
        if required_len and values.size < required_len:
            return AnomalySignal(score=0.0)
        past_values = torch.tensor(values[None, :, None], device=self._device)
        with torch.inference_mode():
            outputs = self._anomaly_model(past_values=past_values)
            prediction = outputs.prediction.squeeze().cpu().numpy()
        error = np.abs(prediction[-1] - values[-1])
        baseline = np.std(values) + 1e-6
        score = float(error / baseline)
        return AnomalySignal(score=score)
