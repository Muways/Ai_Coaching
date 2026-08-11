"""Convert a presentation video into the 90x14 LSTM input tensor.

The training CSV stores aggregate versions of these signals. At inference time
the models consume the per-frame signals below, normalized in the same screen-
relative coordinate system.
"""

from pathlib import Path

import numpy as np


TARGET_FRAMES = 90
FEATURE_COUNT = 14


def _distance(a, b):
    return float(np.linalg.norm(np.asarray(a) - np.asarray(b)))


def _point(landmarks, index):
    if landmarks is None:
        return None
    p = landmarks[index]
    return np.array([p.x, p.y], dtype=np.float32)


def extract_features(video_path):
    """Return a float32 array shaped (90, 14) from a video file."""
    import cv2
    import mediapipe as mp

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError("Video tidak dapat dibuka atau formatnya tidak didukung.")

    pose_api = mp.solutions.pose
    hands_api = mp.solutions.hands
    rows = []
    previous = None

    with pose_api.Pose(static_image_mode=False, model_complexity=1,
                       min_detection_confidence=0.5,
                       min_tracking_confidence=0.5) as pose, \
            hands_api.Hands(static_image_mode=False, max_num_hands=2,
                            min_detection_confidence=0.5,
                            min_tracking_confidence=0.5) as hands:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pose_result = pose.process(rgb)
            hands_result = hands.process(rgb)
            pose_landmarks = (pose_result.pose_landmarks.landmark
                              if pose_result.pose_landmarks else None)

            left_shoulder = _point(pose_landmarks, 11)
            right_shoulder = _point(pose_landmarks, 12)
            left_hip = _point(pose_landmarks, 23)
            right_hip = _point(pose_landmarks, 24)
            nose = _point(pose_landmarks, 0)
            left_wrist = _point(pose_landmarks, 15)
            right_wrist = _point(pose_landmarks, 16)

            if left_shoulder is None or right_shoulder is None or left_hip is None or right_hip is None:
                if previous is not None:
                    rows.append(previous)
                continue

            shoulder_mid = (left_shoulder + right_shoulder) / 2
            hip_mid = (left_hip + right_hip) / 2
            torso_height = max(_distance(shoulder_mid, hip_mid), 1e-3)
            shoulder_width = max(_distance(left_shoulder, right_shoulder), 1e-3)
            wrist_left = left_wrist if left_wrist is not None else shoulder_mid
            wrist_right = right_wrist if right_wrist is not None else shoulder_mid

            left_visible = float(left_wrist is not None)
            right_visible = float(right_wrist is not None)
            if hands_result.multi_hand_landmarks:
                # MediaPipe's handedness is camera-relative; use the x-position
                # to keep left/right stable for mirrored webcam footage.
                hand_points = [h.landmark[0] for h in hands_result.multi_hand_landmarks]
                hand_x = sorted((p.x, p.y) for p in hand_points)
                if len(hand_x) >= 1:
                    wrist_left = np.array(hand_x[0], dtype=np.float32)
                    left_visible = 1.0
                if len(hand_x) >= 2:
                    wrist_right = np.array(hand_x[-1], dtype=np.float32)
                    right_visible = 1.0

            shoulder_tilt = (right_shoulder[1] - left_shoulder[1]) / shoulder_width
            body_lean = (shoulder_mid[0] - hip_mid[0]) / torso_height
            head_height = ((shoulder_mid[1] - nose[1]) / torso_height
                           if nose is not None else 0.0)
            left_hand_height = (shoulder_mid[1] - wrist_left[1]) / torso_height
            right_hand_height = (shoulder_mid[1] - wrist_right[1]) / torso_height
            hands_spread = _distance(wrist_left, wrist_right) / shoulder_width

            if previous is None:
                left_movement = right_movement = sway_x = sway_y = movement = 0.0
            else:
                left_movement = _distance(wrist_left, previous["left_wrist"])
                right_movement = _distance(wrist_right, previous["right_wrist"])
                sway_x = shoulder_mid[0] - previous["shoulder_mid"][0]
                sway_y = shoulder_mid[1] - previous["shoulder_mid"][1]
                movement = _distance(shoulder_mid, previous["shoulder_mid"])

            row = np.array([
                shoulder_tilt, body_lean, head_height, torso_height,
                left_hand_height, right_hand_height, hands_spread,
                left_movement, right_movement, left_visible, right_visible,
                sway_x, sway_y, movement,
            ], dtype=np.float32)
            rows.append(row)
            previous = {
                "left_wrist": wrist_left,
                "right_wrist": wrist_right,
                "shoulder_mid": shoulder_mid,
            }

    capture.release()
    if not rows:
        raise ValueError("Tidak ada pose tubuh yang terdeteksi di video.")

    data = np.asarray(rows, dtype=np.float32)
    if len(data) >= TARGET_FRAMES:
        indices = np.linspace(0, len(data) - 1, TARGET_FRAMES).astype(int)
        data = data[indices]
    else:
        padding = np.repeat(data[-1][None, :], TARGET_FRAMES - len(data), axis=0)
        data = np.concatenate([data, padding], axis=0)
    return data.reshape(1, TARGET_FRAMES, FEATURE_COUNT)
