import sys
import cv2
import numpy as np
from PyQt5.QtCore import Qt, QPoint, QSize
from PyQt5.QtGui import QImage, QPixmap, QPolygonF, QPainter, QPen, QColor
from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel, QPushButton,
                             QFileDialog, QVBoxLayout, QHBoxLayout, QWidget,
                             QGraphicsScene, QGraphicsView, QGraphicsPolygonItem,
                             QListWidget, QMessageBox, QProgressBar)


class VideoWatermarkRemover(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Batch Video Watermark Remover")
        self.setGeometry(100, 100, 1200, 800)

        self.video_paths = []
        self.coordinates = []
        self.frame = None
        self.mask_created = False
        self.mask = None

        self.init_ui()

    def init_ui(self):
        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Video display and list layout
        content_layout = QHBoxLayout()

        # Left side - video display
        left_layout = QVBoxLayout()

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setMinimumSize(800, 600)
        left_layout.addWidget(QLabel("Video Preview (select area):"))
        left_layout.addWidget(self.view)

        # Right side - video list
        right_layout = QVBoxLayout()

        right_layout.addWidget(QLabel("Selected Videos:"))
        self.video_list = QListWidget()
        self.video_list.setMaximumWidth(350)
        right_layout.addWidget(self.video_list)

        content_layout.addLayout(left_layout)
        content_layout.addLayout(right_layout)
        layout.addLayout(content_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Controls
        controls_layout = QHBoxLayout()

        self.btn_load_videos = QPushButton("Load Videos")
        self.btn_load_videos.clicked.connect(self.load_videos)
        controls_layout.addWidget(self.btn_load_videos)

        self.btn_select_area = QPushButton("Select Watermark Area")
        self.btn_select_area.clicked.connect(self.enable_area_selection)
        self.btn_select_area.setEnabled(False)
        controls_layout.addWidget(self.btn_select_area)

        self.btn_process = QPushButton("Process All Videos")
        self.btn_process.clicked.connect(self.process_all_videos)
        self.btn_process.setEnabled(False)
        controls_layout.addWidget(self.btn_process)

        layout.addLayout(controls_layout)

    def load_videos(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Video Files", "", "Video Files (*.mp4 *.avi *.mov *.mkv)")

        if files:
            self.video_paths = files
            self.video_list.clear()
            self.video_list.addItems([f.split('/')[-1] for f in files])
            self.btn_select_area.setEnabled(True)
            self.show_first_frame()

    def show_first_frame(self):
        if not self.video_paths:
            return

        cap = cv2.VideoCapture(self.video_paths[0])
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                self.frame = frame
                height, width, channel = frame.shape
                bytes_per_line = 3 * width
                q_img = QImage(frame.data, width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
                pixmap = QPixmap.fromImage(q_img)

                self.scene.clear()
                self.scene.addPixmap(pixmap)
                self.view.setScene(self.scene)
                cap.release()

    def enable_area_selection(self):
        self.coordinates = []
        self.mask_created = False
        self.view.mousePressEvent = self.get_coordinates
        QMessageBox.information(self, "Area Selection",
                                "Click on four points to define the watermark area. Click in order: top-left, top-right, bottom-right, bottom-left.")

    def get_coordinates(self, event):
        if len(self.coordinates) < 4:
            point = self.view.mapToScene(event.pos())
            x, y = point.x(), point.y()
            self.coordinates.append((x, y))

            # Draw selected points
            pen = QPen(QColor(255, 0, 0))
            self.scene.addEllipse(x - 3, y - 3, 6, 6, pen)

            if len(self.coordinates) == 4:
                self.draw_selection_polygon()
                self.create_mask()
                self.btn_process.setEnabled(True)

    def draw_selection_polygon(self):
        polygon = QPolygonF()
        for x, y in self.coordinates:
            polygon.append(QPoint(x, y))

        pen = QPen(QColor(0, 255, 0), 2)
        self.scene.addPolygon(polygon, pen)

    def create_mask(self):
        if len(self.coordinates) != 4:
            return

        # Create mask from the first frame
        height, width = self.frame.shape[:2]
        self.mask = np.zeros((height, width), dtype=np.uint8)
        pts = np.array([(int(x), int(y)) for x, y in self.coordinates], dtype=np.int32)
        cv2.fillPoly(self.mask, [pts], color=255)
        self.mask_created = True

    def process_all_videos(self):
        if not self.mask_created or not self.video_paths:
            QMessageBox.warning(self, "Error", "Please select videos and define watermark area first.")
            return

        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not output_dir:
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(self.video_paths))

        for i, video_path in enumerate(self.video_paths):
            self.progress_bar.setValue(i)
            QApplication.processEvents()  # Keep UI responsive

            output_path = f"{output_dir}/processed_{video_path.split('/')[-1]}"
            success = self.remove_watermark(video_path, output_path)

            if not success:
                QMessageBox.warning(self, "Processing Error",
                                    f"Failed to process: {video_path.split('/')[-1]}")
                break

        self.progress_bar.setVisible(False)
        QMessageBox.information(self, "Complete", "All videos processed successfully!")

    def remove_watermark(self, input_path, output_path):
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            return False

        # Get video properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        # Resize mask if video dimensions don't match
        if (height, width) != self.mask.shape[:2]:
            mask_resized = cv2.resize(self.mask, (width, height))
        else:
            mask_resized = self.mask

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            # Apply inpainting
            inpainted_frame = cv2.inpaint(frame, mask_resized, 3, cv2.INPAINT_TELEA)
            out.write(inpainted_frame)

        cap.release()
        out.release()
        return True


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoWatermarkRemover()
    window.show()
    sys.exit(app.exec_())