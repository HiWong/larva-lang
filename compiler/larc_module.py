#coding=utf8

"""
编译larva模块
"""

import copy
import os
import larc_common
import larc_token
import larc_type
import larc_stmt
import larc_expr

builtins_module = None
module_map = larc_common.OrderedDict()

def _parse_decr_set(token_list):
    decr_set = set()
    while True:
        t = token_list.peek()
        for decr in "public", "native", "final", "usemethod":
            if t.is_reserved(decr):
                if decr in decr_set:
                    t.syntax_err("重复的修饰'%s'" % decr)
                decr_set.add(decr)
                token_list.pop()
                break
        else:
            return decr_set

def _parse_gtp_name_list(token_list, dep_module_set):
    gtp_name_list = []
    while True:
        t, name = token_list.pop_name()
        if name in dep_module_set:
            t.syntax_err("泛型参数名与导入模块重名")
        if name in gtp_name_list:
            t.syntax_err("泛型参数名重复定义")
        gtp_name_list.append(name)
        t, sym = token_list.pop_sym()
        if sym == ",":
            continue
        if sym == ">":
            break
        t.syntax_err("需要'>'或','")
    return gtp_name_list

def _parse_arg_map(token_list, dep_module_set, gtp_name_list):
    arg_map = larc_common.OrderedDict()
    if token_list.peek().is_sym(")"):
        return arg_map
    while True:
        if token_list.peek().is_reserved("ref"):
            token_list.pop()
            is_ref = True
        else:
            is_ref = False
        type = larc_type.parse_type(token_list, dep_module_set, is_ref = is_ref)
        if type.name == "void":
            type.token.syntax_err("参数类型不可为void")
        t, name = token_list.pop_name()
        if name in arg_map:
            t.syntax_err("参数名重定义")
        if name in dep_module_set:
            t.syntax_err("参数名和导入模块名冲突")
        if name in gtp_name_list:
            t.syntax_err("参数名和函数或方法的泛型参数名冲突")
        arg_map[name] = type
        t = token_list.peek()
        if t.is_sym(","):
            token_list.pop_sym(",")
            continue
        if t.is_sym(")"):
            return arg_map
        t.syntax_err("需要','或')'")

#下面_ClsBase和_IntfBase的基类，用于定义一些接口和类共有的通用属性和方法
class _CoiBase:
    def __init__(self):
        self.is_cls = isinstance(self, _Cls)
        self.is_gcls_inst = isinstance(self, _GclsInst)
        self.is_intf = isinstance(self, _Intf)
        self.is_gintf_inst = isinstance(self, _GintfInst)
        assert [self.is_cls, self.is_gcls_inst, self.is_intf, self.is_gintf_inst].count(True) == 1

    def can_convert_from(self, other):
        assert isinstance(other, _CoiBase) and self is not other
        if self.is_cls or self.is_gcls_inst:
            #只能是到接口的转换
            return False
        #检查self接口的每个方法是否都在other实现了
        for name, method in self.method_map.iteritems():
            if name not in other.method_map:
                #没有对应方法
                return False
            other_method = other.method_map[name]
            if self.module is not other.module and "public" not in other_method.decr_set:
                #接口所在模块对other的方法无权限
                return False
            #注：允许方法的权限修饰不同，例如类A有个public方法，接口B的同签名方法是非public，B=A是可以赋值的，反之也可以
            #检查返回类型和参数类型是否一致，参数类型比较必须考虑ref
            if method.type != other_method.type:
                return False
            arg_map = method.arg_map
            other_arg_map = other_method.arg_map
            if len(arg_map) != len(other_arg_map):
                return False
            for i in xrange(len(arg_map)):
                arg_tp = arg_map.value_at(i)
                other_arg_tp = other_arg_map.value_at(i)
                if arg_tp != other_arg_tp or arg_tp.is_ref != other_arg_tp.is_ref:
                    return False
        return True

#下面_Cls和_GclsInst的基类，只用于定义一些通用属性和方法
class _ClsBase(_CoiBase):
    def expand_usemethod(self, expand_chain):
        if self.is_cls:
            assert not self.gtp_name_list
        else:
            assert self.type_checked

        #检查扩展状态
        assert self.usemethod_stat
        if self.usemethod_stat == "expanded":
            return
        if self.usemethod_stat == "expanding":
            larc_common.exit("检测到环形usemethod：'%s'" % expand_chain)

        self.usemethod_stat = "expanding"

        #统计usemethod属性的类型并确保其中的类都扩展完毕
        usemethod_coi_list = []
        for attr in self.attr_map.itervalues():
            if "usemethod" in attr.decr_set:
                coi = attr.type.get_coi()
                if isinstance(coi, (_Cls, _GclsInst)):
                    coi.expand_usemethod(expand_chain + "." + attr.name)
                usemethod_coi_list.append((attr, coi))

        #列表中的类或接口的可见方法都use过来
        usemethod_map = larc_common.OrderedDict()
        for attr, coi in usemethod_coi_list:
            for method in coi.method_map.itervalues():
                if coi.module is not self.module and "public" not in method.decr_set:
                    #无访问权限的忽略
                    continue
                if method.name in self.method_map:
                    #在本类已经重新实现的忽略
                    continue
                if method.name in usemethod_map:
                    larc_common.exit("类'%s'对方法'%s'存在多个可能的usemethod来源" % (self, method.name))
                if method.name in self.attr_map:
                    larc_common.exit("类'%s'中的属性'%s'和通过usemethod引入的方法同名" % (self, method.name))
                if method.name in self.module.get_dep_module_set(self.file_name):
                    larc_common.exit("类'%s'通过usemethod引入的方法'%s'与导入模块同名" % (self, method.name))
                if self.is_gcls_inst and method.name in self.gcls.gtp_name_list:
                    larc_common.exit("类'%s'通过usemethod引入的方法'%s'与泛型参数同名" % (self, method.name))
                usemethod_map[method.name] = _UseMethod(self, attr, method)
        for method in usemethod_map.itervalues():
            assert method.name not in self.method_map
            self.method_map[method.name] = method

        self.usemethod_stat = "expanded"

    def has_method_or_attr(self, name):
        return name in self.attr_map or name in self.method_map

    def get_method_or_attr(self, name, token):
        if name in self.method_map:
            return self.method_map[name], None
        if name in self.attr_map:
            return None, self.attr_map[name]
        token.syntax_err("类'%s'没有方法或属性'%s'" % (self, name))

class _MethodBase:
    def __init__(self):
        self.is_method = isinstance(self, _Method) or isinstance(self, _GclsInstMethod)
        self.is_usemethod = isinstance(self, _UseMethod)
        assert [self.is_method, self.is_usemethod].count(True) == 1

class _Method(_MethodBase):
    def __init__(self, cls, decr_set, type, name, arg_map, block_token_list):
        _MethodBase.__init__(self)

        self.cls = cls
        self.module = cls.module
        self.decr_set = decr_set
        self.type = type
        self.name = name
        self.arg_map = arg_map
        self.block_token_list = block_token_list

    __repr__ = __str__ = lambda self : "%s.%s" % (self.cls, self.name)

    def check_type(self):
        self.type.check(self.cls.module)
        for tp in self.arg_map.itervalues():
            tp.check(self.cls.module)

    def compile(self):
        if self.block_token_list is None:
            self.stmt_list = None
        else:
            self.stmt_list = larc_stmt.Parser(self.block_token_list, self.cls.module, self.cls.module.get_dep_module_set(self.cls.file_name),
                                              self.cls, None, self.type).parse((self.arg_map.copy(),), 0)
            self.block_token_list.pop_sym("}")
            assert not self.block_token_list
        del self.block_token_list

class _Attr:
    def __init__(self, cls, decr_set, type, name):
        self.cls = cls
        self.module = cls.module
        self.decr_set = decr_set
        self.type = type
        self.name = name

    __repr__ = __str__ = lambda self : "%s.%s" % (self.cls, self.name)

    def check_type(self):
        self.type.check(self.cls.module)

class _UseMethod(_MethodBase):
    def __init__(self, cls, attr, method):
        _MethodBase.__init__(self)

        self.attr = attr
        self.method = method

        self.cls = cls
        self.module = cls.module
        self.decr_set = method.decr_set
        self.type = method.type
        self.name = method.name
        self.arg_map = method.arg_map

    __repr__ = __str__ = lambda self : "%s.usemethod[%s.%s]" % (self.cls, self.attr.name, self.method)

class _Cls(_ClsBase):
    def __init__(self, module, file_name, decr_set, name, gtp_name_list):
        _ClsBase.__init__(self)

        if gtp_name_list:
            assert "native" not in decr_set

        self.module = module
        self.file_name = file_name
        self.decr_set = decr_set
        self.name = name
        self.gtp_name_list = gtp_name_list
        self.construct_method = None
        self.attr_map = larc_common.OrderedDict()
        self.method_map = larc_common.OrderedDict()
        self.usemethod_stat = None

    __repr__ = __str__ = lambda self : "%s.%s" % (self.module, self.name)

    def parse(self, token_list):
        while True:
            t = token_list.peek()
            if t.is_sym("}"):
                break

            #解析修饰
            decr_set = _parse_decr_set(token_list)
            if "final" in decr_set or "native" in decr_set:
                t.syntax_err("方法或属性不能用final或native修饰")

            t = token_list.peek()
            if t.is_name and t.value == self.name:
                t, name = token_list.pop_name()
                if token_list.peek().is_sym("("):
                    #构造方法
                    if "usemethod" in decr_set:
                        t.syntax_err("方法不可用usemethod修饰")
                    token_list.pop_sym("(")
                    self._parse_method(decr_set, larc_type.VOID_TYPE, name, token_list)
                    continue
                token_list.revert()

            #解析属性或方法
            type = larc_type.parse_type(token_list, self.module.get_dep_module_set(self.file_name))
            t, name = token_list.pop_name()
            if name == self.name:
                t.syntax_err("属性或方法不可与类同名")
            self._check_redefine(t, name)
            sym_t, sym = token_list.pop_sym()
            if sym == "(":
                #方法
                if "usemethod" in decr_set:
                    sym_t.syntax_err("方法不可用usemethod修饰")
                self._parse_method(decr_set, type, name, token_list)
                continue
            if sym in (";", ","):
                #属性
                if type.name == "void":
                    t.syntax_err("属性类型不可为void")
                while True:
                    if "usemethod" in decr_set and (type.is_nil or type.is_array or not type.is_obj_type):
                        t.syntax_err("usemethod不可用于类型'%s'" % type)
                    self.attr_map[name] = _Attr(self, decr_set, type, name)
                    if sym == ";":
                        break
                    #多属性定义
                    assert sym == ","
                    t, name = token_list.pop_name()
                    self._check_redefine(t, name)
                    sym_t, sym = token_list.pop_sym()
                    if sym not in (";", ","):
                        t.syntax_err()
                continue
            t.syntax_err()
        if self.construct_method is None:
            t.syntax_err("类'%s'缺少构造函数定义" % self)
        self.usemethod_stat = "to_expand"

    def _check_redefine(self, t, name):
        if name in self.module.get_dep_module_set(self.file_name):
            t.syntax_err("属性或方法名与导入模块名相同")
        if name in self.gtp_name_list:
            t.syntax_err("属性或方法名与泛型参数名相同")
        for i in self.attr_map, self.method_map:
            if name in i:
                t.syntax_err("属性或方法名重定义")

    def _parse_method(self, decr_set, type, name, token_list):
        arg_map = _parse_arg_map(token_list, self.module.get_dep_module_set(self.file_name), [])
        token_list.pop_sym(")")

        if "native" in self.decr_set:
            token_list.pop_sym(";")
            block_token_list = None
        else:
            token_list.pop_sym("{")
            block_token_list, sym = larc_token.parse_token_list_until_sym(token_list, ("}",))
            assert sym == "}"

        if name == self.name:
            #构造方法
            assert type is larc_type.VOID_TYPE
            self.construct_method = _Method(self, decr_set, larc_type.VOID_TYPE, name, arg_map, block_token_list)
        else:
            self.method_map[name] = _Method(self, decr_set, type, name, arg_map, block_token_list)

    def check_type(self):
        for attr in self.attr_map.itervalues():
            attr.check_type()
        self.construct_method.check_type()
        for method in self.method_map.itervalues():
            method.check_type()

    def compile(self):
        assert not self.gtp_name_list
        self.construct_method.compile()
        for method in self.method_map.itervalues():
            if isinstance(method, _UseMethod):
                continue
            method.compile()

class _GclsInstMethod(_MethodBase):
    def __init__(self, gcls_inst, method):
        _MethodBase.__init__(self)

        self.cls = gcls_inst
        self.method = method

        self.module = gcls_inst.module
        self.decr_set = method.decr_set
        self.type = copy.deepcopy(method.type)
        self.name = method.name
        self.arg_map = copy.deepcopy(method.arg_map)
        self.block_token_list = method.block_token_list.copy()

    __repr__ = __str__ = lambda self : "%s.%s" % (self.cls, self.method.name)

    def check_type(self):
        self.type.check(self.cls.gcls.module, self.cls.gtp_map)
        for tp in self.arg_map.itervalues():
            tp.check(self.cls.gcls.module, self.cls.gtp_map)

    def compile(self):
        self.stmt_list = larc_stmt.Parser(self.block_token_list, self.module, self.module.get_dep_module_set(self.cls.gcls.file_name),
                                          self.cls, self.cls.gtp_map, self.type).parse((self.arg_map.copy(),), 0)
        self.block_token_list.pop_sym("}")
        assert not self.block_token_list
        del self.block_token_list

class _GclsInstAttr:
    def __init__(self, gcls_inst, attr):
        self.cls = gcls_inst
        self.attr = attr

        self.module = gcls_inst.module
        self.decr_set = attr.decr_set
        self.type = copy.deepcopy(attr.type)
        self.name = attr.name

    __repr__ = __str__ = lambda self : "%s.%s" % (self.cls, self.attr.name)

    def check_type(self):
        self.type.check(self.cls.gcls.module, self.cls.gtp_map)

class _GclsInst(_ClsBase):
    def __init__(self, gcls, gtp_list):
        _ClsBase.__init__(self)

        self.gcls = gcls

        self.gtp_map = larc_common.OrderedDict()
        assert len(gcls.gtp_name_list) == len(gtp_list)
        for i in xrange(len(gtp_list)):
            self.gtp_map[gcls.gtp_name_list[i]] = gtp_list[i]

        self.module = gcls.module
        self.decr_set = gcls.decr_set
        self.name = gcls.name
        self._init_attr_and_method()
        self.type_checked = False
        self.usemethod_stat = "to_expand"
        self.compiled = False

    __repr__ = __str__ = lambda self : "%s<%s>" % (self.gcls, ", ".join([str(tp) for tp in self.gtp_map.itervalues()]))

    def _init_attr_and_method(self):
        assert self.gcls.construct_method is not None
        self.construct_method = _GclsInstMethod(self, self.gcls.construct_method)
        self.attr_map = larc_common.OrderedDict()
        for name, attr in self.gcls.attr_map.iteritems():
            self.attr_map[name] = _GclsInstAttr(self, attr)
        self.method_map = larc_common.OrderedDict()
        for name, method in self.gcls.method_map.iteritems():
            self.method_map[name] = _GclsInstMethod(self, method)

    def check_type(self):
        if self.type_checked:
            return False
        for attr in self.attr_map.itervalues():
            attr.check_type()
        self.construct_method.check_type()
        for method in self.method_map.itervalues():
            method.check_type()
        self.type_checked = True
        return True

    def compile(self):
        if self.compiled:
            return False
        self.construct_method.compile()
        for method in self.method_map.itervalues():
            method.compile()
        self.compiled = True
        return True

#下面_Intf和_GintfInst的基类，只用于定义一些通用属性和方法
class _IntfBase(_CoiBase):
    def get_method_or_attr(self, name, token):
        if name in self.method_map:
            return self.method_map[name], None
        token.syntax_err("接口'%s'没有方法'%s'" % (self, name))

class _IntfMethod:
    def __init__(self, intf, decr_set, type, name, arg_map):
        self.intf = intf

        self.module = intf.module
        self.decr_set = decr_set
        self.type = type
        self.name = name
        self.arg_map = arg_map

    __repr__ = __str__ = lambda self : "%s.%s" % (self.intf, self.name)

    def check_type(self):
        self.type.check(self.intf.module)
        for tp in self.arg_map.itervalues():
            tp.check(self.intf.module)

class _Intf(_IntfBase):
    def __init__(self, module, file_name, decr_set, name, gtp_name_list):
        _IntfBase.__init__(self)

        self.module = module
        self.file_name = file_name
        self.decr_set = decr_set
        self.name = name
        self.gtp_name_list = gtp_name_list
        self.method_map = larc_common.OrderedDict()

    __repr__ = __str__ = lambda self : "%s.%s" % (self.module, self.name)

    def parse(self, token_list):
        while True:
            t = token_list.peek()
            if t.is_sym("}"):
                break

            decr_set = _parse_decr_set(token_list)
            if decr_set - set(["public"]):
                t.syntax_err("接口方法只能用public修饰")

            type = larc_type.parse_type(token_list, self.module.get_dep_module_set(self.file_name))
            t, name = token_list.pop_name()
            self._check_redefine(t, name)
            token_list.pop_sym("(")
            self._parse_method(decr_set, type, name, token_list)

    def _check_redefine(self, t, name):
        if name in self.module.get_dep_module_set(self.file_name):
            t.syntax_err("接口方法名与导入模块名相同")
        if name in self.gtp_name_list:
            t.syntax_err("接口方法名与泛型参数名相同")
        if name in self.method_map:
            t.syntax_err("接口方法名重定义")

    def _parse_method(self, decr_set, type, name, token_list):
        arg_map = _parse_arg_map(token_list, self.module.get_dep_module_set(self.file_name), [])
        token_list.pop_sym(")")
        token_list.pop_sym(";")
        self.method_map[name] = _IntfMethod(self, decr_set, type, name, arg_map)

    def check_type(self):
        for method in self.method_map.itervalues():
            method.check_type()

class _GintfInstMethod:
    def __init__(self, gintf_inst, method):
        self.intf = gintf_inst
        self.method = method

        self.module = gintf_inst.module
        self.decr_set = method.decr_set
        self.type = copy.deepcopy(method.type)
        self.name = method.name
        self.arg_map = copy.deepcopy(method.arg_map)

    __repr__ = __str__ = lambda self : "%s.%s" % (self.intf, self.method.name)

    def check_type(self):
        self.type.check(self.intf.gintf.module, self.intf.gtp_map)
        for tp in self.arg_map.itervalues():
            tp.check(self.intf.gintf.module, self.intf.gtp_map)

class _GintfInst(_IntfBase):
    def __init__(self, gintf, gtp_list):
        _IntfBase.__init__(self)

        self.gintf = gintf

        self.gtp_map = larc_common.OrderedDict()
        assert len(gintf.gtp_name_list) == len(gtp_list)
        for i in xrange(len(gtp_list)):
            self.gtp_map[gintf.gtp_name_list[i]] = gtp_list[i]

        self.module = gintf.module
        self.decr_set = gintf.decr_set
        self.name = gintf.name
        self._init_method()
        self.type_checked = False

    __repr__ = __str__ = lambda self : "%s<%s>" % (self.gintf, ", ".join([str(tp) for tp in self.gtp_map.itervalues()]))

    def _init_method(self):
        self.method_map = larc_common.OrderedDict()
        for name, method in self.gintf.method_map.iteritems():
            self.method_map[name] = _GintfInstMethod(self, method)

    def check_type(self):
        if self.type_checked:
            return False
        for method in self.method_map.itervalues():
            method.check_type()
        self.type_checked = True
        return True

class _FuncBase:
    def __init__(self):
        self.is_func = isinstance(self, _Func)
        self.is_gfunc_inst = isinstance(self, _GfuncInst)
        assert [self.is_func, self.is_gfunc_inst].count(True) == 1

class _Func(_FuncBase):
    def __init__(self, module, file_name, decr_set, type, name, gtp_name_list, arg_map, block_token_list):
        _FuncBase.__init__(self)

        self.module = module
        self.file_name = file_name
        self.decr_set = decr_set
        self.type = type
        self.name = name
        self.gtp_name_list = gtp_name_list
        self.arg_map = arg_map
        self.block_token_list = block_token_list

    __repr__ = __str__ = lambda self : "%s.%s" % (self.module, self.name)

    def check_type(self):
        assert not self.gtp_name_list
        self.type.check(self.module)
        for tp in self.arg_map.itervalues():
            tp.check(self.module)

    def compile(self):
        if self.block_token_list is None:
            self.stmt_list = None
        else:
            self.stmt_list = larc_stmt.Parser(self.block_token_list, self.module, self.module.get_dep_module_set(self.file_name), None, None,
                                              self.type).parse((self.arg_map.copy(),), 0)
            self.block_token_list.pop_sym("}")
            assert not self.block_token_list
        del self.block_token_list

class _GfuncInst(_FuncBase):
    def __init__(self, gfunc, gtp_list):
        _FuncBase.__init__(self)

        self.gfunc = gfunc

        self.module = gfunc.module
        self.decr_set = gfunc.decr_set
        self.name = gfunc.name

        self.gtp_map = larc_common.OrderedDict()
        assert len(gfunc.gtp_name_list) == len(gtp_list)
        for i in xrange(len(gtp_list)):
            self.gtp_map[gfunc.gtp_name_list[i]] = gtp_list[i]

        self.type = copy.deepcopy(gfunc.type)
        self.arg_map = copy.deepcopy(gfunc.arg_map)
        self.block_token_list = gfunc.block_token_list.copy()

        self.type_checked = False
        self.compiled = False

    __repr__ = __str__ = lambda self : "%s<%s>" % (self.gfunc, ", ".join([str(tp) for tp in self.gtp_map.itervalues()]))

    def check_type(self):
        if self.type_checked:
            return False
        self.type.check(self.gfunc.module, self.gtp_map)
        for tp in self.arg_map.itervalues():
            tp.check(self.gfunc.module, self.gtp_map)
        self.type_checked = True
        return True

    def compile(self):
        if self.compiled:
            return False
        self.stmt_list = larc_stmt.Parser(self.block_token_list, self.module, self.module.get_dep_module_set(self.gfunc.file_name), None,
                                          self.gtp_map, self.type).parse((self.arg_map.copy(),), 0)
        self.block_token_list.pop_sym("}")
        assert not self.block_token_list
        del self.block_token_list
        self.compiled = True
        return True

class _GlobalVar:
    def __init__(self, module, file_name, decr_set, type, name, expr_token_list):
        self.module = module
        self.file_name = file_name
        self.decr_set = decr_set
        self.type = type
        self.name = name
        self.expr_token_list = expr_token_list
        self.used_dep_module_set = set()

    __repr__ = __str__ = lambda self : "%s.%s" % (self.module, self.name)

    def check_type(self):
        self.type.check(self.module)

    def compile(self):
        if self.expr_token_list is None:
            self.expr = None
        else:
            self.expr = larc_expr.Parser(self.expr_token_list, self.module, self.module.get_dep_module_set(self.file_name), None,
                                         None, self.used_dep_module_set).parse((), self.type)
            t, sym = self.expr_token_list.pop_sym()
            assert not self.expr_token_list and sym in (";", ",")
        del self.expr_token_list

        if self.module.name in self.used_dep_module_set:
            self.used_dep_module_set.remove(self.module.name)
        for used_dep_module in self.used_dep_module_set:
            module_map[used_dep_module].check_cycle_import_for_gv_init(self, [used_dep_module])

class Module:
    def __init__(self, file_path_name):
        if file_path_name.endswith(".lar"):
            self.dir, file_name = os.path.split(file_path_name)
            self.name = file_name[: -4]
            file_name_list = [file_name]
            self.is_pkg = False
        else:
            assert os.path.isdir(file_path_name)
            self.dir = file_path_name
            self.name = os.path.basename(file_path_name)
            file_name_list = [fn for fn in os.listdir(self.dir) if fn.endswith(".lar")]
            self.is_pkg = True
        self.file_dep_module_set_map = {}
        self.cls_map = larc_common.OrderedDict()
        self.gcls_inst_map = larc_common.OrderedDict()
        self.intf_map = larc_common.OrderedDict()
        self.gintf_inst_map = larc_common.OrderedDict()
        self.func_map = larc_common.OrderedDict()
        self.gfunc_inst_map = larc_common.OrderedDict()
        self.global_var_map = larc_common.OrderedDict()
        self.literal_str_list = []
        for file_name in file_name_list:
            self._precompile(file_name)
        if self.name == "__builtins":
            #内建模块需要做一些必要的检查
            if "String" not in self.cls_map: #必须有String类
                larc_common.exit("内建模块缺少String类")
            str_cls = self.cls_map["String"]
            if "format" in str_cls.attr_map or "format" in str_cls.method_map:
                larc_common.exit("String类的format方法属于内建保留方法，禁止显式定义")

    __repr__ = __str__ = lambda self : self.name

    def _precompile(self, file_name):
        #解析token列表，解析正文
        token_list = larc_token.parse_token_list(os.path.join(self.dir, file_name))
        self._parse_text(file_name, token_list)

    def _parse_text(self, file_name, token_list):
        self.file_dep_module_set_map[file_name] = dep_module_set = set()
        import_end = False
        self.literal_str_list += [t for t in token_list if t.type == "literal_str"]
        while token_list:
            #解析import
            t = token_list.peek()
            if t.is_reserved("import"):
                #import
                if import_end:
                    t.syntax_err("import必须在模块代码最前面")
                self._parse_import(token_list, dep_module_set)
                continue
            import_end = True

            #解析修饰
            decr_set = _parse_decr_set(token_list)

            #解析各种定义
            t = token_list.peek()
            if t.is_reserved("class"):
                #解析类
                if decr_set - set(["public", "native"]):
                    t.syntax_err("类只能用public和native修饰")
                self._parse_cls(file_name, dep_module_set, decr_set, token_list)
                continue

            if t.is_reserved("interface"):
                #解析interface
                if decr_set - set(["public"]):
                    t.syntax_err("interface只能用public修饰")
                self._parse_intf(file_name, dep_module_set, decr_set, token_list)
                continue

            #可能是函数或全局变量
            type = larc_type.parse_type(token_list, dep_module_set)
            name_t, name = token_list.pop_name()
            self._check_redefine(name_t, name, dep_module_set)
            t, sym = token_list.pop_sym()
            if sym in ("(", "<"):
                #函数
                if decr_set - set(["public", "native"]):
                    t.syntax_err("函数只能用public和native修饰")
                if sym == "<" and "native" in decr_set:
                    t.syntax_err("不可定义native泛型函数")
                self._parse_func(file_name, dep_module_set, decr_set, type, name_t, sym == "<", token_list)
                continue
            if sym in (";", "=", ","):
                #全局变量
                if decr_set - set(["public", "final"]):
                    t.syntax_err("全局变量只能用public和final修饰")
                if type.name == "void":
                    t.syntax_err("变量类型不可为void")
                while True:
                    if sym == "=":
                        expr_token_list, sym = larc_token.parse_token_list_until_sym(token_list, (";", ","))
                    else:
                        expr_token_list = None
                    self.global_var_map[name] = _GlobalVar(self, file_name, decr_set, type, name, expr_token_list)
                    if sym == ";":
                        break
                    #定义了多个变量，继续解析
                    assert sym == ","
                    t, name = token_list.pop_name()
                    self._check_redefine(t, name, dep_module_set)
                    t, sym = token_list.pop_sym()
                    if sym not in (";", "=", ","):
                        t.syntax_err()
                continue
            t.syntax_err()

    def _check_redefine(self, t, name, dep_module_set):
        if name in dep_module_set:
            t.syntax_err("定义的名字和导入模块名重名")
        for i in self.cls_map, self.intf_map, self.global_var_map, self.func_map:
            if name in i:
                t.syntax_err("名字重定义")

    def _parse_import(self, token_list, dep_module_set):
        t = token_list.pop()
        assert t.is_reserved("import")
        while True:
            t, name = token_list.pop_name()
            if name in dep_module_set:
                t.syntax_err("模块重复import")
            dep_module_set.add(name)
            t = token_list.peek()
            if not t.is_sym:
                t.syntax_err("需要';'或','")
            t, sym = token_list.pop_sym()
            if sym == ";":
                return
            if sym != ",":
                t.syntax_err("需要';'或','")

    def _parse_cls(self, file_name, dep_module_set, decr_set, token_list):
        t = token_list.pop()
        assert t.is_reserved("class")
        t, name = token_list.pop_name()
        self._check_redefine(t, name, dep_module_set)
        t = token_list.peek()
        if t.is_sym("<"):
            if "native" in decr_set:
                t.syntax_err("不可定义native泛型类")
            token_list.pop_sym("<")
            gtp_name_list = _parse_gtp_name_list(token_list, dep_module_set)
            if name in gtp_name_list:
                t.syntax_err("存在与类名相同的泛型参数名")
        else:
            gtp_name_list = []
        token_list.pop_sym("{")
        cls = _Cls(self, file_name, decr_set, name, gtp_name_list)
        cls.parse(token_list)
        token_list.pop_sym("}")
        self.cls_map[name] = cls

    def _parse_intf(self, file_name, dep_module_set, decr_set, token_list):
        t = token_list.pop()
        assert t.is_reserved("interface")
        t, name = token_list.pop_name()
        self._check_redefine(t, name, dep_module_set)
        t = token_list.peek()
        if t.is_sym("<"):
            token_list.pop_sym("<")
            gtp_name_list = _parse_gtp_name_list(token_list, dep_module_set)
        else:
            gtp_name_list = []
        token_list.pop_sym("{")
        intf = _Intf(self, file_name, decr_set, name, gtp_name_list)
        intf.parse(token_list)
        token_list.pop_sym("}")
        self.intf_map[name] = intf

    def _parse_func(self, file_name, dep_module_set, decr_set, type, name_t, is_gfunc, token_list):
        name = name_t.value

        if is_gfunc:
            gtp_name_list = _parse_gtp_name_list(token_list, dep_module_set)
            token_list.pop_sym("(")
        else:
            gtp_name_list = []
        arg_map = _parse_arg_map(token_list, dep_module_set, gtp_name_list)
        token_list.pop_sym(")")

        if "native" in decr_set:
            assert not is_gfunc
            token_list.pop_sym(";")
            block_token_list = None
        else:
            token_list.pop_sym("{")
            block_token_list, sym = larc_token.parse_token_list_until_sym(token_list, ("}",))
            assert sym == "}"

        self.func_map[name] = _Func(self, file_name, decr_set, type, name, gtp_name_list, arg_map, block_token_list)
        if name.startswith("__ptm_"):
            l = name[6 :].split("_")
            if len(l) < 2 or l[0] not in larc_type.PTM_TYPE_LIST:
                name_t.syntax_err("非法的基础类型方法名")
            ptm_tp = l[0]
            if gtp_name_list:
                name_t.syntax_err("基础类型方法不能实现为泛型函数")
            if len(arg_map) == 0 or arg_map.value_at(0) != eval("larc_type.%s_TYPE" % ptm_tp.upper()):
                name_t.syntax_err("基础类型方法的第一个参数类型必须和方法所属类型一致：需要[%s]" % ptm_tp)

    def check_type_for_non_ginst(self):
        for map in self.cls_map, self.intf_map, self.func_map:
            for i in map.itervalues():
                if i.gtp_name_list:
                    #泛型元素不做check
                    continue
                i.check_type()
        for i in self.global_var_map.itervalues():
            i.check_type()

    def check_type_for_ginst(self):
        for map in self.gcls_inst_map, self.gintf_inst_map, self.gfunc_inst_map:
            #反向遍历，优先处理新ginst
            for i in xrange(len(map) - 1, -1, -1):
                if map.value_at(i).check_type():
                    #成功处理了一个新的，立即返回
                    return True
        #全部都无需处理
        return False

    def expand_usemethod(self):
        for cls in self.cls_map.itervalues():
            if cls.gtp_name_list:
                continue
            cls.expand_usemethod(str(cls))
        for gcls_inst in self.gcls_inst_map.itervalues():
            gcls_inst.expand_usemethod(str(gcls_inst))

    def check_main_func(self):
        if "main" not in self.func_map:
            larc_common.exit("主模块[%s]没有main函数" % self)
        main_func = self.func_map["main"]
        if main_func.gtp_name_list:
            larc_common.exit("主模块[%s]的main函数不能是泛型函数" % self)
        if main_func.type != larc_type.INT_TYPE:
            larc_common.exit("主模块[%s]的main函数返回类型必须为int" % self)
        if len(main_func.arg_map) != 1:
            larc_common.exit("主模块[%s]的main函数只能有一个类型为'__builtins.String[]'的参数" % self)
        tp = main_func.arg_map.value_at(0)
        if tp.array_dim_count != 1 or tp.is_ref or tp.to_elem_type() != larc_type.STR_TYPE:
            larc_common.exit("主模块[%s]的main函数的参数类型必须为'__builtins.String[]'" % self)
        if "public" not in main_func.decr_set:
            larc_common.exit("主模块[%s]的main函数必须是public的" % self)

    def compile_non_ginst(self):
        for map in self.cls_map, self.func_map:
            for i in map.itervalues():
                if i.gtp_name_list:
                    continue
                i.compile()
        for i in self.global_var_map.itervalues():
            i.compile()

    def compile_ginst(self):
        for map in self.gcls_inst_map, self.gfunc_inst_map:
            #反向遍历，优先处理新ginst
            for i in xrange(len(map) - 1, -1, -1):
                if map.value_at(i).compile():
                    #成功处理了一个新的，立即返回
                    return True
        #全部都无需处理
        return False

    def check_cycle_import_for_gv_init(self, gv, stk):
        assert stk and stk[-1] == self.name
        for dep_module in self.get_dep_module_set():
            if dep_module == gv.module.name:
                larc_common.exit("全局变量'%s'的初始化依赖于模块'%s'，且存在从其依赖关系开始并包含模块'%s'的循环模块依赖：%s" %
                                 (gv, stk[0], gv.module.name, "->".join([gv.module.name] + stk + [dep_module])))
            if dep_module in stk:
                #进入循环依赖但不包含gv模块，继续探测
                continue
            stk.append(dep_module)
            module_map[dep_module].check_cycle_import_for_gv_init(gv, stk)
            stk.pop()

    def get_coi(self, type):
        is_cls = is_intf = False
        if type.name in self.cls_map:
            is_cls = True
            coi = self.cls_map[type.name]
            tp_desc = "类"
        elif type.name in self.intf_map:
            is_intf = True
            coi = self.intf_map[type.name]
            tp_desc = "接口"
        else:
            return None

        if coi.gtp_name_list:
            if type.gtp_list:
                if len(coi.gtp_name_list) != len(type.gtp_list):
                    type.token.syntax_err("泛型参数数量错误：需要%d个，传入了%d个" % (len(coi.gtp_name_list), len(type.gtp_list)))
            else:
                type.token.syntax_err("泛型%s'%s'无法单独使用" % (tp_desc, coi))
        else:
            if type.gtp_list:
                type.token.syntax_err("'%s'不是泛型%s" % (coi, tp_desc))

        assert len(coi.gtp_name_list) == len(type.gtp_list)
        if not coi.gtp_name_list:
            return coi

        #泛型类或接口，生成gXXX实例后再返回，ginst_key是这个泛型实例的唯一key标识
        ginst_key = id(coi),
        for tp in type.gtp_list:
            array_dim_count = tp.array_dim_count
            while tp.is_array:
                tp = tp.to_elem_type()
            if tp.token.is_reserved:
                ginst_key += tp.name, array_dim_count
            else:
                ginst_key += id(tp.get_coi()), array_dim_count

        if is_cls:
            ginst_map = self.gcls_inst_map
            ginst_class = _GclsInst
        else:
            assert is_intf
            ginst_map = self.gintf_inst_map
            ginst_class = _GintfInst
        if ginst_key in ginst_map:
            return ginst_map[ginst_key]
        ginst_map[ginst_key] = ginst = ginst_class(coi, type.gtp_list)

        s = str(ginst)
        if len(s) > 1000:
            larc_common.exit("存在名字过长的泛型实例，请检查是否存在泛型实例的无限递归构建：%s" % s)

        return ginst

    def get_func(self, t, gtp_list):
        name = t.value
        if name not in self.func_map:
            return None
        func = self.func_map[name]
        if func.gtp_name_list:
            if gtp_list:
                if len(func.gtp_name_list) != len(gtp_list):
                    t.syntax_err("泛型参数数量错误：需要%d个，传入了%d个" % (len(func.gtp_name_list), len(gtp_list)))
            else:
                t.syntax_err("泛型函数'%s'无法单独使用" % func)
        else:
            if gtp_list:
                t.syntax_err("'%s'不是泛型函数" % func)

        assert len(func.gtp_name_list) == len(gtp_list)
        if not func.gtp_name_list:
            return func

        #泛型函数，生成gfunc实例后再返回，gfunc_key是这个泛型实例的唯一key标识
        gfunc_key = id(func),
        for tp in gtp_list:
            array_dim_count = tp.array_dim_count
            while tp.is_array:
                tp = tp.to_elem_type()
            if tp.token.is_reserved:
                gfunc_key += tp.name, array_dim_count
            else:
                gfunc_key += id(tp.get_coi()), array_dim_count

        if gfunc_key in self.gfunc_inst_map:
            return self.gfunc_inst_map[gfunc_key]
        self.gfunc_inst_map[gfunc_key] = gfunc_inst = _GfuncInst(func, gtp_list)

        s = str(gfunc_inst)
        if len(s) > 1000:
            larc_common.exit("存在名字过长的泛型实例，请检查是否存在泛型实例的无限递归构建：%s" % s)

        return gfunc_inst

    def get_global_var(self, name):
        return self.global_var_map[name] if name in self.global_var_map else None

    def has_type(self, name):
        return name in self.cls_map or name in self.intf_map

    def has_func(self, name):
        return name in self.func_map

    def has_global_var(self, name):
        return name in self.global_var_map

    def get_main_func(self):
        assert "main" in self.func_map
        return self.func_map["main"]

    def has_native_item(self):
        for cls in self.cls_map.itervalues():
            if "native" in cls.decr_set:
                return True
        for func in self.func_map.itervalues():
            if "native" in func.decr_set:
                return True
        return False

    def get_dep_module_set(self, file_name = None):
        if file_name is None:
            dep_module_set = set()
            for s in self.file_dep_module_set_map.itervalues():
                dep_module_set |= s
            return dep_module_set
        return self.file_dep_module_set_map[file_name]

#反复对所有新增的ginst进行check type，直到完成
def check_type_for_ginst():
    while True:
        for m in module_map.itervalues():
            if m.check_type_for_ginst():
                #有一个模块刚check了新的ginst，有可能生成新ginst，重启check流程
                break
        else:
            #所有ginst都check完毕
            break

#在编译过程中如果可能新生成了泛型实例，则调用这个进行check type和usemethod的expand
def check_new_ginst_during_compile():
    check_type_for_ginst()
    for m in module_map.itervalues():
        m.expand_usemethod()
