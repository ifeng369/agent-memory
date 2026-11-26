"""构建阶段导出 ONNX 模型，运行时无需下载或 PyTorch。"""
import os
from pathlib import Path

from optimum.onnxruntime import ORTModelForFeatureExtraction
from transformers import AutoTokenizer

source = os.environ.get("MODEL_SOURCE", "BAAI/bge-small-zh-v1.5")
out = Path(os.environ.get("MODEL_OUT", "/app/models/agent-memory-onnx"))
out.mkdir(parents=True, exist_ok=True)

model = ORTModelForFeatureExtraction.from_pretrained(
    source, export=True, provider="CPUExecutionProvider"
)
model.save_pretrained(out)
AutoTokenizer.from_pretrained(source).save_pretrained(out)
print(f"exported ONNX model to {out}")
