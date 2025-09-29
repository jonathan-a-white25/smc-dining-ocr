import cv2
import numpy as np

def preprocess_for_digits(np_img):
    gray = cv2.cvtColor(np_img, cv2.COLOR_RGB2GRAY)
    th = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 31, 10
    )
    denoise = cv2.medianBlur(th, 3)
    kernel = np.ones((2, 2), np.uint8)
    morph = cv2.morphologyEx(denoise, cv2.MORPH_CLOSE, kernel, iterations=1)
    return morph
