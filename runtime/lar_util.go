import (
    "unsafe"
)

type lar_type_bool bool
type lar_type_schar int8
type lar_type_char uint8
type lar_type_short int16
type lar_type_ushort uint16
type lar_type_int int32
type lar_type_uint uint32
type lar_type_long int64
type lar_type_ulong uint64
type lar_type_float float32
type lar_type_double float64

type lar_util_intf_stru struct {
    tab unsafe.Pointer
    data unsafe.Pointer
}

func lar_util_is_same_intf(a, b interface{}) bool {
    return ((*lar_util_intf_stru)(unsafe.Pointer(&a))).data == ((*lar_util_intf_stru)(unsafe.Pointer(&b))).data
}