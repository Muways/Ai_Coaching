import os

from flask import Flask, jsonify, request, send_file, send_from_directory

from api.analyzer import analyze_video, model_status

app = Flask(__name__)
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/api/analyze", methods=["POST"])
def analyze():
    video = request.files.get("video")

    if video is None:
        return jsonify(error="File video belum dikirim."), 400

    result, status = analyze_video(video)
    result["filename"] = video.filename
    return jsonify(result), status


@app.route("/", methods=["GET"])
def health():
    built_index = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.isfile(built_index):
        return send_from_directory(FRONTEND_DIST, "index.html")
    return send_file(os.path.join(os.path.dirname(__file__), "index.html"))


@app.route("/assets/<path:filename>", methods=["GET"])
def frontend_assets(filename):
    return send_from_directory(os.path.join(FRONTEND_DIST, "assets"), filename)


@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify(status="ok", service="AI Presentation Coach API", models=model_status())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=True)
