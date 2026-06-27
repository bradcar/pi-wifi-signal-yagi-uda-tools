import os
import re 
import time
import socket


class Gain_Param():
    Get_back = [0,0,0,0,0] # Returns the memory of Disk     
    flag = 0 # Unmounted or unpartitioned   
    def GET_IP(self):
        #There will be exceptions, get stuck, get it carefully
        #Threading is better
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        s.connect_ex(('8.8.8.8',80))
        ip=s.getsockname()[0]
        s.close()
        return ip


    def GET_Temp(self):
        with open('/sys/class/thermal/thermal_zone0/temp', 'rt') as f:
            temp = (int)(f.read() ) / 1000.0
        return temp

    

                  
