import pyvisa
import time
import serial
import json
import pandas as pd
import datetime
import os

rm=None
try:
    rm = pyvisa.ResourceManager()
except Exception as e:
    print(e)

EMPTY = (0,0)

def Serial_Connection():
    ser = None
    try:
        ser = serial.Serial("COM3", 9600)
        serial_status = True

    except(Exception, serial.SerialException) as error:
        serial_status = None
        print("Serial Connection")
        print(str(error).split(":")[0])

    return serial_status,ser

def Load_Connection():
    rmt_load = load_status = None
    # Query if rmt_load instrument is present
    if rm:
        try:
            rmt_load = rm.open_resource("RIGOL_DC_ELoad")  ####  TCPIP0::192.168.178.112::rmt_loadR
            print(rmt_load.query("*IDN?"))
            load_status = True
        except(Exception, pyvisa.errors.Error) as error:
            load_status = False
            print("Load Connection")
            print("Error-Code:", error.error_code)
            print("Error-Abbreviation:", error.abbreviation)
            print("Error-Description:", error.description)
    return load_status,rmt_load

def RPS_Connection():
    rmt_rps= rps_status = None
    if rm:
        try:
            rmt_rps = rm.open_resource("LRPS")
            print(rmt_rps.query("*IDN?"))
            rps_status = True
        except(Exception, pyvisa.errors.Error) as error:
            rps_status = False
            print("RPS Connection")
            print("Error-Code:", error.error_code)
            print("Error-Abbreviation:", error.abbreviation)
            print("Error-Description:", error.description)
    return rps_status , rmt_rps

def Initialise_Parameters(rmt_rps, rmt_load, INVolt):
    rmt_rps.write("*RST")  # Resets to Default Values
    time.sleep(1)

    rmt_load.write("*RST")  # Resets to Default Values
    time.sleep(1)

    rmt_rps.write(f''':VOLT {INVolt}''')  # Sets Voltage Level of RPS
    time.sleep(.1)

    rmt_rps.write(f''':CURR 5''')  # Sets Current Level of RPS
    time.sleep(.1)

    rmt_rps.write(":OUTP:STAT CH1,ON")  # Enable RPS
    time.sleep(.1)

    rmt_load.write(":SOUR:LIST:MODE CC")  # Sets To Constant Current Mode
    time.sleep(.1)

    print("Mode: ", rmt_load.query(":SOURCE:LIST:MODE?").strip())
    time.sleep(1)

    rmt_load.write(f''':SOUR:CURR:VON {INVolt}''')  # Sets VOn to 24V
    time.sleep(.1)

    rmt_load.write(":SOUR:CURR:RANG 40")  # Sets Curret Range to 4A or 40A
    time.sleep(.1)

    rmt_load.write(":SOURCE:INPUT:STATE On")  # Enable electronic load
    time.sleep(.1)

def Read(rmt_load, ser):
    load_list = []
    recv_list = []
    cur = 0
    maxLoad = 5
    tolerance = 0.2
    while cur <= (maxLoad + tolerance):
        load_Current = round(cur, 2)
        rmt_load.write(f''':SOUR:CURR:LEV:IMM {load_Current}''')  # sets Load Current
        # Wait for value to stabilize
        # Measure!
        print("Current Load:", load_Current)
        time.sleep(.2)
        try:
            ser.flushInput()
            bs = ser.readline()  # Serial port Reading
            decod = (bs).decode('utf-8')  # Response decoding
            js = json.loads(decod.rstrip())  # converting into json
            recv = js["current"]
            print("recv:", recv)
        except:
            rmt_load.write(f''':SOUR:CURR:LEV:IMM {load_Current}''')  # sets Load Current
            time.sleep(1)

            ser.flushInput()
            bs = ser.readline()  # Serial port Reading
            decod = (bs).decode('utf-8')  # Response decoding
            js = json.loads(decod.rstrip())  # converting into json
            recv = js["current"]
            print("recv:", recv)

        load_list.append(load_Current)
        recv_list.append(recv)

        # print("Voltage: ", rmt_load.query(":MEASURE:VOLTAGE?").strip())
        # print("Current: ", rmt_load.query(":MEASURE:CURRENT?").strip())
        # print("Power: ", rmt_load.query(":MEASURE:POWER?").strip())

        cur += tolerance

    return load_list, recv_list

def Save(pd_data):
    current_time = datetime.datetime.now().strftime("%d_%m_%y_%H_%M_%S")

    path = f'''{os.getcwd()}/ELOAD_Reports'''
    isdir = os.path.isdir(path)
    if isdir == False:
        os.mkdir(path)
    else:
        pass

    pd_data.to_csv(f'''{path}/Test_{current_time}.csv''')

def main():
    pd_data = pd.DataFrame()
    csv = pd.read_csv("Sample_Rates.csv")
    Input_Cases = [Val for Val in csv["input_voltage"]]
    sample_rates = [rates for rates in csv["samples"]]

    serial_status,ser = Serial_Connection()
    rps_status, rmt_rps = RPS_Connection()
    load_status,rmt_load = Load_Connection()

    if serial_status == True and load_status == True and rps_status == True:
        if ser is not None and rmt_load is not None and rmt_rps is not None:
            for i in range(len(Input_Cases)):
                INVolt, sample_rate = Input_Cases[i], sample_rates[i]
                print("*" * 10, "Voltage", INVolt, "*" * 10)

                time.sleep(2)
                loadlist = []
                recvlist = []

                Initialise_Parameters(rmt_rps, rmt_load, INVolt)

                # Write to Pandas Data Frame
                for _ in range(sample_rate):
                    print("*" * 10, "Sample", _ + 1, "*" * 10)
                    load, Vo = Read(rmt_load, ser)
                    loadlist.append(load)
                    recvlist.append(Vo)

                loadlist = loadlist[0]
                pd_data = pd_data.assign(Load=loadlist)

                for i in range(sample_rate):
                    header = f'''Vo_{INVolt}V_{i + 1}'''
                    new_data = {header: recvlist[i]}
                    pd_data = pd_data.assign(**new_data)

                print(pd_data)

        if serial_status == False:
            print("Cannot Connect to Serial Port")
        if load_status == False:
            print("Cannot Connect to RIGOL_DC_ELoad")
        if rps_status == False:
            print("Cannot Connect to RIGOL_RPS")

    if pd_data.shape != EMPTY:
        Save(pd_data)

    if serial_status == True:
        ser.close()

    if load_status == True:
        load_resp = int(rmt_load.query(":SOUR:INP:STAT?"))
        if load_resp == 1:
            rmt_load.write(":SOURCE:INPUT:STATE Off")
            time.sleep(1)

    if rps_status == True:
        rps_resp = rmt_rps.query(":OUTPut:STATe? CH1").strip()
        if rps_resp == "ON":
            rmt_rps.write(":OUTP:STAT CH1,OFF")
            time.sleep(1)

if __name__ == "__main__":
    main()