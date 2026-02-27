import cv2  # importer OpenCV

# læs billede fra fil
img = cv2.imread("doortest.jpg")

if img is None:
    print("Kunne ikke finde 'image.jpg' – tjek filnavn og sti.")
else:
    # vis billedet
    cv2.imshow("Test OpenCV", img)

    # vent på et tastetryk
    cv2.waitKey(0)

    # luk alle OpenCV-vinduer
    cv2.destroyAllWindows()