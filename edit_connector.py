import jetson.utils
import argparse
import sys
import numpy as np
import json
import os
import threading
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GObject, GstVideo
from PyQt5 import QtWidgets


parser = argparse.ArgumentParser(description = "shows camera stream and overlays the connector dimensions.\nto edit the dimensions, please edit the csv file directly.\nto reload the csv file, press reload",
                                formatter_class=argparse.RawTextHelpFormatter)

# parser.add_argument("connector", type=str, default="", help="csv file containing the connector dimensions")

try:
	opt = parser.parse_known_args()[0]
except:
	print("")
	parser.print_help()
	sys.exit(0)

dirname = os.path.dirname(os.path.realpath(__file__))
dirname = os.path.dirname(dirname)

# load settings from network config file
with open(os.path.join(dirname, "ressource", "neural_network_config.json")) as f:
    neural_network_config = json.load(f)
video_source = neural_network_config["video_source"]
video_sink = neural_network_config["video_sink"]
width = neural_network_config["width"]
height = neural_network_config["height"]
ai_vision_dir = os.path.expanduser(neural_network_config["ai_vision_dir"])
exposurecompensation = neural_network_config["exposurecompensation"]
rotate_180 = "rotate-180" if neural_network_config["rotate_180"] else "none"

# connector = os.path.splitext(opt.connector)[0] + '.csv'

def create_overlay(left: int, top: int, right: int, bottom: int, color: tuple, img):
    """creates rectange overlay for connector chambers"""
    jetson.utils.cudaDrawLine(img, (left,top), (left,bottom), color, 1)
    jetson.utils.cudaDrawLine(img, (left,bottom), (right,bottom), color, 1)
    jetson.utils.cudaDrawLine(img, (right,bottom), (right,top), color, 1)
    jetson.utils.cudaDrawLine(img, (right,top), (left,top), color, 1)

video_input = jetson.utils.videoSource(video_source, argv=[f"--input-width={width}", f"--input-height={height}", f"--exposurecompensation={exposurecompensation}", f"--input-flip={rotate_180}"])
video_output = jetson.utils.videoOutput(video_sink, argv=["--headless"])

class FirstWindow(QWidget):
    QMainWindow.left = []
    QMainWindow.right = []
    QMainWindow.top = []
    QMainWindow.bottom = []
    QMainWindow.left_temp = []
    QMainWindow.right_temp = []
    QMainWindow.top_temp = []
    QMainWindow.bottom_temp = []
    QMainWindow.selected_box = -1
    QMainWindow.x_number = 1
    QMainWindow.y_number = 1
    def __init__(self, connector):
        QMainWindow.__init__(self, None)
        self.connector = connector
        self.setWindowTitle("Connector Editor - " + os.path.basename(os.path.join(ai_vision_dir, "plugs", self.connector)))
        self.setGeometry(50,50,700,350)

        # setup video widget
        self.videowidget = VideoWidget(parent=self)

        # create control buttons
        self.buttonFont = QFont("Arial", 10)
        self.button1 = QPushButton("Reload")
        self.button1.setStyleSheet("background-color: #66cc00; color: white")
        self.button1.setFont(self.buttonFont)
        self.button1.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)
        self.button1.clicked.connect(lambda: self.load_connector(os.path.join(ai_vision_dir, "plugs", self.connector)))

        x_label = QLabel("Horizontal Boxes")
        y_label = QLabel("Vertical Boxes")
        self.x_input = QLineEdit("1")
        self.y_input = QLineEdit("1")
        self.x_input.setValidator(QIntValidator(1,10000))
        self.y_input.setValidator(QIntValidator(1,10000))
        self.x_input.textChanged[str].connect(self.update_input)
        self.y_input.textChanged[str].connect(self.update_input)

        self.add_button = QPushButton("Add")
        self.add_button.setStyleSheet("background-color: #66cc00; color: white")
        self.add_button.setFont(self.buttonFont)
        self.add_button.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed)
        self.add_button.clicked.connect(self.add_values)

        self.save_button = QPushButton("Save")
        self.save_button.setStyleSheet("background-color: #66cc00; color: white")
        self.save_button.setFont(self.buttonFont)
        self.save_button.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed)
        self.save_button.clicked.connect(lambda: self.save_file(os.path.join(ai_vision_dir, "plugs", self.connector)))

        delete_label = QLabel("Delete Boxes")
        self.delete_button = QPushButton("Delete")
        self.delete_button.setStyleSheet("background-color: #ED2939; color: white")
        self.delete_button.setFont(self.buttonFont)
        self.delete_button.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed)
        self.delete_button.clicked.connect(self.delete_boxes)

        self.delete_input = QLineEdit("0")
        self.delete_input.setValidator(QIntValidator(0,10000))


        # load connector for the first time
        self.load_connector(os.path.join(ai_vision_dir, "plugs", self.connector))

        # create input thread
        self.input_thread = threading.Thread(target=self.inputThread, daemon=True)
        self.input_thread.start()

        # create layouts
        videolayout = QHBoxLayout()
        # videolayout.addStretch(1)
        videolayout.addWidget(self.videowidget)
        # videolayout.addStretch(1)

        layout = QHBoxLayout()
        # layout.addStretch(1)
        layout.addLayout(videolayout, stretch=20)
        # layout.addStretch(1)
        # layout.addWidget(self.button1, stretch=1)

        inputLayout = QVBoxLayout()
        inputLayout.addWidget(x_label)
        inputLayout.addWidget(self.x_input)
        inputLayout.addWidget(y_label)
        inputLayout.addWidget(self.y_input)
        inputLayout.addWidget(self.add_button)
        inputLayout.addWidget(self.save_button)
        inputLayout.addWidget(delete_label)
        inputLayout.addWidget(self.delete_input)
        inputLayout.addWidget(self.delete_button)
        inputLayout.addStretch()

        layout.addLayout(inputLayout)

        self.setLayout(layout)

    def add_values(self):
        QMainWindow.left = np.append(QMainWindow.left, QMainWindow.left_temp, 0)
        QMainWindow.top = np.append(QMainWindow.top, QMainWindow.top_temp, 0)
        QMainWindow.bottom = np.append(QMainWindow.bottom, QMainWindow.bottom_temp, 0)
        QMainWindow.right = np.append(QMainWindow.right, QMainWindow.right_temp, 0)

    def delete_boxes(self):
        try:
            QMainWindow.left = np.delete(QMainWindow.left, int(self.delete_input.text()))
            QMainWindow.right = np.delete(QMainWindow.right, int(self.delete_input.text()))
            QMainWindow.top = np.delete(QMainWindow.top, int(self.delete_input.text()))
            QMainWindow.bottom = np.delete(QMainWindow.bottom, int(self.delete_input.text()))
        except:
            pass

    def update_input(self):
        try:
            QMainWindow.x_number = int(self.x_input.text())
            QMainWindow.y_number = int(self.y_input.text())
        except:
            pass

    def save_file(self, connectorfile):
        array = np.vstack([QMainWindow.left + (QMainWindow.right - QMainWindow.left)/2, QMainWindow.top + (QMainWindow.bottom - QMainWindow.top)/2, QMainWindow.right - QMainWindow.left, QMainWindow.bottom - QMainWindow.top])
        array = np.rint(array).T
        # array = np.vstack([["x","y","chamber_size_x","chamber_size_y"], array.T])
        print(array)
        np.savetxt(connectorfile, array, delimiter=',',header ="x,y,chamber_size_x,chamber_size_y", fmt='%.0f')

    def load_connector(self, connectorfile):
        """Loads connector from csv file and returns dimensions for cropping as array of [left,top,right,bottom]"""
        try:
            connector_array = np.genfromtxt(connectorfile, delimiter = ',', comments='#')
            if connector_array.ndim == 1:
                QMainWindow.left = [connector_array[0] - connector_array[2]/2]
                QMainWindow.top = [connector_array[1] - connector_array[3]/2]
                QMainWindow.right = [connector_array[0] + connector_array[2]/2]
                QMainWindow.bottom = [connector_array[1] + connector_array[3]/2]
            else:
                QMainWindow.left = connector_array[:,0] - connector_array[:,2]/2
                QMainWindow.top = connector_array[:,1] - connector_array[:,3]/2
                QMainWindow.right = connector_array[:,0] + connector_array[:,2]/2
                QMainWindow.bottom = connector_array[:,1] + connector_array[:,3]/2
            print(connector_array)
            print(QMainWindow.left)
           
        except Exception as e: 
            print(e)
            QMainWindow.left = []
            QMainWindow.top = []
            QMainWindow.right = []
            QMainWindow.bottom = []

    def inputThread(self):
        """capture images and create output stream"""
        font = jetson.utils.cudaFont()
        while True:
            self.img = video_input.Capture()
            temp_left = np.append(QMainWindow.left, QMainWindow.left_temp, 0)
            temp_top = np.append(QMainWindow.top, QMainWindow.top_temp, 0)
            temp_bottom = np.append(QMainWindow.bottom, QMainWindow.bottom_temp, 0)
            temp_right = np.append(QMainWindow.right, QMainWindow.right_temp, 0)
            for idx,(left, top, right, bottom) in enumerate(zip(temp_left, temp_top, temp_right, temp_bottom)):
                create_overlay(left, top, right, bottom, (0,255,0,255), self.img)
                font.OverlayText(self.img, self.img.width, self.img.height, f" {idx:02} " , int(left)-10, int(top)+10, font.White)

            video_output.Render(self.img)

class VideoWidget(QWidget):
    def __init__(self, parent=None):
        QWidget.__init__(self, parent=parent)
        self.video_frame = QLabel()
        lay = QVBoxLayout()
        lay.addWidget(self.video_frame)
        self.setLayout(lay)

    def mousePressEvent(self, event):
        pass


class VideoWidget(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.windowId = self.winId()
        self.mousePressEvent = self.mousePressed
        self.mouseReleaseEvent = self.mouseReleased
        self.mouseMoveEvent = self.mouseMoved
        self.x_start = 0
        self.y_start = 0
        self.x_end = 0
        self.y_end = 0


    def mousePressed(self, event):
        self.x_start = event.x()
        self.y_start = event.y()

    def mouseReleased(self, event):
        self.x_end = event.x()
        self.y_end = event.y()

    def mouseMoved(self, event):
        pass

    def setup_pipeline(self):
        self.pipeline = Gst.parse_launch("intervideosrc channel=v0 ! xvimagesink")
        bus =  self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.enable_sync_message_emission()
        bus.connect('sync-message::element', self.on_sync_message)

    def on_sync_message(self, bus, msg):
        message_name = msg.get_structure().get_name()
        print(message_name)
        if message_name == 'prepare-window-handle':
            win_id = self.windowId
            assert win_id
            imagesink = msg.src
            imagesink.set_window_handle(win_id)

    def  start_pipeline(self):
        self.pipeline.set_state(Gst.State.PLAYING)


def move_annotation(annotations, annotation_idx, delta_x, delta_y):
    if isinstance(annotation_idx, int):
        annotation = annotations[annotation_idx]
        move_annotations([annotation], delta_x, delta_y)
    else:
        annotations_to_move = [annotations[idx] for idx in annotation_idx]
        move_annotations(annotations_to_move, delta_x, delta_y)

    selected_annotations = []

    def on_mouse(event, x, y, flags, param):
        global selected_annotations
    
        if event == cv2.EVENT_LBUTTONDOWN:
            for idx, annotation in enumerate(annotations):
                if x >= annotation['left'] and x <= annotation['right'] and y >= annotation['top'] and y <= annotation['bottom']:
                    selected_annotations.append(idx)
                    break
    
        elif event == cv2.EVENT_RBUTTONDOWN:
            # Clear the list of selected annotations
            selected_annotations.clear()
    
        # Draw the selected annotations
        for idx in selected_annotations:
            annotation = annotations[idx]
            cv2.rectangle(img, (annotation['left'], annotation['top']), (annotation['right'], annotation['bottom']), (0, 255, 0), 2)

    def on_key(event, key, *args):
        if key == 27:
            # ESC key
            cv2.destroyAllWindows()
            exit()
        elif key == ord('q'):
            # Quit editing mode
            return False
        elif key == ord('up'):
            # Move the selected annotations up
            move_annotation(annotations, selected_annotations, 0, -10)
        elif key == ord('down'):
            # Move the selected annotations down
            move_annotation(annotations, selected_annotations, 0, 10)
        elif key == ord('left'):
            # Move the selected annotations left
            move_annotation(annotations, selected_annotations, -10, 0)
        elif key == ord('right'):
            # Move the selected annotations right
            move_annotation(annotations, selected_annotations, 10, 0)




    def mousePressed(self, event):
        self.x_start, self.y_start = self.getMousePos(event)
        # print(f"mouse pressed: {self.x_start}, {self.y_start}")

    def mouseReleased(self, event):
        QMainWindow.selected_box = -1

    def mouseMoved(self, event):
        self.x_end, self.y_end = self.getMousePos(event)
        # print(f"mouse released: {self.x_end}, {self.y_end}")

        self.x_left = min(self.x_start, self.x_end)
        self.x_right = max(self.x_start, self.x_end)
        self.y_top = min(self.y_start, self.y_end)
        self.y_bottom = max(self.y_start, self.y_end)
        if event.buttons() == Qt.LeftButton:
            QMainWindow.selected_box = -1
            self.add_boxes()
        elif event.buttons() == Qt.RightButton:
            QMainWindow.left_temp = []
            QMainWindow.right_temp = []
            QMainWindow.top_temp = []
            QMainWindow.bottom_temp = []
            self.move_boxes()

    def getMousePos(self, event):
        video_size = width/height
        x_pos = event.pos().x()
        y_pos = event.pos().y()
        x_len = self.width()
        y_len = self.height()

        if x_len/y_len > video_size:
            video_height = y_len
            video_width = y_len * video_size
        else:
            video_width = x_len
            video_height = x_len * 1/video_size

        # print(f"video size: {video_width}, {video_height}")

        x_offset = (x_len - video_width)/2
        y_offset = (y_len - video_height)/2

        # print(f"video offset: {x_offset}, {y_offset}")

        x_adjusted = (x_pos-x_offset)*width/video_width
        y_adjusted = (y_pos-y_offset)*height/video_height

        # print(f"adjusted position: {x_adjusted}, {y_adjusted}")

        return x_adjusted, y_adjusted

    def add_boxes(self):
        x_size = (self.x_right - self.x_left)/int(QMainWindow.x_number)
        y_size = (self.y_bottom - self.y_top)/int(QMainWindow.y_number)
        left = []
        right = []
        top = []
        bottom = []

        for y in range(int(QMainWindow.y_number)):
            for x in range(int(QMainWindow.x_number)):
                left.append(self.x_left + x*x_size)
                right.append(self.x_left + (x+1)*x_size)
                top.append(self.y_top + y*y_size)
                bottom.append(self.y_top + (y+1)*y_size)

        QMainWindow.left_temp = left
        QMainWindow.right_temp = right
        QMainWindow.top_temp = top
        QMainWindow.bottom_temp = bottom

    def move_boxes(self):
        """moves the selected box"""
        if QMainWindow.selected_box != -1:
            x_size = QMainWindow.right[QMainWindow.selected_box] - QMainWindow.left[QMainWindow.selected_box]
            y_size = QMainWindow.bottom[QMainWindow.selected_box] - QMainWindow.top[QMainWindow.selected_box]
            QMainWindow.left[QMainWindow.selected_box] = self.x_end - 0.5*x_size
            QMainWindow.right[QMainWindow.selected_box] = self.x_end + 0.5*x_size
            QMainWindow.top[QMainWindow.selected_box] = self.y_end - 0.5*y_size
            QMainWindow.bottom[QMainWindow.selected_box] = self.y_end + 0.5*y_size
        else:
            for idx,(l,r,t,b) in reversed(list(enumerate(zip(QMainWindow.left, QMainWindow.right, QMainWindow.top, QMainWindow.bottom)))):
                if min(l,r) < self.x_end < max(l,r) and min(t,b) < self.y_end < max(t,b):
                    # print(f"{self.x_end}, {self.y_end} is between {l},{r},{t},{b} at index {idx}")
                    x_size = QMainWindow.right[idx] - QMainWindow.left[idx]
                    y_size = QMainWindow.bottom[idx] - QMainWindow.top[idx]
                    QMainWindow.left[idx] = self.x_end - 0.5*x_size
                    QMainWindow.right[idx] = self.x_end + 0.5*x_size
                    QMainWindow.top[idx] = self.y_end - 0.5*y_size
                    QMainWindow.bottom[idx] = self.y_end + 0.5*y_size
                    QMainWindow.selected_box = idx
                    break

if __name__ == "__main__":
    # ask for connector name
    while True:
        connector = input("Please enter a connector: ")
        connector = os.path.splitext(connector)[0] + '.csv'
        if os.path.exists(os.path.join(ai_vision_dir, "plugs", connector)):
            break
        elif input(f"Connector '{connector}' doesn't exist, create it now?(Y/N)") in ["Y", "y", "YES", "yes", "YEs", "Yes", "yEs", "yeS", "yES"]:
            np.savetxt(os.path.join(ai_vision_dir, "plugs", connector), [], delimiter=',',header ="x,y,chamber_size_x,chamber_size_y")
            break


    GObject.threads_init()
    Gst.init(None)

    app = QApplication([])

    # setup pipeline for video output
    window = FirstWindow(connector)
    window.videowidget.setup_pipeline()
    window.videowidget.start_pipeline()

    window.show()
    sys.exit(app.exec_())
