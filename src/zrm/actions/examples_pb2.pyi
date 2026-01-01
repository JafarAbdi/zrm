from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class Fibonacci(_message.Message):
    __slots__ = ()
    class Goal(_message.Message):
        __slots__ = ()
        ORDER_FIELD_NUMBER: _ClassVar[int]
        order: int
        def __init__(self, order: _Optional[int] = ...) -> None: ...
    class Result(_message.Message):
        __slots__ = ()
        SEQUENCE_FIELD_NUMBER: _ClassVar[int]
        sequence: _containers.RepeatedScalarFieldContainer[int]
        def __init__(self, sequence: _Optional[_Iterable[int]] = ...) -> None: ...
    class Feedback(_message.Message):
        __slots__ = ()
        PARTIAL_SEQUENCE_FIELD_NUMBER: _ClassVar[int]
        partial_sequence: _containers.RepeatedScalarFieldContainer[int]
        def __init__(self, partial_sequence: _Optional[_Iterable[int]] = ...) -> None: ...
    def __init__(self) -> None: ...
