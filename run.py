# run.py
import cv2
from flask import Response, redirect, url_for, session, flash, jsonify
from app import create_app
from config import Config
from anomaly_engine.detector import generate_live_feed

app = create_app(Config)


@app.context_processor
def inject_user():
    return dict(user=session.get("user"))


@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@app.route("/camera/snapshot/<int:cam_index>")
def camera_snapshot(cam_index):
    cap = cv2.VideoCapture(cam_index)
    success, frame = cap.read()
    cap.release()
    if not success:
        return "Camera error", 404
    ok, buffer = cv2.imencode(".jpg", frame)
    if not ok:
        return "Encode error", 500
    return Response(buffer.tobytes(), mimetype="image/jpeg")


@app.route("/reset_system")
def reset_system():
    if "user" not in session:
        return redirect(url_for("auth.login"))
    if session.get("role") != "admin":
        flash("Admin access required", "danger")
        return redirect(url_for("main.dashboard"))
    try:
        app.db.anomalies.delete_many({})
        flash("All anomaly records cleared!", "success")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        return f"Error: {str(e)}", 500


@app.route("/live_feed")
def live_feed():
    return Response(
        generate_live_feed(app.db, 0),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/live_feed_test")
def live_feed_test():
    result = {"cameras_available": [], "message": ""}
    for i in range(6):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            result["cameras_available"].append({
                "index": i,
                "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": cap.get(cv2.CAP_PROP_FPS),
            })
            cap.release()
    if not result["cameras_available"]:
        result["message"] = "No cameras detected."
    else:
        result["message"] = f"Found {len(result['cameras_available'])} camera(s)."
    return jsonify(result)


@app.route("/live")
def live_view():
    return redirect(url_for("live.live_dashboard"))


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, threaded=True)