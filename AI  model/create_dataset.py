import os
import pickle
import mediapipe as mp
import cv2

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(static_image_mode=True, min_detection_confidence=0.3)

DATA_DIR = '.\data'

data = []
labels = []
USE_PLACEHOLDER = False  
for dir_ in os.listdir(DATA_DIR):
    for img_path in os.listdir(os.path.join(DATA_DIR, dir_)):
        img = cv2.imread(os.path.join(DATA_DIR, dir_, img_path))
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        results = hands.process(img_rgb)

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                x_ = [lm.x for lm in hand_landmarks.landmark]
                y_ = [lm.y for lm in hand_landmarks.landmark]

                data_aux = [(lm.x - min(x_), lm.y - min(y_))
                            for lm in hand_landmarks.landmark]
                data_aux_flat = [coord for pair in data_aux for coord in pair]

                if len(data_aux_flat) == 42:
                    data.append(data_aux_flat)
                    labels.append(dir_)
                    print(
                        f" Processed: {img_path} | Features: {len(data_aux_flat)}")
                else:
                    print(
                        f" Incomplete hand detected in {img_path}, skipping.")
        else:
            print(f" No hands detected in {img_path}")

            if USE_PLACEHOLDER:
                data.append([0] * 42)
                labels.append(dir_)
                print(f" Added placeholder for {img_path}")

f = open('final_data.pickle', 'wb')
pickle.dump({'data': data, 'labels': labels}, f)
f.close()

print(f"\n Dataset preparation complete! Processed {len(data)} images.")
