import pickle
import cv2
import mediapipe as mp
import numpy as np
import time
import os

model_dict = pickle.load(open('./model.p', 'rb'))
model = model_dict['model']

labels_dict = {
    0: 'A', 1: 'B', 2: 'C', 3: 'D', 4: 'E', 5: 'F', 6: 'G', 7: 'H', 8: 'I', 9: 'J',
    10: 'K', 11: 'L', 12: 'M', 13: 'N', 14: 'O', 15: 'P', 16: 'Q', 17: 'R', 18: 'S',
    19: 'T', 20: 'U', 21: 'V', 22: 'W', 23: 'X', 24: 'Y', 25: 'Z', 26: 'del',
    27: 'nothing', 28: 'space'
}

save_dir = "asl_test"
os.makedirs(save_dir, exist_ok=True)

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles
hands = mp_hands.Hands(static_image_mode=False, min_detection_confidence=0.5)

cap = cv2.VideoCapture(0)  
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

print("Press 'c' or 's' to save the frame with prediction, or 'q' to quit.")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to access the camera!")
        break

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(frame_rgb)

    prediction_text = "No hand detected"
    predicted_character = ""
    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            mp_drawing.draw_landmarks(
                frame, hand_landmarks, mp_hands.HAND_CONNECTIONS,
                mp_drawing_styles.get_default_hand_landmarks_style(),
                mp_drawing_styles.get_default_hand_connections_style()
            )

            x_ = [lm.x for lm in hand_landmarks.landmark]
            y_ = [lm.y for lm in hand_landmarks.landmark]
            data_aux = [(lm.x - min(x_), lm.y - min(y_)) for lm in hand_landmarks.landmark]
            data_aux_flat = [coord for pair in data_aux for coord in pair]

            if len(data_aux_flat) == 42:
                prediction = model.predict([np.asarray(data_aux_flat)])
                predicted_character = labels_dict[int(prediction[0])]
                prediction_text = f"Prediction: {predicted_character}"
                x1, y1 = int(min(x_) * frame.shape[1]) - 10, int(min(y_) * frame.shape[0]) - 10
                x2, y2 = int(max(x_) * frame.shape[1]) + 10, int(max(y_) * frame.shape[0]) + 10
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 3)
                cv2.putText(frame, predicted_character, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 255, 0), 3, cv2.LINE_AA)

    cv2.putText(frame, prediction_text, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    cv2.putText(frame, "Press C/S to save, Q to quit", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.imshow('ASL Test', frame)
    key = cv2.waitKey(1) & 0xFF

    if key in [ord('q'), ord('Q')]:
        break
    elif key in [ord('c'), ord('C'), ord('s'), ord('S')]:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(save_dir, f"asl_test_{predicted_character}_{timestamp}.jpg")
        cv2.imwrite(filename, frame)
        print(f"Image saved as {filename}")

cap.release()
cv2.destroyAllWindows()
print("Program finished.")