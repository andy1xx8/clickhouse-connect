import uuid
import decimal
import pytz

from typing import Any, Union
from datetime import date, datetime, timezone, timedelta
from struct import unpack_from as suf, pack as sp

from clickhouse_connect.driver.rowbinary import read_leb128, to_leb128
from clickhouse_connect.datatypes.registry import ClickHouseType, TypeDef


class Int8(ClickHouseType):
    @staticmethod
    def _from_row_binary(source: bytes, loc: int):
        x = source[loc]
        return x if x < 128 else x - 128, loc + 1

    @staticmethod
    def _to_row_binary(value: int, dest: bytearray):
        if value < 128:
            dest.append(value)
        else:
            dest.append(value + 128)


class UInt8(ClickHouseType):
    @staticmethod
    def _from_row_binary(source: bytes, loc: int):
        return source[loc], loc + 1

    @staticmethod
    def _to_row_binary(value:int, dest: bytearray):
        dest.append(value)


class Int16(ClickHouseType):
    @staticmethod
    def _from_row_binary(source: bytes, loc:int):
        return suf('<h', source, loc)[0], loc + 2

    @staticmethod
    def _to_row_binary(value: int, dest: bytearray):
        dest += sp('<h', value,)


class UInt16(ClickHouseType):
    @staticmethod
    def _from_row_binary(source: bytes, loc: int):
        return suf('<H', source, loc)[0], loc + 2

    @staticmethod
    def _to_row_binary(value: int, dest: bytearray):
        dest += sp('<H', value,)


class Int32(ClickHouseType):
    @staticmethod
    def _from_row_binary(source: bytes, loc: int):
        return suf('<l', source, loc)[0], loc + 4

    @staticmethod
    def _to_row_binary(value: int, dest: bytearray):
        dest += sp('<l', value,)


class UInt32(ClickHouseType):
    @staticmethod
    def _from_row_binary(source: bytes, loc: int):
        return suf('<L', source, loc)[0], loc + 4

    @staticmethod
    def _to_row_binary(value: int, dest: bytearray):
        dest += sp('<L', value,)


class Int64(ClickHouseType):
    @staticmethod
    def _from_row_binary(source: bytes, loc: int):
        return suf('<q', source, loc)[0], loc + 8

    @staticmethod
    def _to_row_binary(value: int, dest: bytearray):
        dest += sp('<q', value,)


def int64_signed(source: bytes, loc: int):
    return suf('<q', source, loc)[0], loc + 8


def int64_unsigned(source: bytes, loc: int):
    return suf('<Q', source, loc)[0], loc + 8


class UInt64(ClickHouseType):
    _from_row_binary = staticmethod(int64_unsigned)

    @staticmethod
    def _to_row_binary(value: int, dest: bytearray):
        dest += sp('<Q', value,)


class Float32(ClickHouseType):
    @staticmethod
    def _from_row_binary(source: bytearray, loc: int):
        return suf('f', source, loc)[0], loc + 4

    @staticmethod
    def _to_row_binary(value: float, dest: bytearray):
        dest += sp('f', value,)


class Float64(ClickHouseType):
    @staticmethod
    def _from_row_binary(source: bytearray, loc: int):
        return suf('d', source, loc)[0], loc + 8

    @staticmethod
    def _to_row_binary(value: float, dest: bytearray):
        dest += sp('d', (value,))


from_ts_naive = datetime.utcfromtimestamp
from_ts_tz = datetime.fromtimestamp


class DateTime(ClickHouseType):
    __slots__ = '_from_row_binary',

    def __init__(self, type_def: TypeDef):
        if type_def.values:
            tzinfo = pytz.timezone(type_def.values[0][1:-1])
            self._from_row_binary = lambda source, loc: (from_ts_tz(suf('<L', source, loc)[0], tzinfo), loc + 4)
        else:
            self._from_row_binary = lambda source, loc: (from_ts_naive(suf('<L', source, loc)[0]), loc + 4)
        super().__init__(type_def)

    @staticmethod
    def _to_row_binary(value: datetime, dest: bytearray):
        dest += sp('<L', int(value.timestamp()),)


epoch_start_date = date(1970, 1, 1)


class Date(ClickHouseType):
    @staticmethod
    def _from_row_binary(source: bytes, loc: int):
        return epoch_start_date + timedelta(suf('<H', source, loc)[0]), loc + 2

    @staticmethod
    def _to_row_binary(value: date, dest: bytearray):
        dest += sp('<H', (value - epoch_start_date).days,)


class Date32(ClickHouseType):
    @staticmethod
    def _from_row_binary(source, loc):
        return epoch_start_date + timedelta(suf('<L', source, loc)[0]), loc + 4

    @staticmethod
    def _to_row_binary(self, value: date) -> bytes:
        return (value - epoch_start_date).days.to_bytes(4, 'little', signed=True)


class DateTime64(ClickHouseType):
    __slots__ = 'prec', 'tzinfo'

    def __init__(self, type_def: TypeDef):
        super().__init__(type_def)
        self.name_suffix = type_def.arg_str
        self.prec = 10 ** type_def.values[0]
        if len(type_def.values) > 1:
            self.tzinfo = pytz.timezone(type_def.values[1][1:-1])
        else:
            self.tzinfo = timezone.utc

    def _from_row_binary(self, source, loc):
        ticks = int.from_bytes(source[loc:loc + 8], 'little', signed=True)
        seconds = ticks // self.prec
        dt_sec = datetime.fromtimestamp(seconds, self.tzinfo)
        microseconds = ((ticks - seconds * self.prec) * 1000000) // self.prec
        return dt_sec + timedelta(microseconds=microseconds), loc + 8

    def _to_row_binary(self, value: datetime, dest: bytearray):
        microseconds = int(value.timestamp()) * 1000000 + value.microsecond
        dest += (int(microseconds * 1000000) // self.prec).to_bytes(8, 'little', signed=True)


class String(ClickHouseType):
    _encoding = 'utf8'

    def _from_row_binary(self, source, loc):
        length, loc = read_leb128(source, loc)
        return str(source[loc:loc + length], self._encoding), loc + length

    def _to_row_binary(self, value: str, dest: bytearray):
        value = bytes(value, self._encoding)
        dest += to_leb128(len(value)) + value


class UUID(ClickHouseType):
    @staticmethod
    def _from_row_binary(source: bytearray, loc: int):
        int_high = int.from_bytes(source[loc:loc + 8], 'little')
        int_low = int.from_bytes(source[loc + 8:loc + 16], 'little')
        byte_value = int_high.to_bytes(8, 'big') + int_low.to_bytes(8, 'big')
        return uuid.UUID(bytes=byte_value), loc + 16

    @staticmethod
    def _to_row_binary(value: uuid.UUID, dest: bytearray):
        source = value.bytes
        bytes_high, bytes_low = bytearray(source[:8]), bytearray(source[8:])
        bytes_high.reverse()
        bytes_low.reverse()
        dest += bytes_high + bytes_low


class Boolean(ClickHouseType):
    @staticmethod
    def _from_row_binary(source: bytearray, loc: int):
        return source[loc] > 0, loc + 1

    @staticmethod
    def _to_row_binary(value: bool, dest: bytearray):
        dest += b'\x01' if value else b'\x00'


class Bool(Boolean):
    pass


class Enum8(ClickHouseType):
    __slots__ = '_name_map', '_int_map'

    def __init__(self, type_def: TypeDef):
        super().__init__(type_def)
        escaped_keys = [key.replace("'", "\\'") for key in type_def.keys]
        self._name_map = {key: value for key, value in zip(type_def.keys, type_def.values)}
        self._int_map = {value: key for key, value in zip(type_def.keys, type_def.values)}
        val_str = ', '.join(f"'{key}' = {value}" for key, value in zip(escaped_keys, type_def.values))
        self.name_suffix = f'({val_str})'

    def _from_row_binary(self, source: bytes, loc: int):
        value = source[loc]
        return self._int_map[value if value < 128 else value - 128], loc + 1

    def _to_row_binary(self, value: Union[str, int], dest: bytearray):
        try:
            value = self._name_map[value]
        except KeyError:
            pass
        dest += value if value < 128 else value - 128


class Enum16(Enum8):
    def _from_row_binary(self, source: bytes, loc: int):
        return self._int_map[suf('<h', source, loc)[0]], loc + 2

    def _to_row_binary(self, value: Union[str, int], dest: bytearray):
        try:
            value = self._name_map[value]
        except KeyError:
            pass
        dest += sp('<h', value)


class Decimal(ClickHouseType):
    __slots__ = 'size', 'prec', 'zeros', 'mult'

    def __init__(self, type_def: TypeDef):
        super().__init__(type_def)
        size = type_def.size
        if size == 0:
            self.name_suffix = type_def.arg_str
            prec = type_def.values[0]
            self.prec = type_def.values[1]
            if prec < 1 or prec > 79:
                raise ArithmeticError(f"Invalid precision {prec} for ClickHouse Decimal type")
            if prec < 10:
                size = 32
            elif prec < 19:
                size = 64
            elif prec < 39:
                size = 128
            else:
                size = 256
        else:
            self.prec = type_def.values[0]
            self.name_suffix = f'{type_def.size}({self.prec})'
        self.size = size // 8
        self.mult = 10 ** self.prec
        self.zeros = bytes([0] * self.size)

    def _from_row_binary(self, source, loc):
        neg = ''
        unscaled = int.from_bytes(source[loc:loc + self.size], 'little')
        if unscaled <= 0:
            neg = '-'
            unscaled = -unscaled
        digits = str(unscaled)
        return decimal.Decimal(f'{neg}{digits[:-self.prec]}.{digits[-self.prec:]}'), loc + self.size

    def _to_row_binary(self, value: Any) -> bytes:
        if isinstance(value, int) or isinstance(value, float) or (
                isinstance(value, decimal.Decimal) and value.is_finite()):
            return int(value * self.mult).to_bytes(self.size, 'little')
        return self.zeros