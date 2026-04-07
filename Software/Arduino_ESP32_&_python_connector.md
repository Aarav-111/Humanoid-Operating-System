To connect the Operating system to an Arduino, we use a library called PySerial (Installation: pip install pyserial), this uses USB communication.
We have two codes, one for arduino (C++) and the other one is python.

C++ Arduino code / ESP32 code (hardware_connector_universal):

Find on Humanoid-operating-system/connectors/Hardware_connector_universal


Python code (K3D.py):

Find on Humanoid-operating-system/connectors/Pycode_(appropriate version)


---------------------
**Arduino Code**
The Arduino code is universal for all version of the HOS operating system while the Python Code changes for each version.

------

**Connecting with ESP32**

To connect with ESP32, use the Same Code as the Arduino. Set up the USB as how we do it normally with ESP32 and upload the same code on the corresponding board & port.
