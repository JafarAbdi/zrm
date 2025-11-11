from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class Header(_message.Message):
    __slots__ = ()
    TIMESTAMP_NS_FIELD_NUMBER: _ClassVar[int]
    FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    timestamp_ns: int
    frame_id: str
    def __init__(self, timestamp_ns: _Optional[int] = ..., frame_id: _Optional[str] = ...) -> None: ...
