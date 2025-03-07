#####################################
### Ecostab Sensors to Robonomics ###
#####################################

# Read data from Ecostab sensors and send to Robonomics sensors map

### Using nodes:
# ecostab_sensors_publisher -> 
#           publish data to /airaflot/ecostab_sensors/data
# ecostab_to_robonomisc -> 
#           collect data from sensors (/airaflot/ecostab_sensors/data), 
#           gps (mavros) and timestamp and publish to /airaflot/data_to_send
# file_saver (if USE_FILE_SAVER_WITH_IPFS is True) -> 
#           read /airaflot/data_to_send and write data to files. 
#           On every new file publish the name of the finished file in /airaflot/file_saver/file_finished
# robonomics -> 
#           if USE_FILE_SAVER_WITH_IPFS is True, listen to /airaflot/file_saver/file_finished
#           and on new file add it to pinata and create datalog with ipfs hash.
#           if USE_FILE_SAVER_WITH_IPFS is False, listen to /airaflot/data_to_send
#           and create datalog with every message

USE_FILE_SAVER_WITH_IPFS = True    # Send the batch of data in datalog using IPFS (True) 
                                   # or create datalog on every new message in /airaflot/data_to_send (False)

EMULATE_ECOSTAB_SENSORS = False     # Use emulator instead of real sensors for testing

NEW_DATA_INTERVAL = 5              # secons, How often to send data to /airaflot/data_to_send in ecostab_to_robonomisc node