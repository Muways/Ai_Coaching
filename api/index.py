from flask import Flask, jsonify, request

try:
    from .analyzer import analyze_video, model_status
except ImportError:  # Vercel loads a function module with api/ on sys.path.
    from analyzer import analyze_video, model_status

app = Flask(__name__)


@app.get("/")
def health():
    return jsonify(status="ok", service="AI Presentation Coach API", models=model_status())


@app.post("/api/analyze")
def analyze():
    video = request.files.get("video")
    if video is None or not video.filename:
        return jsonify(error="File video belum dikirim."), 400

    result, status = analyze_video(video)
    result["filename"] = video.filename
    return jsonify(result), status
