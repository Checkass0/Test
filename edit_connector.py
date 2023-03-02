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


import cv2
import argparse
from jetson.utils.videoSource import videoSource
from jetson.utils.display import display
from jetson.utils import cudaFromNumpy, cudaToNumpy
from jetson.inference.detectNet import detectNet



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
    def __init__(self, parent):
        QMainWindow.__init__(self, parent)
        self.windowId = self.winId()
        # self.setStyleSheet("background-color: black")
        # self.setFixedSize(width,height)
        self.mousePressEvent = self.mousePressed
        self.mouseReleaseEvent = self.mouseReleased
        self.mouseMoveEvent = self.mouseMoved
        # self.keyPressEvent = self.delete_boxes
        # self.mouseDoubleClickEvent = self.mouseRightClick
        self.x_start = 0
        self.y_start = 0
        self.x_end = 0
        self.y_end = 0

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

class BoxEditor:
    def __init__(self, window_name, video_src, detector, boxes=[]):
        self.window_name = window_name
        self.video_src = video_src
        self.detector = detector
        self.boxes = boxes
        
        # Initialisiere die Mausvariablen
        self.mouse_down = False
        self.prev_mouse_x = 0
        self.prev_mouse_y = 0
        self.mouse_x = 0
        self.mouse_y = 0
        
        # Erstelle das Fenster
        cv2.namedWindow(window_name)
        cv2.setMouseCallback(window_name, self.mouse_callback)
        
    def mouse_callback(self, event, x, y, flags, param):
        # Speichere die Mausposition
        self.mouse_x = x
        self.mouse_y = y
        
        # Überprüfe, ob die linke Maustaste gedrückt wird
        if event == cv2.EVENT_LBUTTONDOWN:
            self.mouse_down = True
            self.prev_mouse_x = x
            self.prev_mouse_y = y
        elif event == cv2.EVENT_LBUTTONUP:
            self.mouse_down = False
    
    def draw_boxes(self, frame, boxes):
        # Kopiere das Frame
        frame_copy = frame.copy()
        
        # Zeichne die Bounding Boxes auf das Frame
        for box in boxes:
            cv2.rectangle(frame_copy, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
        
        # Zeige das Frame mit den Bounding Boxes
        cv2.imshow(self.window_name, frame_copy)
    
    def move_boxes(self):
        # Wähle die Bounding Boxes aus, die verschoben werden sollen
        selected_boxes = []
        while True:
            # Warte auf die nächste Frame
            frame = self.video_src.Capture()
            
            # Zeige die Bounding Boxes auf dem Frame
            self.draw_boxes(frame, self.boxes)
            
            # Zeige das Frame auf dem Bildschirm
            cv2.imshow(self.window_name, frame)
            
            # Überprüfe, ob eine Taste gedrückt wird
            key = cv2.waitKey(1) & 0xFF
            
            # Wenn die Eingabetaste gedrückt wird, beende die Schleife
            if key == ord('\n'):
                break
                
            # Wenn die Entfernen-Taste gedrückt wird, entferne die ausgewählten Bounding Boxes
            if key == 8:
                self.boxes = [box for box in self.boxes if box not in selected_boxes]
                selected_boxes = []
                
            # Überprüfe, ob die linke Maustaste gedrückt wird
            if cv2.getWindowProperty(self.window_name, cv2.WND_PROP_VISIBLE) < 1:
                break
            elif self.mouse_down:
                # Wähle die Bounding Boxes aus, die den aktuellen Mauszeiger umschließen
                curr_boxes = []
                for box in self.boxes:
                    x1, y1, x2, y2 = box
                    if self.mouse_x >= x1 and self.mouse_x <= x2 and self.mouse_y >= y1 and self.mouse_y <= y2:

                        curr_boxes.append(box)
                
                # Markiere die ausgewählten Bounding Boxes
                for box in curr_boxes:
                    if box not in selected_boxes:
                        selected_boxes.append(box)
                
                # Verschiebe die ausgewählten Bounding Boxes
                dx = self.mouse_x - self.prev_mouse_x
                dy = self.mouse_y - self.prev_mouse_y
                for i in range(len(self.boxes)):
                    if self.boxes[i] in selected_boxes:
                        self.boxes[i] = (
                            self.boxes[i][0] + dx,
                            self.boxes[i][1] + dy,
                            self.boxes[i][2] + dx,
                            self.boxes[i][3] + dy
                        )
                
                # Speichere die Mausposition für den nächsten Frame
                self.prev_mouse_x = self.mouse_x
                self.prev_mouse_y = self.mouse_y
        
        # Beende die Bewegung der Bounding Boxes
        self.mouse_down = False
    
    def run(self):
        while True:
            # Warte auf die nächste Frame
            frame = self.video_src.Capture()
            
            # Detektiere Objekte im Frame
            detections = self.detector.Detect(frame)
            
            # Extrahiere die Bounding Boxes aus den Detektionen
            boxes = []
            for detection in detections:
                x1, y1, x2, y2 = detection.ROI
                boxes.append((int(x1), int(y1), int(x2), int(y2)))
            
            # Füge die vom Benutzer erstellten Bounding Boxes hinzu
            boxes.extend(self.boxes)
            
            # Zeige die Bounding Boxes auf dem Frame
            self.draw_boxes(frame, boxes)
            
            # Überprüfe, ob eine Taste gedrückt wird
            key = cv2.waitKey(1) & 0xFF
            
            # Wenn die ESC-Taste gedrückt wird, beende das Programm
            if key == 27:
                break
            
            # Wenn die Leertaste gedrückt wird, führe die Bewegung der Bounding Boxes aus
            if key == ord(' '):
                self.move_boxes()
                
            # Zeige das Frame auf dem Bildschirm
            cv2.imshow(self.window_name, frame)
        
        # Schließe das Fenster
        cv2.destroyAllWindows()


def main():
    # Analysiere die Eingabeparameter
    parser = argparse.ArgumentParser(description="Edit bounding boxes")
    parser.add_argument("input_uri", type=str, help="URI for input stream")
    parser.add_argument("--model", type=str, default="ssd-mobilenet-v2",
                        help="pre-trained model to load (see the list of models in the detectNet class for options)")
    args = parser.parse_args()
    
    # Erstelle den Objektdetektor
    detector = detectNet(args.model, threshold=0.5)
    
    # Erstelle die Videoquelle
    video_src = videoSource(args.input_uri)
    
    # Erstelle den BoxEditor
    box_editor = BoxEditor("Bounding Box Editor", video_src, detector)
    
    # Führe das Programm aus
    box_editor.run()

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
