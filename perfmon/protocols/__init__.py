from perfmon.config.schema import ApiProtocol
from perfmon.protocols.base import ProtocolHandler
from perfmon.protocols.rest import RestHandler

HANDLERS: dict[ApiProtocol, ProtocolHandler] = {
    ApiProtocol.REST: RestHandler(),
}
