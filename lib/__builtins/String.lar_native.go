import (
    "fmt"
    "strconv"
)

type lar_cls_10___builtins_6_String string

func lar_new_obj_lar_cls_10___builtins_6_String(arr *[]lar_type_char) *lar_cls_10___builtins_6_String {
    size := len(*arr)
    byte_arr := make([]byte, size)
    for i := 0; i < size; i ++ {
        byte_arr[i] = byte((*arr)[i])
    }
    ls := lar_cls_10___builtins_6_String(string(byte_arr))
    return &ls
}

func (this *lar_cls_10___builtins_6_String) method_size() lar_type_long {
    return lar_type_long(len(string(*this)))
}

func (this *lar_cls_10___builtins_6_String) method_char_at(idx lar_type_long) lar_type_char {
    return lar_type_char(string(*this)[idx])
}

func (this *lar_cls_10___builtins_6_String) method_cmp(other *lar_cls_10___builtins_6_String) lar_type_int {
    this_s := string(*this)
    other_s := string(*other)
    if this_s < other_s {
        return -1
    }
    if this_s > other_s {
        return 1
    }
    return 0
}

func (this *lar_cls_10___builtins_6_String) method_parse_short(base lar_type_int, n *lar_type_short) *lar_cls_10___builtins_5_Error {
    r, err := strconv.ParseInt(string(*this), int(base), 16)
    if err != nil {
        return lar_new_obj_lar_cls_10___builtins_5_Error(-1, lar_util_create_lar_str_from_go_str("parse error"))
    }
    *n = lar_type_short(r)
    return nil
}

func (this *lar_cls_10___builtins_6_String) method_parse_ushort(base lar_type_int, n *lar_type_ushort) *lar_cls_10___builtins_5_Error {
    r, err := strconv.ParseUint(string(*this), int(base), 16)
    if err != nil {
        return lar_new_obj_lar_cls_10___builtins_5_Error(-1, lar_util_create_lar_str_from_go_str("parse error"))
    }
    *n = lar_type_ushort(r)
    return nil
}

func (this *lar_cls_10___builtins_6_String) method_parse_int(base lar_type_int, n *lar_type_int) *lar_cls_10___builtins_5_Error {
    r, err := strconv.ParseInt(string(*this), int(base), 32)
    if err != nil {
        return lar_new_obj_lar_cls_10___builtins_5_Error(-1, lar_util_create_lar_str_from_go_str("parse error"))
    }
    *n = lar_type_int(r)
    return nil
}

func (this *lar_cls_10___builtins_6_String) method_parse_uint(base lar_type_int, n *lar_type_uint) *lar_cls_10___builtins_5_Error {
    r, err := strconv.ParseUint(string(*this), int(base), 32)
    if err != nil {
        return lar_new_obj_lar_cls_10___builtins_5_Error(-1, lar_util_create_lar_str_from_go_str("parse error"))
    }
    *n = lar_type_uint(r)
    return nil
}

func (this *lar_cls_10___builtins_6_String) method_parse_long(base lar_type_int, n *lar_type_long) *lar_cls_10___builtins_5_Error {
    r, err := strconv.ParseInt(string(*this), int(base), 64)
    if err != nil {
        return lar_new_obj_lar_cls_10___builtins_5_Error(-1, lar_util_create_lar_str_from_go_str("parse error"))
    }
    *n = lar_type_long(r)
    return nil
}

func (this *lar_cls_10___builtins_6_String) method_parse_ulong(base lar_type_int, n *lar_type_ulong) *lar_cls_10___builtins_5_Error {
    r, err := strconv.ParseUint(string(*this), int(base), 64)
    if err != nil {
        return lar_new_obj_lar_cls_10___builtins_5_Error(-1, lar_util_create_lar_str_from_go_str("parse error"))
    }
    *n = lar_type_ulong(r)
    return nil
}

func (this *lar_cls_10___builtins_6_String) method_parse_float(n *lar_type_float) *lar_cls_10___builtins_5_Error {
    r, err := strconv.ParseFloat(string(*this), 32)
    if err != nil {
        return lar_new_obj_lar_cls_10___builtins_5_Error(-1, lar_util_create_lar_str_from_go_str("parse error"))
    }
    *n = lar_type_float(r)
    return nil
}

func (this *lar_cls_10___builtins_6_String) method_parse_double(n *lar_type_double) *lar_cls_10___builtins_5_Error {
    r, err := strconv.ParseFloat(string(*this), 64)
    if err != nil {
        return lar_new_obj_lar_cls_10___builtins_5_Error(-1, lar_util_create_lar_str_from_go_str("parse error"))
    }
    *n = lar_type_double(r)
    return nil
}

func lar_util_create_lar_str_from_go_str(s string) *lar_cls_10___builtins_6_String {
	ls := lar_cls_10___builtins_6_String(s)
	return &ls
}

func lar_util_convert_lar_str_to_go_str(s *lar_cls_10___builtins_6_String) string {
    return string(*s)
}

func lar_str_fmt(format string, a ...interface{}) *lar_cls_10___builtins_6_String {
    for i, v := range a {
        s, ok := v.(*lar_cls_10___builtins_6_String)
        if ok {
            a[i] = (string)(*s)
        }
    }
    ls := lar_cls_10___builtins_6_String(fmt.Sprintf(format, a...))
    return &ls
}
