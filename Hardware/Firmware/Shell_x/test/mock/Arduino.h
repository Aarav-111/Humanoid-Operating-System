// Host mock of the Arduino core for testing Shell x. Not for the real board.
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <math.h>
#include <stdlib.h>
#include <stdio.h>

typedef uint8_t byte;
typedef bool boolean;
#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
#define DEC 10
#define A0 14
#define A1 15
#define A2 16
#define A3 17
#define A4 18
#define A5 19

class __FlashStringHelper;
#define F(s) (reinterpret_cast<const __FlashStringHelper*>(s))

uint32_t micros();
uint32_t millis();
void delay(uint32_t ms);
void delayMicroseconds(uint32_t us);
void pinMode(uint8_t pin, uint8_t mode);
void digitalWrite(uint8_t pin, uint8_t level);
int digitalRead(uint8_t pin);
int analogRead(uint8_t pin);

class Print {
public:
  virtual ~Print() {}
  virtual size_t write(uint8_t b) = 0;
  virtual size_t write(const uint8_t *b, size_t n) { size_t c = 0; for (size_t i = 0; i < n; i++) c += write(b[i]); return c; }
  size_t print(const char *s) { return write((const uint8_t*)s, strlen(s)); }
  size_t print(const __FlashStringHelper *s) { return print((const char*)s); }
  size_t print(char c) { return write((uint8_t)c); }
  size_t print(unsigned char v) { return printNum((long)v); }
  size_t print(int v) { return printNum(v); }
  size_t print(unsigned int v) { return printNum((long)v); }
  size_t print(long v) { return printNum(v); }
  size_t print(unsigned long v) { char b[24]; snprintf(b, sizeof b, "%lu", v); return print(b); }
  template <typename T> size_t println(T v) { size_t n = print(v); return n + println(); }
  size_t println() { return print("\r\n"); }
private:
  size_t printNum(long v) { char b[24]; snprintf(b, sizeof b, "%ld", v); return print(b); }
};

class Stream : public Print {
public:
  virtual int available() = 0;
  virtual int read() = 0;
  virtual int peek() = 0;
};

class HardwareSerialMock : public Stream {
public:
  void begin(unsigned long) {}
  int available() override;
  int read() override;
  int peek() override;
  int availableForWrite() { return 63; }
  size_t write(uint8_t b) override;
  using Print::write;
};
extern HardwareSerialMock Serial;
