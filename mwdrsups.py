#!/usr/bin/env python3
"""
    Mean Well DRS-240/480-series DC-UPS
    ModBus to MQTT poller
"""
import os
import sys
import logging
from time import sleep,time
import pymodbus.client as ModbusClient
from pymodbus import ModbusException
from pymodbus import Framer
import paho.mqtt.client as mqtt


# settings
SLAVE_ID = 0x83
POLL_INTERVAL = 5
REPORT_INTERVAL = 600
SERIAL_PORT = '/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0'
SERIAL_BAUD = 115200
REPORT_HYSTERESIS = 10
MQTT_TOPIC = '/sensor/mw-drs'
VOLTAGE_VOUT_LOW = 2500
VOLTAGE_VOUT_CRITICAL = 2350
VOLTAGE_VOUT_LOW_ACTION = 'echo "System is running on battery backup power"|wall'
VOLTAGE_VOUT_CRITICAL_ACTION = '/sbin/shutdown -P now'
CONF_VOUT_SET = 2722
CONF_CURVE_CC = 100
CONF_CURVE_VFLOAT = 2722


# logger
logging.basicConfig(level=logging.INFO, format="%(levelname)-6s %(message)s")
log = logging.getLogger(__name__)

# create mqtt client
mqc = mqtt.Client()
mqc.connect("mqtt", 1883, 60)

# modbus client
mb = ModbusClient.ModbusSerialClient(
    SERIAL_PORT,
    framer=Framer.RTU,
    timeout=2,
    baudrate=SERIAL_BAUD,
    bytesize=8,
    parity="N",
    stopbits=1,
)


# threshold/hysteresis function
def threshold_check(value_last, value_current):
    if (value_current + REPORT_HYSTERESIS) < value_last:
        log.debug('value is higher (value_current > value_last)')
        return True
    if (value_current - REPORT_HYSTERESIS) > value_last:
        log.debug('value is lower (value_current < value_last)')
        return True
    log.debug('value is unchanged')
    return False


# init values
report_last = 0
value_change = False
value_vin_raw = 0
value_vout_raw = 0
value_iout_raw = 0
value_vbat_raw = 0
value_ibat_raw = 0
value_tint_raw = 0
value_tbat_raw = 0
action_low_done = False
action_critical_done = False


# begin
mb.connect()
log.info('connected to %s at %d baud', SERIAL_PORT, SERIAL_BAUD)
log.info('poll interval is %d seconds', POLL_INTERVAL)
log.info('minimum report interval is %d seconds', REPORT_INTERVAL)
log.info('VOLTAGE_VOUT_LOW is configured to %.02fV', VOLTAGE_VOUT_LOW/100)
log.info('VOLTAGE_VOUT_CRITICAL is configured to %.02fV', VOLTAGE_VOUT_CRITICAL/100)


# voltage adjust
if CONF_VOUT_SET:
    log.info('VOUT_SET (0x20) set to %d', CONF_VOUT_SET)
    rr = mb.write_register(0x20, CONF_VOUT_SET, slave=SLAVE_ID)
    if rr.isError():
        log.error(f"Received exception from device ({rr}). unable to configure VOUT_SET")
        sys.exit(1)

    log.info('CURVE_CC (0xB0) set to %d', CONF_CURVE_CC)
    rr = mb.write_register(0xB0, CONF_CURVE_CC, slave=SLAVE_ID)
    if rr.isError():
        log.error(f"Received exception from device ({rr}). unable to configure CURVE_CC")
        sys.exit(1)

    log.info('CURVE_VFLOAT (0xB2) set to %d', CONF_CURVE_VFLOAT)
    rr = mb.write_register(0xB2, CONF_CURVE_VFLOAT, slave=SLAVE_ID)
    if rr.isError():
        log.error(f"Received exception from device ({rr}). unable to configure CURVE_VFLOAT")
        sys.exit(1)


# main loop
while True:
    try:
        # read registers
        rr_vin = mb.read_input_registers(0x50, count=1, slave=SLAVE_ID)    # AC voltage
        rr_vout = mb.read_input_registers(0x60, count=1, slave=SLAVE_ID)   # DC output voltage
        rr_iout = mb.read_input_registers(0x61, count=1, slave=SLAVE_ID)   # DC current output
        rr_vbat = mb.read_input_registers(0xD3, count=1, slave=SLAVE_ID)   # DC battery voltage
        rr_ibat = mb.read_input_registers(0xD4, count=1, slave=SLAVE_ID)   # DC battery current
        rr_tint = mb.read_input_registers(0x62, count=1, slave=SLAVE_ID)   # Internal temperature
        rr_tbat = mb.read_input_registers(0xD5, count=1, slave=SLAVE_ID)   # Battery temperature

    except ModbusException as exc:
        log.critical(f"Received ModbusException({exc}) from library")
        mb.close()
        sys.exit(1)

    if rr_vin.isError():
        log.error(f"Received exception from device ({rr_vin})")
        continue

    # store previous values
    value_vin_raw_last = value_vin_raw
    value_vout_raw_last = value_vout_raw
    value_iout_raw_last = value_iout_raw
    value_vbat_raw_last = value_vbat_raw
    value_ibat_raw_last = value_ibat_raw

    # process values
    value_vin_raw = mb.convert_from_registers(rr_vin.registers, data_type=mb.DATATYPE.INT16)
    value_vout_raw = mb.convert_from_registers(rr_vout.registers, data_type=mb.DATATYPE.INT16)
    value_iout_raw = mb.convert_from_registers(rr_iout.registers, data_type=mb.DATATYPE.INT16)
    value_vbat_raw = mb.convert_from_registers(rr_vbat.registers, data_type=mb.DATATYPE.INT16)
    value_ibat_raw = mb.convert_from_registers(rr_ibat.registers, data_type=mb.DATATYPE.INT16)
    value_tint_raw = mb.convert_from_registers(rr_tint.registers, data_type=mb.DATATYPE.INT16)
    value_tbat_raw = mb.convert_from_registers(rr_tbat.registers, data_type=mb.DATATYPE.INT16)
    value_pout = (value_vout_raw * value_iout_raw)/10000

    # publish changes
    if threshold_check(value_vout_raw_last, value_vout_raw):
        mqc.publish('%s/vout/volt' % MQTT_TOPIC, value_vout_raw/100)
        mqc.publish('%s/pout/watt' % MQTT_TOPIC, value_pout)
        value_change = True

    if threshold_check(value_iout_raw_last, value_iout_raw):
        mqc.publish('%s/iout/ampere' % MQTT_TOPIC, value_iout_raw/100)
        mqc.publish('%s/pout/watt' % MQTT_TOPIC, value_pout)
        value_change = True

    if threshold_check(value_vbat_raw_last, value_vbat_raw):
        mqc.publish('%s/vbat/volt' % MQTT_TOPIC, value_vbat_raw/100)
        value_change = True

    if threshold_check(value_ibat_raw_last, value_ibat_raw):
        mqc.publish('%s/ibat/ampere' % MQTT_TOPIC, value_ibat_raw/100)
        value_change = True

    # regular report
    if (report_last + REPORT_INTERVAL) < time():
        log.info('REPORT_INTERVAL reached, performing full report')
        log.info('report vin=%dV vout=%.02fV iout=%.02fA vbat=%.02fV ibat=%.02fA pout=%dW tint=%.02fC tbat=%.02fC' %
            (value_vin_raw/10, value_vout_raw/100, value_iout_raw/100, value_vbat_raw/100, value_ibat_raw/100,
             value_pout, value_tint_raw/10, value_tbat_raw/10))

    # publish to mqtt
        mqc.publish('%s/vin/volt' % MQTT_TOPIC, value_vin_raw/10)
        mqc.publish('%s/vout/volt' % MQTT_TOPIC, value_vout_raw/100)
        mqc.publish('%s/iout/ampere' % MQTT_TOPIC, value_iout_raw/100)
        mqc.publish('%s/vbat/volt' % MQTT_TOPIC, value_vbat_raw/100)
        mqc.publish('%s/ibat/ampere' % MQTT_TOPIC, value_ibat_raw/100)
        mqc.publish('%s/tint/temp' % MQTT_TOPIC, value_tint_raw/10)
        mqc.publish('%s/tbat/temp' % MQTT_TOPIC, value_tbat_raw/10)
        mqc.publish('%s/pout/watt' % MQTT_TOPIC, value_pout)
        report_last = time()

    # perform action on low voltage
    if VOLTAGE_VOUT_LOW > value_vout_raw and action_low_done is False:
        log.warning('VOUT level is below VOLTAGE_VOUT_LOW, performing actions')
        os.system(VOLTAGE_VOUT_LOW_ACTION)
        action_low_done = True

    # perform action on critical voltage
    if VOLTAGE_VOUT_CRITICAL > value_vout_raw and action_critical_done is False:
        log.warning('VOUT level is below VOLTAGE_VOUT_CRITICAL, performing actions')
        os.system(VOLTAGE_VOUT_CRITICAL_ACTION)
        action_critical_done = True

    # sleep
    mqc.loop()
    log.debug('sleep')
    sleep(POLL_INTERVAL)


# end
mb.close()
mqc.close()
log.info("connection closed")





