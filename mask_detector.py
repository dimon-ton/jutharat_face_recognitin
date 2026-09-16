"""Direct, whole-image masked-face detection with a local YOLOv5 model."""
import math
from pathlib import Path

MASK_LABELS = {"cloth", "respirator", "surgical", "valved"}


class MaskDetector:
    def __init__(self, weights, repo, confidence=0.5, size=640, device="cpu"):
        if not math.isfinite(confidence) or not 0 < confidence <= 1:
            raise ValueError("Mask confidence must be greater than 0 and at most 1.")
        if size <= 0:
            raise ValueError("Mask image size must be positive.")
        weights, repo = Path(weights).resolve(), Path(repo).resolve()
        if not weights.is_file() or not (repo / "hubconf.py").is_file():
            raise ValueError("Provide TFM weights and a local YOLOv5 checkout containing hubconf.py. See README.md.")
        import torch
        from PIL import Image, ImageOps
        self.model = torch.hub.load(str(repo), "custom", path=str(weights),
                                     source="local", device=device)
        names = self.model.names
        labels = set(names.values() if isinstance(names, dict) else names)
        if labels != MASK_LABELS | {"unmasked"}:
            raise ValueError(f"Expected TFM masked-face classes, found {labels}.")
        self.model.conf = confidence
        self.confidence, self.size = confidence, size
        self.Image, self.ImageOps = Image, ImageOps

    def detections(self, path):
        with self.Image.open(path) as source:
            image = self.ImageOps.exif_transpose(source).convert("RGB")
            predictions = self.model(image, size=self.size).xyxy[0].cpu().tolist()
        masks = []
        for x1, y1, x2, y2, confidence, class_id in predictions:
            label = self.model.names[int(class_id)]
            if not math.isfinite(confidence):
                raise ValueError("Invalid mask confidence")
            if label in MASK_LABELS and confidence >= self.confidence:
                masks.append(dict(label=label, confidence=confidence, box=[x1, y1, x2, y2]))
        return masks
