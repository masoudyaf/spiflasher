#include <SPI.h>
#include <FS.h>
#include <SPIFFS.h>

#define SPI_CS 5
#define BUFFER_SIZE 256
#define ACK 0xAA
#define NACK 0x55

SPIClass spi(HSPI);

void setup() {
  Serial.begin(500000);
  spi.begin(18, 19, 23, SPI_CS);
  pinMode(SPI_CS, OUTPUT);
  digitalWrite(SPI_CS, HIGH);
}

void loop() {
  if (Serial.available() >= 1) {
    char command = Serial.read();
    
    switch (command) {
      case 'R':
        readFlash();
        break;
        
      case 'W':
        writeFlash();
        break;
        
      case 'E':
        eraseChip();
        break;
        
      case 'D':
        fullDetect();
        break;
    }
  }
}

void fullDetect() {
  waitBusy();
  digitalWrite(SPI_CS, LOW);
  spi.transfer(0x9F);
  uint8_t jedec[3] = {
    spi.transfer(0), spi.transfer(0), spi.transfer(0)
  };
  digitalWrite(SPI_CS, HIGH);
  
  uint32_t capacity = getCapacityFromID(jedec[2]);
  
  if (capacity == 0 && jedec[0] == 0xEF) {
    capacity = getCapacityFromID(jedec[1]);
  }
  
  Serial.write(jedec, 3);
  uint8_t capBytes[4] = {
    (uint8_t)(capacity),
    (uint8_t)(capacity >> 8),
    (uint8_t)(capacity >> 16),
    (uint8_t)(capacity >> 24)
  };
  Serial.write(capBytes, 4);
}

uint32_t getCapacityFromID(uint8_t deviceID) {
  switch (deviceID) {
    case 0x11: return 0x80000;
    case 0x12: return 0x100000;
    case 0x13: return 0x200000;
    case 0x14: return 0x400000;
    case 0x15: return 0x800000;   
    case 0x16: return 0x1000000;
    case 0x17: return 0x2000000;
    case 0x18: return 0x4000000;
    case 0x19: return 0x8000000; 
    case 0x40: return 0x100000;  
    case 0x50: return 0x200000; 
    case 0x60: return 0x400000;
    case 0x70: return 0x800000;
    case 0x80: return 0x1000000;
    case 0x90: return 0x2000000;
    default:   return 0;
  }
}

void readFlash() {
  uint32_t addr = readU32();
  uint32_t len = readU32();
  uint8_t buffer[BUFFER_SIZE];
  
  Serial.write(ACK);
  
  while (len > 0) {
    uint32_t chunk = (len > BUFFER_SIZE) ? BUFFER_SIZE : len;
    digitalWrite(SPI_CS, LOW);
    spi.transfer(0x03);
    spi.transfer(addr >> 16);
    spi.transfer(addr >> 8);
    spi.transfer(addr);
    for (uint32_t i = 0; i < chunk; i++) {
      buffer[i] = spi.transfer(0);
    }
    digitalWrite(SPI_CS, HIGH);
    Serial.write(buffer, chunk);
    addr += chunk;
    len -= chunk;
  }
}

void writeFlash() {
  uint32_t addr = readU32();
  uint32_t len = readU32();
  uint8_t buffer[BUFFER_SIZE];
  
  Serial.write(ACK);
  
  while (len > 0) {
    uint32_t chunk = (len > BUFFER_SIZE) ? BUFFER_SIZE : len;
    Serial.readBytes(buffer, chunk);
    writePage(addr, buffer, chunk);
    addr += chunk;
    len -= chunk;
  }
  
  Serial.write(ACK);
}

void writePage(uint32_t addr, uint8_t *data, uint32_t len) {
  digitalWrite(SPI_CS, LOW);
  spi.transfer(0x06);
  digitalWrite(SPI_CS, HIGH);
  delayMicroseconds(1);
  
  digitalWrite(SPI_CS, LOW);
  spi.transfer(0x02);
  spi.transfer(addr >> 16);
  spi.transfer(addr >> 8);
  spi.transfer(addr);
  for (uint32_t i = 0; i < len; i++) {
    spi.transfer(data[i]);
  }
  digitalWrite(SPI_CS, HIGH);
  waitBusy();
}

void eraseChip() {
  digitalWrite(SPI_CS, LOW);
  spi.transfer(0x06);
  digitalWrite(SPI_CS, HIGH);
  delayMicroseconds(1);
  
  digitalWrite(SPI_CS, LOW);
  spi.transfer(0xC7);
  digitalWrite(SPI_CS, HIGH);
  waitBusy();
  Serial.write(ACK);
}

void waitBusy() {
  uint8_t status;
  do {
    delay(1);
    digitalWrite(SPI_CS, LOW);
    spi.transfer(0x05);
    status = spi.transfer(0);
    digitalWrite(SPI_CS, HIGH);
  } while (status & 0x01);
}

uint32_t readU32() {
  uint8_t bytes[4];
  Serial.readBytes(bytes, 4);
  return (bytes[3] << 24) | (bytes[2] << 16) | (bytes[1] << 8) | bytes[0];
}