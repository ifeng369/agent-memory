"""
向量嵌入服务 - 仅 ONNX Runtime CPU 推理
"""
from pathlib import Path
from typing import List, Optional
import logging

import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer

from ..config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """向量嵌入服务"""

    def __init__(self):
        self.session = None
        self.input_names = []
        self.tokenizer = None
        self.is_initialized = False

    def initialize(self):
        """加载构建阶段已导出的本地 ONNX 模型（不联网、不依赖 PyTorch）"""
        if self.is_initialized:
            return

        model_dir = Path(settings.MODEL_NAME)
        logger.info(f"Loading ONNX embedding model: {model_dir}")
        self.session = ort.InferenceSession(
            str(model_dir / "model.onnx"),
            providers=["CPUExecutionProvider"],
        )
        self.input_names = [i.name for i in self.session.get_inputs()]
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)

        self._warmup()
        self.is_initialized = True
        logger.info("Embedding service initialized with ONNX Runtime")

    def _warmup(self):
        try:
            self.encode(["warmup text"])
        except Exception as e:
            logger.warning(f"Warmup failed: {e}")

    def encode(self, texts: List[str], batch_size: Optional[int] = None) -> np.ndarray:
        """批量编码文本为向量（mean pooling + L2 归一化）"""
        if not self.is_initialized:
            self.initialize()

        if isinstance(texts, str):
            texts = [texts]

        try:
            inputs = self.tokenizer(
                texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="np",
            )
            feed = {k: inputs[k] for k in self.input_names if k in inputs}
            outputs = self.session.run(None, feed)[0]
            mask = inputs["attention_mask"][..., None].astype(np.float32)
            embeddings = (outputs * mask).sum(axis=1) / mask.sum(axis=1)
            embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
            return embeddings.astype(np.float32)
        except Exception as e:
            logger.error(f"Encoding failed: {e}")
            raise

    def encode_single(self, text: str) -> List[float]:
        """编码单个文本"""
        return self.encode([text])[0].tolist()

    def get_dimension(self) -> int:
        return settings.MODEL_DIMENSION


# 全局嵌入服务实例
embedding_service = EmbeddingService()
