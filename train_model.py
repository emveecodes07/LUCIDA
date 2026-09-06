import os
import tensorflow as tf
from keras import layers, models

# 1. Dataset directories
BASE_DIR = "main"
train_dir = os.path.join(BASE_DIR, "M-FER2013_cropped", "train")
test_dir = os.path.join(BASE_DIR, "M-FER2013_cropped", "test")

print("[1/4] Checking dataset folders...")
print(f"Train exists: {os.path.exists(train_dir)}")
print(f"Test exists:  {os.path.exists(test_dir)}")

if not os.path.exists(train_dir) or not os.path.exists(test_dir):
    print("ERROR: Folder paths not found. Verify 'main/M-FER2013_cropped/train' exists.")
    exit()

# 2. Modern Keras 3 loader (no ImageDataGenerator)
print("[2/4] Loading image batches...")
BATCH_SIZE = 32
IMG_SIZE = (48, 48)

train_ds = tf.keras.utils.image_dataset_from_directory(
    train_dir,
    labels="inferred",
    label_mode="categorical",
    color_mode="grayscale",
    batch_size=BATCH_SIZE,
    image_size=IMG_SIZE,
    shuffle=True
)

val_ds = tf.keras.utils.image_dataset_from_directory(
    test_dir,
    labels="inferred",
    label_mode="categorical",
    color_mode="grayscale",
    batch_size=BATCH_SIZE,
    image_size=IMG_SIZE,
    shuffle=False
)

num_classes = len(train_ds.class_names)
print(f"Detected {num_classes} classes: {train_ds.class_names}")

# Optimize data pipeline
AUTOTUNE = tf.data.AUTOTUNE
train_ds = train_ds.cache().prefetch(buffer_size=AUTOTUNE)
val_ds = val_ds.cache().prefetch(buffer_size=AUTOTUNE)

# 3. Model Architecture
model = models.Sequential([
    layers.Input(shape=(48, 48, 1)),
    layers.Rescaling(1.0 / 255.0),
    layers.RandomFlip("horizontal"),

    layers.Conv2D(32, (3, 3), activation="relu"),
    layers.BatchNormalization(),
    layers.MaxPooling2D((2, 2)),
    layers.Dropout(0.25),

    layers.Conv2D(64, (3, 3), activation="relu"),
    layers.BatchNormalization(),
    layers.MaxPooling2D((2, 2)),
    layers.Dropout(0.25),

    layers.Flatten(),
    layers.Dense(64, activation="relu"),
    layers.Dropout(0.5),
    layers.Dense(num_classes, activation="softmax")
])

model.compile(
    optimizer="adam",
    loss="categorical_crossentropy",
    metrics=["accuracy"]
)

# 4. Train and save
print("[3/4] Training for 5 epochs...")
model.fit(
    train_ds,
    validation_data=val_ds,
    epochs=5
)

print("[4/4] Saving model file...")
model.save("custom_emotion_model.keras")
print("--> SUCCESS: custom_emotion_model.keras has been created!")