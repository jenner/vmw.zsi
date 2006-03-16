############################################################################
# Joshua R. Boverhof, LBNL
# See LBNLCopyright for copyright notice!
###########################################################################

import pydoc, sys, warnings
from ZSI import TC

# If function.__name__ is read-only, fail
def _x(): return
try: 
    _x.func_name = '_y'
except:
    raise RuntimeError,\
        'use python-2.4 or later, cannot set function names in python "%s"'\
        %sys.version
del _x


class pyclass_type(type):
    """Stability: Unstable

    type for pyclasses used with typecodes.  expects the typecode to
    be available in the classdict.  creates python properties for accessing
    and setting the elements specified in the ofwhat list, and factory methods
    for constructing the elements.
    """
    def __new__(cls,classname,bases,classdict):
        """
        """
        import new
        typecode = classdict.get('typecode')
        assert typecode is not None, 'MUST HAVE A TYPECODE.'

        # Assume this means not immutable type. ie. ofwhat.
        if len(bases) == 0:
            assert hasattr(typecode, 'ofwhat'), 'typecode has no ofwhat list??'
            assert hasattr(typecode, 'attribute_typecode_dict'),\
                'typecode has no attribute_typecode_dict??'
            
            if typecode.mixed:
                get,set = cls.__create_text_functions_from_what(typecode)
                
                if classdict.has_key(get.__name__):
                    raise AttributeError,\
                        'attribute %s previously defined.' %get.__name__
                        
                if classdict.has_key(set.__name__):
                    raise AttributeError,\
                        'attribute %s previously defined.' %set.__name__
                
                classdict[get.__name__] = get
                classdict[set.__name__] = set
                
            #attribute_typecode_dict = typecode.attribute_typecode_dict or {}
            #for key,what in attribute_typecode_dict.items():
            #    get,set = cls.__create_attr_functions_from_what(key, what)
            #    if classdict.has_key(get.__name__):
            #        raise AttributeError,\
            #            'attribute %s previously defined.' %get.__name__
            #            
            #    if classdict.has_key(set.__name__):
            #        raise AttributeError,\
            #            'attribute %s previously defined.' %set.__name__
            #    
            #    classdict[get.__name__] = get
            #    classdict[set.__name__] = set
                
            for what in typecode.ofwhat:
                get,set,new_func = cls.__create_functions_from_what(what)

                if classdict.has_key(get.__name__):
                    raise AttributeError,\
                        'attribute %s previously defined.' %get.__name__
                        
                classdict[get.__name__] = get
                if classdict.has_key(set.__name__):
                    raise AttributeError,\
                        'attribute %s previously defined.' %set.__name__
                        
                classdict[set.__name__] = set
                if new_func is not None:
                    if classdict.has_key(new_func.__name__):
                        raise AttributeError,\
                            'attribute %s previously defined.' %new_func.__name__
                            
                    classdict[new_func.__name__] = new_func

                assert not classdict.has_key(what.pname),\
                    'collision with pname="%s", bail..' %what.pname
                    
                #if classdict.has_key(what.pname):
                #    classdict['p%s' %what.aname] =\
                #        property(get, set, None, 
                #            'property for element (%s,%s)' %(what.nspname,what.pname))
                #else:
                pname = what.pname
                if pname is None and isinstance(what, TC.AnyElement): pname = 'any'
                assert pname is not None, 'Element with no name: %s' %what

                # TODO: for pname if keyword just uppercase first letter.
                #if pydoc.Helper.keywords.has_key(pname):
                pname = pname[0].upper() + pname[1:]
                assert not pydoc.Helper.keywords.has_key(pname), 'unexpected keyword: %s' %pname

                classdict[pname] =\
                    property(get, set, None, 
                        'property for element (%s,%s), minOccurs="%s" maxOccurs="%s" nillable="%s"'\
                        %(what.nspname,what.pname,what.minOccurs,what.maxOccurs,what.nillable)
                        )

        # 
        # mutable type <complexType> complexContent | modelGroup
        # or immutable type <complexType> simpleContent (float, str, etc)
        # 
        if hasattr(typecode, 'attribute_typecode_dict'):
            attribute_typecode_dict = typecode.attribute_typecode_dict or {}
            for key,what in attribute_typecode_dict.items():
                get,set = cls.__create_attr_functions_from_what(key, what)
                if classdict.has_key(get.__name__):
                    raise AttributeError,\
                        'attribute %s previously defined.' %get.__name__
                        
                if classdict.has_key(set.__name__):
                    raise AttributeError,\
                        'attribute %s previously defined.' %set.__name__
                
                classdict[get.__name__] = get
                classdict[set.__name__] = set

        return type.__new__(cls,classname,bases,classdict)

    def __create_functions_from_what(what):
 
        def get(self):
            return getattr(self, what.aname)
        get.im_func = 'get_element_%s' %what.aname

        if what.maxOccurs > 1:
            def set(self, value):
                setattr(self, what.aname, [value])
        else:
            def set(self, value):
                setattr(self, what.aname, value)

        pyclass = what.pyclass
        if isinstance(what, TC.ComplexType) or isinstance(what, TC.Array):
            def new_func(self):
                '''returns a mutable type
                '''
                return pyclass()
            new_func.__name__ = 'new%s' %what.aname
        elif pyclass is None:
            def new_func(self, value):
                '''value -- initialize value
                NOT IMPLEMENTED FOR %s, UNSUPPORTED TYPECODE.
                ''' %what.__class__
                raise NotImplementedError,\
                    'no support built in for %s right now' %what.__class__
                    
            new_func = None
        else:
            def new_func(self, value):
                '''value -- initialize value
                returns an immutable type
                '''
                return pyclass(value)
            new_func.__name__ = 'new%s' %what.aname

        get.func_name = 'get_element_%s' %what.aname
        set.func_name = 'set_element_%s' %what.aname
        return get,set,new_func
    __create_functions_from_what = staticmethod(__create_functions_from_what)
    
    

    def __create_attr_functions_from_what(key, what):
        def get(self):
            '''returns attribute value for attribute %s, else None.
            ''' %str(key)
            return getattr(self, what.attrs_aname, {}).get(key, None)
                
        #get.im_func = 'get_element_%s' %what.aname

        def set(self, value):
            '''set value for attribute %s.
            value -- initialize value, immutable type
            ''' %str(key)
            if not hasattr(self, what.attrs_aname):
                setattr(self, what.attrs_aname, {})
            getattr(self, what.attrs_aname)[key] = value
        
        # TODO: need to make sure these function names are legal.
        
        if type(key) in (tuple, list):
            get.__name__ = 'get_attribute_%s' %key[1]
            set.__name__ = 'set_attribute_%s' %key[1]
        else:
            get.__name__ = 'get_attribute_%s' %key
            set.__name__ = 'set_attribute_%s' %key

        return get,set
    __create_attr_functions_from_what = \
        staticmethod(__create_attr_functions_from_what)

    def __create_text_functions_from_what(what):
        
        def get(self):
            '''returns text content, else None.
            '''
            return getattr(self, what.mixed_aname, None)
                
        get.im_func = 'get_text'

        def set(self, value):
            '''set text content.
            value -- initialize value, immutable type
            '''
            setattr(self, what.mixed_aname, value)
            
        get.im_func = 'set_text'
        
        return get,set
    __create_text_functions_from_what = \
        staticmethod(__create_text_functions_from_what)
        
        
        