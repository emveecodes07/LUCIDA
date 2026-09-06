import cv2
from fer.fer import FER
from collections import deque, Counter

# Initialize FER detector
detector = FER(mtcnn=False)

# Open webcam index 0
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

if not cap.isOpened():
    print("Error: Could not access the webcam.")
    exit()

print("Webcam feed running with smoothing. Press 'q' on video window to quit.")

# Frame skipping parameter: process 1 out of every 6 frames
FRAME_INTERVAL = 10
frame_count = 0

# Rolling window for smoothing (stores the last 10 detected emotions)
WINDOW_SIZE = 10
emotion_history = deque(maxlen=WINDOW_SIZE)

# Active display values
smoothed_emotion = "SCANNING..."
current_confidence = 0

while True:
    ret, frame = cap.read()
    if not ret:
        print("Error: Failed to read frame.")
        break

    # Un-reverse / mirror the feed
    frame = cv2.flip(frame, 1)

    # Run inference only on designated interval frames
    if frame_count % FRAME_INTERVAL == 0:
        result = detector.top_emotion(frame)
        if result and result[0] is not None:
            raw_emotion, raw_score = result
            
            # Append detected emotion to the sliding queue
            emotion_history.append(raw_emotion)
            current_confidence = int(raw_score * 100)

            # Determine dominant emotion by majority vote
            most_frequent = Counter(emotion_history).most_common(1)[0][0]
            smoothed_emotion = most_frequent.upper()

    # Draw status overlay
    label = f"{smoothed_emotion} ({current_confidence}%)"
    cv2.putText(
        frame,
        label,
        (30, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )

    cv2.imshow("Emotion Test Feed (Smoothed)", frame)
    frame_count += 1

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()