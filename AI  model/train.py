import pickle
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report, precision_score, recall_score, f1_score


data_dict = pickle.load(open('./final_data.pickle', 'rb'))
data = np.asarray(data_dict['data'], dtype=np.float32)
labels = np.asarray(data_dict['labels'])


x_train, x_test, y_train, y_test = train_test_split(
    data, labels, test_size=0.2, shuffle=True, stratify=labels, random_state=42
)


model = RandomForestClassifier(
    n_estimators=200,
    max_depth=20,
    random_state=42,
    n_jobs=-1,
    verbose=1
)
model.fit(x_train, y_train)

y_predict = model.predict(x_test)


accuracy = accuracy_score(y_test, y_predict)
print(f"Accuracy: {accuracy * 100:.2f}% of samples were classified correctly!")


precision = precision_score(y_test, y_predict, average='macro')
recall = recall_score(y_test, y_predict, average='macro')
f1 = f1_score(y_test, y_predict, average='macro')

print(f"Precision: {precision:.2f}")
print(f"Recall: {recall:.2f}")
print(f"F1 Score: {f1:.2f}")


print("\nClassification Report:")
print(classification_report(y_test, y_predict))


with open("model.p", "wb") as f:
    pickle.dump({"model": model}, f)
print("Model saved successfully!")


plt.figure(figsize=(4, 5))
plt.bar(["Accuracy"], [accuracy * 100], color='green')
plt.ylabel("Accuracy (%)")
plt.title("Overall Model Accuracy")
plt.ylim(0, 100)
plt.grid(axis='y')
plt.tight_layout()
plt.show()


cm = confusion_matrix(y_test, y_predict)
labels_unique = np.unique(labels)
plt.figure(figsize=(8, 6))
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
            xticklabels=labels_unique,
            yticklabels=labels_unique)
plt.title("Confusion Matrix")
plt.xlabel("Predicted Label")
plt.ylabel("True Label")
plt.tight_layout()
plt.show()


importances = model.feature_importances_
plt.figure(figsize=(12, 4))
plt.bar(range(len(importances)), importances, color='orange')
plt.title("Feature Importances from Random Forest")
plt.xlabel("Feature Index")
plt.ylabel("Importance")
plt.grid(True)
plt.tight_layout()
plt.show()