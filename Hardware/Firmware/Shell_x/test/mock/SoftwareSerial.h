#pragma once
#include "Arduino.h"
class SoftwareSerial : public Stream {
public:
  SoftwareSerial(uint8_t rx, uint8_t tx);
  void begin(long baud);
  void end();
  bool listen();
  bool stopListening();
  bool isListening() { return listening_; }
  int available() override;
  int read() override;
  int peek() override;
  size_t write(uint8_t b) override;
  using Print::write;
  // sim side
  void simDeliver(uint8_t b);
  long baud_ = 115200;
  bool listening_ = false;
private:
  uint8_t buf_[64];
  uint8_t head_ = 0, tail_ = 0;
};
