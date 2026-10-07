from connectors.core.connector import Connector
from connectors.core.connector import get_logger, ConnectorError
from .constants import LOGGER_NAME
from .operations import check_health, operations
logger = get_logger(LOGGER_NAME)


class Modbus(Connector):

    def execute(self, config, operation, params, *args, **kwargs):
        operation = operations.get(operation)
        logger.info("Modbus Operation: {}".format(operation))
        return operation(config, params)

    def check_health(self, config=None, *args, **kwargs):
        pass

