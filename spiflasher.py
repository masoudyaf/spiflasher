import sys
import serial
import serial.tools.list_ports
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QProgressBar, QFileDialog,
    QMessageBox, QGroupBox, QFormLayout
)
from PyQt5.QtCore import QThread, pyqtSignal

MANUFACTURERS = {
    0xEF: "Winbond",
    0xC2: "Macronix",
    0x20: "Micron",
    0x1F: "Adesto/Atmel",
    0xBF: "Microchip",
    0x1C: "EON",
    0x9D: "ISSI",
}

DEVICE_CAPACITY = {
    0x11: "512KB",
    0x12: "1MB",
    0x13: "2MB",
    0x14: "4MB",
    0x15: "8MB",
    0x16: "16MB",
    0x17: "32MB",
    0x18: "64MB",
    0x19: "128MB",
    0x40: "1MB",
    0x50: "2MB",
    0x60: "4MB",
    0x70: "8MB",
    0x80: "16MB",
    0x90: "32MB",
}

class SerialThread(QThread):
    progress = pyqtSignal(int)
    detect_result = pyqtSignal(bytes, int)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, port, command, file_path=None, flash_size=None):
        super().__init__()
        self.port = port
        self.command = command
        self.file_path = file_path
        self.flash_size = flash_size

    def run(self):
        try:
            with serial.Serial(self.port, 500000, timeout=2) as ser:
                if self.command == 'D':
                    ser.write(b'D')
                    jedec = ser.read(3)
                    if len(jedec) != 3:
                        self.error.emit("JEDEC ID read failed")
                        return
                        
                    capacity_bytes = ser.read(4)
                    if len(capacity_bytes) != 4:
                        self.error.emit("Capacity read failed")
                        return
                        
                    capacity = int.from_bytes(capacity_bytes, 'little')
                    self.detect_result.emit(jedec, capacity)
                    
                elif self.command == 'R':
                    ser.write(b'R')
                    ser.write(b'\x00\x00\x00\x00')
                    ser.write(self.flash_size.to_bytes(4, 'little'))
                    if ser.read(1) != bytes([0xAA]):
                        self.error.emit("ACK failed")
                        return
                    
                    with open(self.file_path, 'wb') as f:
                        total = self.flash_size
                        received = 0
                        while received < total:
                            chunk = ser.read(min(4096, total - received))
                            f.write(chunk)
                            received += len(chunk)
                            self.progress.emit(int(received / total * 100))
                    self.finished.emit()
                    
                elif self.command == 'W':
                    ser.write(b'W')
                    ser.write(b'\x00\x00\x00\x00')
                    ser.write(self.flash_size.to_bytes(4, 'little'))
                    if ser.read(1) != bytes([0xAA]):
                        self.error.emit("ACK failed")
                        return
                    
                    with open(self.file_path, 'rb') as f:
                        total = self.flash_size
                        sent = 0
                        while sent < total:
                            chunk = f.read(256)
                            ser.write(chunk)
                            sent += len(chunk)
                            self.progress.emit(int(sent / total * 100))
                    if ser.read(1) == bytes([0xAA]):
                        self.finished.emit()
                    else:
                        self.error.emit("Write failed")
                        
                elif self.command == 'E':
                    ser.write(b'E')
                    if ser.read(1) == bytes([0xAA]):
                        self.finished.emit()
                    else:
                        self.error.emit("Erase failed")
                    
        except Exception as e:
            self.error.emit(f"Port error: {str(e)}")

class FlashUtility(QMainWindow):
    def __init__(self):
        super().__init__()
        self.capacity = 0
        self.manufacturer = "Unknown"
        self.part_number = "Unknown"
        self.jedec_id = bytes(3)
        self.initUI()
        self.serial_thread = None

    def initUI(self):
        self.setWindowTitle("SPI Flash Programmer")
        self.setGeometry(100, 100, 500, 400)
        
        self.port_combo = QComboBox()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_detect = QPushButton("Detect Flash")
        self.btn_read = QPushButton("Read Flash")
        self.btn_write = QPushButton("Write Flash")
        self.btn_erase = QPushButton("Erase Chip")
        self.progress = QProgressBar()
        self.status = QLabel("Disconnected")
        
        info_group = QGroupBox("Flash Information")
        info_layout = QFormLayout()
        
        self.lbl_manufacturer = QLabel("Unknown")
        self.lbl_capacity = QLabel("0 MB")
        self.lbl_part = QLabel("Unknown")
        self.lbl_jedec = QLabel("00 00 00")
        
        info_layout.addRow(QLabel("Manufacturer:"), self.lbl_manufacturer)
        info_layout.addRow(QLabel("Capacity:"), self.lbl_capacity)
        info_layout.addRow(QLabel("Part Number:"), self.lbl_part)
        info_layout.addRow(QLabel("JEDEC ID:"), self.lbl_jedec)
        info_group.setLayout(info_layout)
        
        layout = QVBoxLayout()
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("COM Port:"))
        port_layout.addWidget(self.port_combo)
        port_layout.addWidget(self.btn_refresh)
        
        layout.addLayout(port_layout)
        layout.addWidget(info_group)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_detect)
        btn_layout.addWidget(self.btn_read)
        btn_layout.addWidget(self.btn_write)
        btn_layout.addWidget(self.btn_erase)
        
        layout.addLayout(btn_layout)
        
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        
        self.btn_refresh.clicked.connect(self.refresh_ports)
        self.btn_detect.clicked.connect(self.detect_flash)
        self.btn_read.clicked.connect(self.read_flash)
        self.btn_write.clicked.connect(self.write_flash)
        self.btn_erase.clicked.connect(self.erase_chip)
        
        self.refresh_ports()

    def refresh_ports(self):
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(port.device)

    def detect_flash(self):
        port = self.port_combo.currentText()
        if not port:
            QMessageBox.critical(self, "Error", "Select a COM port")
            return
            
        self.serial_thread = SerialThread(port, 'D')
        self.serial_thread.detect_result.connect(self.process_detect)
        self.serial_thread.error.connect(self.show_error)
        self.serial_thread.start()
        
    def process_detect(self, jedec, capacity):
        self.jedec_id = jedec
        self.capacity = capacity
        
        mfg_id = jedec[0]
        self.manufacturer = MANUFACTURERS.get(mfg_id, "Unknown")
        
        self.lbl_jedec.setText(f"{jedec[0]:02X} {jedec[1]:02X} {jedec[2]:02X}")
        self.lbl_manufacturer.setText(self.manufacturer)
        
        if self.capacity == 0:
            self.lbl_capacity.setText("Unknown")
        else:
            mb = self.capacity / (1024 * 1024)
            self.lbl_capacity.setText(f"{mb:.1f} MB")
            
        if self.manufacturer == "Winbond":
            device_id = self.jedec_id[1]
            if device_id in DEVICE_CAPACITY:
                self.part_number = f"W25Q{device_id:X} ({DEVICE_CAPACITY[device_id]})"
            else:
                self.part_number = f"Unknown Winbond ({mb:.1f}MB)"
        else:
            device_id = self.jedec_id[2]
            if device_id in DEVICE_CAPACITY:
                self.part_number = f"{DEVICE_CAPACITY[device_id]} Chip"
            else:
                mb = self.capacity / (1024 * 1024) if self.capacity > 0 else 0
                self.part_number = f"Unknown ({mb:.1f}MB)"
                
        self.lbl_part.setText(self.part_number)
        self.status.setText("Flash detected successfully")

    def read_flash(self):
        if self.capacity == 0:
            QMessageBox.critical(self, "Error", "Detect flash first!")
            return
            
        port = self.port_combo.currentText()
        if not port:
            QMessageBox.critical(self, "Error", "Select a COM port")
            return
            
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Flash Dump", "", "BIN Files (*.bin)")
        if not file_path:
            return
            
        self.serial_thread = SerialThread(port, 'R', file_path, self.capacity)
        self.serial_thread.progress.connect(self.progress.setValue)
        self.serial_thread.finished.connect(lambda: self.status.setText("Read complete!"))
        self.serial_thread.error.connect(self.show_error)
        self.serial_thread.start()

    def write_flash(self):
        if self.capacity == 0:
            QMessageBox.critical(self, "Error", "Detect flash first!")
            return
            
        port = self.port_combo.currentText()
        if not port:
            QMessageBox.critical(self, "Error", "Select a COM port")
            return
            
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Flash Image", "", "BIN Files (*.bin)")
        if not file_path:
            return
            
        with open(file_path, 'rb') as f:
            f.seek(0, 2)
            size = f.tell()
            
        if size > self.capacity:
            QMessageBox.critical(self, "Error", 
                f"File size ({size} bytes) exceeds flash capacity ({self.capacity} bytes)")
            return
            
        self.serial_thread = SerialThread(port, 'W', file_path, size)
        self.serial_thread.progress.connect(self.progress.setValue)
        self.serial_thread.finished.connect(lambda: self.status.setText("Write complete!"))
        self.serial_thread.error.connect(self.show_error)
        self.serial_thread.start()

    def erase_chip(self):
        port = self.port_combo.currentText()
        if not port:
            QMessageBox.critical(self, "Error", "Select a COM port")
            return
            
        self.serial_thread = SerialThread(port, 'E')
        self.serial_thread.finished.connect(lambda: self.status.setText("Chip erased!"))
        self.serial_thread.error.connect(self.show_error)
        self.serial_thread.start()

    def show_error(self, message):
        QMessageBox.critical(self, "Error", message)
        self.status.setText("Operation failed")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FlashUtility()
    window.show()
    sys.exit(app.exec_())