"""Small, dependency-tolerant analysis layer for the Presentation Coach API.

Video-to-landmark extraction is intentionally optional: Vercel can import the
API even when the native computer-vision stack is not installed.  The model
artifacts are still discovered and reported so deployment problems are visible
instead of being mistaken for a successful analysis.
"""

from pathlib import Path
import pickle
import tempfile
import logging
import json
import zipfile

import numpy as np


logger = logging.getLogger(__name__)


BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_NAMES = {
    "posture": "model_posture_lstm.keras",
    "hands": "model_hands_lstm.keras",
    "sway": "model_sway_lstm.keras",
    "movement": "model_movement_lstm.keras",
}


def model_status():
    return {
        name: {
            "available": (BASE_DIR / filename).is_file(),
            "file": filename,
        }
        for name, filename in MODEL_NAMES.items()
    }


def analyze_video(video):
    """Return a truthful result for a received upload.

    Landmark extraction needs OpenCV/MediaPipe and is kept behind an explicit
    capability check. This makes the endpoint useful in local development and
    gives the frontend an actionable response instead of a fake score.
    """
    try:
        from .feature_extractor import extract_features
    except ImportError:
        try:
            from feature_extractor import extract_features
        except ImportError as exc:
            return {
                "status": "processing_unavailable",
                "message": "Modul ekstraksi fitur belum bisa dimuat.",
                "missing_dependency": str(exc),
                "models": model_status(),
            }, 503

    try:
        with tempfile.NamedTemporaryFile(suffix=".webm") as uploaded:
            video.save(uploaded.name)
            features = extract_features(uploaded.name)
            return predict(features)
    except ImportError as exc:
        return {
            "status": "processing_unavailable",
            "message": (
                "Video diterima, tetapi dependency computer vision belum "
                "terpasang di deployment ini."
            ),
            "next_step": "Install requirements.txt lalu deploy ulang.",
            "missing_dependency": str(exc),
            "models": model_status(),
        }, 503
    except (OSError, ValueError) as exc:
        return {"status": "invalid_video", "message": str(exc)}, 422
    except Exception as exc:
        logger.exception("Unexpected video analysis failure")
        return {
            "status": "analysis_error",
            "message": "Terjadi error saat menjalankan model AI.",
            "error_type": type(exc).__name__,
            "error_detail": str(exc),
        }, 500


def _decode_label(name, index):
    encoder_path = BASE_DIR / f"encoder_{name}_lstm.pkl"
    try:
        # These artifacts were written with joblib, not plain pickle.
        import joblib
        encoder = joblib.load(encoder_path)
        return str(encoder.inverse_transform([index])[0])
    except (FileNotFoundError, OSError, ValueError, AttributeError, IndexError, ImportError):
        return str(index)


def predict(features):
    try:
        import tensorflow as tf
    except ImportError as exc:
        return {
            "status": "processing_unavailable",
            "message": "Fitur berhasil diekstrak, tetapi TensorFlow belum terpasang.",
            "next_step": "Install requirements.txt lalu deploy ulang.",
            "missing_dependency": str(exc),
            "models": model_status(),
        }, 503

    predictions = {}
    confidences = []
    for name, filename in MODEL_NAMES.items():
        model = _load_model_compatible(tf, BASE_DIR / filename)
        probabilities = model.predict(features, verbose=0)[0]
        index = int(np.argmax(probabilities))
        confidence = float(probabilities[index])
        predictions[name] = {
            "label": _decode_label(name, index),
            "confidence": round(confidence, 4),
        }
        confidences.append(confidence)

    return {
        "status": "success",
        "message": "Video berhasil dianalisis.",
        "score": round(sum(confidences) / len(confidences) * 100),
        "predictions": predictions,
        "models": model_status(),
    }, 200


def _load_model_compatible(tf, model_path):
    """Load Keras 3 archives with the older tf.keras bundled on Intel macOS."""
    try:
        return tf.keras.models.load_model(model_path, compile=False)
    except Exception as first_error:
        if "batch_shape" not in str(first_error) and "optional" not in str(first_error):
            raise

        # TensorFlow 2.13 calls this field batch_input_shape and does not know
        # InputLayer.optional. Keep the original artifact untouched.
        with zipfile.ZipFile(model_path) as source, tempfile.NamedTemporaryFile(
                suffix=".keras") as converted:
            with zipfile.ZipFile(converted.name, "w") as target:
                for item in source.infolist():
                    payload = source.read(item.filename)
                    if item.filename == "config.json":
                        config = json.loads(payload)

                        def normalize_dtype(value):
                            if isinstance(value, dict):
                                for key, child in list(value.items()):
                                    if key == "dtype" and isinstance(child, dict):
                                        value[key] = "float32"
                                    else:
                                        normalize_dtype(child)
                            elif isinstance(value, list):
                                for child in value:
                                    normalize_dtype(child)

                        normalize_dtype(config)
                        for layer in config.get("config", {}).get("layers", []):
                            if layer.get("class_name") == "InputLayer":
                                layer_config = layer.get("config", {})
                                if "batch_shape" in layer_config:
                                    layer_config["batch_input_shape"] = layer_config.pop("batch_shape")
                                layer_config.pop("optional", None)
                        payload = json.dumps(config).encode("utf-8")
                    target.writestr(item, payload)
            try:
                return tf.keras.models.load_model(converted.name, compile=False)
            except Exception:
                return _load_weights_into_compatible_architecture(tf, model_path)


def _load_weights_into_compatible_architecture(tf, model_path):
    """Fallback for TensorFlow 2.13: rebuild the known model topology."""
    import h5py

    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(90, 14)),
        tf.keras.layers.LSTM(64, return_sequences=True, dropout=0.2, recurrent_dropout=0.1),
        tf.keras.layers.BatchNormalization(),
        tf.keras.layers.LSTM(32, dropout=0.2),
        tf.keras.layers.BatchNormalization(),
        tf.keras.layers.Dense(32, activation="relu"),
        tf.keras.layers.Dropout(0.3),
        tf.keras.layers.Dense(2, activation="softmax"),
    ])
    with zipfile.ZipFile(model_path) as source, tempfile.NamedTemporaryFile(suffix=".h5") as weights:
        weights.write(source.read("model.weights.h5"))
        weights.flush()
        with h5py.File(weights.name, "r") as archive:
            for layer in model.layers:
                group_name = f"layers/{layer.name}/vars"
                if group_name in archive and len(archive[group_name]) > 0:
                    group = archive[group_name]
                elif f"layers/{layer.name}/cell/vars" in archive:
                    group = archive[f"layers/{layer.name}/cell/vars"]
                else:
                    continue
                layer.set_weights([group[str(index)][()] for index in range(len(group))])
    return model
