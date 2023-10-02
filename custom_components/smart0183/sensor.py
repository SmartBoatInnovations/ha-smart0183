import asyncio
import logging
import serial_asyncio
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from serial import SerialException
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import CONF_NAME, CONF_VALUE_TEMPLATE, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.entity import Entity
from datetime import datetime, timedelta


# Setting up logging and configuring constants and default values

_LOGGER = logging.getLogger(__name__)

CONF_SERIAL_PORT = "serial_port"
CONF_BAUDRATE = "baudrate"
CONF_BYTESIZE = "bytesize"
CONF_PARITY = "parity"
CONF_STOPBITS = "stopbits"
CONF_XONXOFF = "xonxoff"
CONF_RTSCTS = "rtscts"
CONF_DSRDTR = "dsrdtr"

DEFAULT_NAME = "Serial Sensor"
DEFAULT_BAUDRATE = 4800
DEFAULT_BYTESIZE = serial_asyncio.serial.EIGHTBITS
DEFAULT_PARITY = serial_asyncio.serial.PARITY_NONE
DEFAULT_STOPBITS = serial_asyncio.serial.STOPBITS_ONE
DEFAULT_XONXOFF = False
DEFAULT_RTSCTS = False
DEFAULT_DSRDTR = False

# Extending the schema to include configurations for the serial connection

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_SERIAL_PORT): cv.string,
        vol.Optional(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): cv.positive_int,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
        vol.Optional(CONF_BYTESIZE, default=DEFAULT_BYTESIZE): vol.In(
            [
                serial_asyncio.serial.FIVEBITS,
                serial_asyncio.serial.SIXBITS,
                serial_asyncio.serial.SEVENBITS,
                serial_asyncio.serial.EIGHTBITS,
            ]
        ),
        vol.Optional(CONF_PARITY, default=DEFAULT_PARITY): vol.In(
            [
                serial_asyncio.serial.PARITY_NONE,
                serial_asyncio.serial.PARITY_EVEN,
                serial_asyncio.serial.PARITY_ODD,
                serial_asyncio.serial.PARITY_MARK,
                serial_asyncio.serial.PARITY_SPACE,
            ]
        ),
        vol.Optional(CONF_STOPBITS, default=DEFAULT_STOPBITS): vol.In(
            [
                serial_asyncio.serial.STOPBITS_ONE,
                serial_asyncio.serial.STOPBITS_ONE_POINT_FIVE,
                serial_asyncio.serial.STOPBITS_TWO,
            ]
        ),
        vol.Optional(CONF_XONXOFF, default=DEFAULT_XONXOFF): cv.boolean,
        vol.Optional(CONF_RTSCTS, default=DEFAULT_RTSCTS): cv.boolean,
        vol.Optional(CONF_DSRDTR, default=DEFAULT_DSRDTR): cv.boolean,
    }
)


async def update_sensor_availability(hass):
    """Update the availability of all sensors every 5 minutes."""
    while True:
        _LOGGER.debug("Running update_sensor_availability")
        await asyncio.sleep(300)  # wait for 5 minutes

        for sensor in hass.data["created_sensors"].values():
            sensor.update_availability()


# The main setup function to initialize the sensor platform

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Serial sensor platform."""
    name = config.get(CONF_NAME)
    port = config.get(CONF_SERIAL_PORT)
    baudrate = config.get(CONF_BAUDRATE)
    bytesize = config.get(CONF_BYTESIZE)
    parity = config.get(CONF_PARITY)
    stopbits = config.get(CONF_STOPBITS)
    xonxoff = config.get(CONF_XONXOFF)
    rtscts = config.get(CONF_RTSCTS)
    dsrdtr = config.get(CONF_DSRDTR)

    if (value_template := config.get(CONF_VALUE_TEMPLATE)) is not None:
        value_template.hass = hass

    _LOGGER.debug("Setting up platform.")
    # Save a reference to the add_entities callback

    _LOGGER.debug("Assigning async_add_entities to hass.data.")

    hass.data["add_serial_sensors"] = async_add_entities

    _LOGGER.debug("Assigned successfully.")

    # Initialize a dictionary to store references to the created sensors
    hass.data["created_sensors"] = {}


    sensor = SerialSensor(
        name,
        port,
        baudrate,
        bytesize,
        parity,
        stopbits,
        xonxoff,
        rtscts,
        dsrdtr,
        value_template,
    )

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, sensor.stop_serial_read)
    async_add_entities([sensor], True)

    # Start the task that updates the sensor availability every 5 minutes
    hass.loop.create_task(update_sensor_availability(hass))

# SmartSensor class representing a basic sensor entity with state

class SmartSensor(Entity):
    def __init__(self, name, initial_state):
        """Initialize the sensor."""
        _LOGGER.info(f"Initializing sensor: {name} with state: {initial_state}")
        self._name = name
        self._unique_id = name
        self._state = initial_state
        self._last_updated = datetime.now()
        if initial_state is None or initial_state == "":
            self._available = False
            _LOGGER.info(f"Setting sensor: '{self._name}' with unavailable")
        else:
            self._available = True

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name
    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def last_updated(self):
        """Return the last updated timestamp of the sensor."""
        return self._last_updated

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self._available

    @property
    def should_poll(self) -> bool:
        """Return the polling requirement for this sensor."""
        return False


    def update_availability(self):
        """Update the availability status of the sensor."""

        new_availability = (datetime.now() - self._last_updated) < timedelta(minutes=4)

        if new_availability:
            _LOGGER.debug(f"Sensor '{self._name}' is being set to available at {datetime.now()}")
        else:
            _LOGGER.debug(f"Sensor '{self._name}' is being set to unavailable at {datetime.now()}")

        self._available = new_availability

        try:
            self.async_schedule_update_ha_state()
        except RuntimeError as re:
            if "Attribute hass is None" in str(re):
                pass  # Ignore this specific error
            else:
                _LOGGER.warning(f"Could not update state for sensor '{self._name}': {re}")
        except Exception as e:  # Catch all other exception types
            _LOGGER.warning(f"Could not update state for sensor '{self._name}': {e}")

    def set_state(self, new_state):
        """Set the state of the sensor."""
        _LOGGER.debug(f"Setting state for sensor: '{self._name}' to {new_state}")
        self._state = new_state
        if new_state is None or new_state == "":
            self._available = False
            _LOGGER.debug(f"Setting sensor:'{self._name}' with unavailable")
        else:
            self._available = True
        self._last_updated = datetime.now()

        try:
            self.async_schedule_update_ha_state()
        except RuntimeError as re:
            if "Attribute hass is None" in str(re):
                pass  # Ignore this specific error
            else:
                _LOGGER.warning(f"Could not update state for sensor '{self._name}': {re}")
        except Exception as e:  # Catch all other exception types
            _LOGGER.warning(f"Could not update state for sensor '{self._name}': {e}")

# SerialSensor class representing a sensor entity interacting with a serial device

class SerialSensor(SensorEntity):
    """Representation of a Serial sensor."""

    _attr_should_poll = False

    def __init__(
        self,
        name,
        port,
        baudrate,
        bytesize,
        parity,
        stopbits,
        xonxoff,
        rtscts,
        dsrdtr,
        value_template,
    ):
        """Initialize the Serial sensor."""
        self._name = name
        self._state = None
        self._port = port
        self._baudrate = baudrate
        self._bytesize = bytesize
        self._parity = parity
        self._stopbits = stopbits
        self._xonxoff = xonxoff
        self._rtscts = rtscts
        self._dsrdtr = dsrdtr
        self._serial_loop_task = None
        self._template = value_template
        self._attributes = None

    async def async_added_to_hass(self) -> None:
        """Handle when an entity is about to be added to Home Assistant."""
        self._serial_loop_task = self.hass.loop.create_task(
            self.serial_read(
                self._port,
                self._baudrate,
                self._bytesize,
                self._parity,
                self._stopbits,
                self._xonxoff,
                self._rtscts,
                self._dsrdtr,
            )
        )



    async def set_smart_sensors(self, line):
        """Process the content of the line related to the smart sensors."""
        try:

            if not line or not line.startswith("$"):  
                return

            # Splitting by comma and getting the data fields
            fields = line.split(',')
            if len(fields) < 1 or len(fields[0]) < 6:  # Ensure enough fields and length
                _LOGGER.error(f"Malformed line: {line}")
                return

            # Splitting by comma and getting the data fields
            fields = line.split(',')
            sentence_id = fields[0][1:6]  # Gets the 5-char word after the $

            _LOGGER.debug(f"Checking sensor: {sentence_id}")

            # Check if main sensor exists; if not, create one
            if sentence_id not in self.hass.data["created_sensors"]:
                _LOGGER.debug(f"Creating main sensor: {sentence_id}")
                sensor = SmartSensor(sentence_id, line)

                self.hass.data["add_serial_sensors"]([sensor])
                self.hass.data["created_sensors"][sentence_id] = sensor
            else:
                # If the sensor already exists, update its state
                _LOGGER.debug(f"Updating main sensor: {sentence_id}")
                sensor = self.hass.data["created_sensors"][sentence_id]
                sensor.set_state(line)

            # Now creating or updating sensors for individual fields
            for idx, field_data in enumerate(fields[1:], 1):
                # Skip the last field since it's a check digit
                if idx == len(fields) - 1:
                    break

                sensor_name = f"{sentence_id}_{idx}"

                _LOGGER.debug(f"Checking field sensor: {sensor_name}")

                # Check if this field sensor exists; if not, create one
                if sensor_name not in self.hass.data["created_sensors"]:
                    _LOGGER.debug(f"Creating field sensor: {sensor_name}")
                    sensor = SmartSensor(sensor_name, field_data)
                    self.hass.data["add_serial_sensors"]([sensor])
                    self.hass.data["created_sensors"][sensor_name] = sensor
                else:
                    # If the sensor already exists, update its state
                    _LOGGER.debug(f"Updating field sensor: {sensor_name}")
                    sensor = self.hass.data["created_sensors"][sensor_name]
                    sensor.set_state(field_data)

            self._state = line
            self.async_write_ha_state()

        except IndexError:
            _LOGGER.error(f"Index error for line: {line}")
        except KeyError as e:
            _LOGGER.error(f"Key error: {e}")
        except Exception as e:
            _LOGGER.error(f"An unexpected error occurred: {e}")



    async def serial_read(
        self,
        device,
        baudrate,
        bytesize,
        parity,
        stopbits,
        xonxoff,
        rtscts,
        dsrdtr,
        **kwargs,
    ):
        """Read the data from the port."""
        logged_error = False
        while True:
            try:
                reader, _ = await serial_asyncio.open_serial_connection(
                    url=device,
                    baudrate=baudrate,
                    bytesize=bytesize,
                    parity=parity,
                    stopbits=stopbits,
                    xonxoff=xonxoff,
                    rtscts=rtscts,
                    dsrdtr=dsrdtr,
                    **kwargs,
                )

            except SerialException as exc:
                if not logged_error:
                    _LOGGER.exception(
                        "Unable to connect to the serial device %s: %s. Will retry",
                        device,
                        exc,
                    )
                    logged_error = True
                await self._handle_error()
            else:
                _LOGGER.info("Serial device %s connected", device)


                while True:
                    try:
                        line = await reader.readline()
                    except SerialException as exc:
                        _LOGGER.exception("Error while reading serial device %s: %s", device, exc)
                        await self._handle_error()
                        break
                    else:
                        try:
                            line = line.decode("utf-8").strip()
                        except UnicodeDecodeError as exc:
                            _LOGGER.error("Failed to decode line from UTF-8: %s", exc)
                            continue

                        # _LOGGER.debug("Received: %s", line)
                        await self.set_smart_sensors(line)




    async def _handle_error(self):
        """Handle error for serial connection."""
        self._state = None
        self._attributes = None
        self.async_write_ha_state()
        await asyncio.sleep(5)

    @callback
    def stop_serial_read(self, event):
        """Close resources."""
        if self._serial_loop_task:
            self._serial_loop_task.cancel()

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def extra_state_attributes(self):
        """Return the attributes of the entity (if any JSON present)."""
        return self._attributes

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._state
