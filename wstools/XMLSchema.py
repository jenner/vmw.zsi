# Copyright (c) 2001 Zope Corporation and Contributors. All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.0 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.

ident = "$Id$"

import types, weakref, urllib
from threading import RLock
from xml.dom.ext import SplitQName
from xml.ns import SCHEMA, XMLNS
from Utility import DOM, Collection
from StringIO import StringIO


class SchemaReader:
    """A SchemaReader creates XMLSchema objects from urls and xml data.
    """
    def __init__(self, domReader=None):
        """domReader -- class must implement DOMAdapterInterface
        """
        self.__readerClass = domReader
        if not self.__readerClass:
            self.__readerClass = DOMAdapter
        self._includes = {}
        self._imports = {}

    def __setImports(self, schema):
        """Add dictionary of imports to schema instance.
           schema -- XMLSchema instance
        """
        for ns,val in schema.imports.items(): 
            if self._imports.has_key(ns):
                schema.addImportSchema(self._imports[ns])

    def __setIncludes(self, schema):
        """Add dictionary of includes to schema instance.
           schema -- XMLSchema instance
        """
        for schemaLocation, val in schema.includes.items(): 
            if self._includes.has_key(schemaLocation):
                schema.addIncludeSchema(self._imports[schemaLocation])

    def addSchemaByLocation(self, location, schema):
        """provide reader with schema document for a location.
        """
        self._includes[location] = schema

    def addSchemaByNamespace(self, schema):
        """provide reader with schema document for a targetNamespace.
        """
        self._imports[schema.targetNamespace] = schema

    def loadFromNode(self, parent, element):
        """element -- DOM node or document
           parent -- WSDLAdapter instance
        """
        reader = self.__readerClass(element)
        schema = XMLSchema(parent)
        #HACK to keep a reference
        schema.wsdl = parent
        schema.load(reader)
        return schema
        
    def loadFromStream(self, file):
        """Return an XMLSchema instance loaded from a file object.
           file -- file object
        """
        reader = self.__readerClass()
        reader.loadDocument(file)
        schema = XMLSchema()
        schema.load(reader)
        self.__setIncludes(schema)
        self.__setImports(schema)
        return schema

    def loadFromString(self, data):
        """Return an XMLSchema instance loaded from an XML string.
           data -- XML string
        """
        return self.loadFromStream(StringIO(data))

    def loadFromURL(self, url):
        """Return an XMLSchema instance loaded from the given url.
           url -- URL to dereference
        """
        if not url.endswith('xsd'):
            raise SchemaError, 'unknown file type %s' %url
        reader = self.__readerClass()
        reader.loadFromURL(url)
        schema = XMLSchema()
        schema.load(reader)
        self.__setIncludes(schema)
        self.__setImports(schema)

    def loadFromFile(self, filename):
        """Return an XMLSchema instance loaded from the given file.
           filename -- name of file to open
        """
        file = open(filename, 'rb')
        try:     schema = self.loadFromStream(file)
        finally: file.close()
        return schema


class SchemaError(Exception): 
    pass

###########################
# DOM Utility Adapters 
##########################
class DOMAdapterInterface:
    def hasattr(self, attr):
        """return true if node has attribute 
           attr - attribute to check for
        """
        raise NotImplementedError, 'adapter method not implemented'

    def getContentList(self, *contents):
        """returns an ordered list of child nodes
           *contents -- list of node names to return
        """
        raise NotImplementedError, 'adapter method not implemented'

    def setAttributeDictionary(self, attributes):
        """set attribute dictionary
        """
        raise NotImplementedError, 'adapter method not implemented'

    def getAttributeDictionary(self):
        """returns a dict of node's attributes
        """
        raise NotImplementedError, 'adapter method not implemented'

    def getTagName(self):
        """returns tagName of node
        """
        raise NotImplementedError, 'adapter method not implemented'

    def loadDocument(self, file):
        """load a Document from a file object
           file --
        """
        raise NotImplementedError, 'adapter method not implemented'

    def loadFromURL(self, url):
        """load a Document from an url
           url -- URL to dereference
        """
        raise NotImplementedError, 'adapter method not implemented'


class DOMAdapter(DOMAdapterInterface):
    """Adapter for ZSI.Utility.DOM
    """
    def __init__(self, node=None):
        """Reset all instance variables.
           element -- DOM document, node, or None
        """
        if hasattr(node, 'documentElement'):
            self.__node = node.documentElement
        else:
            self.__node = node
        self.__attributes = None

    def hasattr(self, attr):
        """XXX assuming all xsd attributes not prefixed,
           all others are.  Should ask xmlInterface so
           it can take care namespace mapping for
           prefixed attributes
        """
        if not self.__attributes:
            self.setAttributeDictionary()
        return self.__attributes.has_key(attr)

    def getContentList(self, *contents):
        nodes = []
        ELEMENT_NODE = self.__node.ELEMENT_NODE
        for child in DOM.getElements(self.__node, None):
            if child.nodeType == ELEMENT_NODE and\
               SplitQName(child.tagName)[1] in contents:
                nodes.append(child)
        return map(self.__class__, nodes)

    def setAttributeDictionary(self):
        self.__attributes = {}
        for v in self.__node._attrs.values():
            self.__attributes[v.nodeName] = v.nodeValue

    def getAttributeDictionary(self):
        if not self.__attributes:
            self.setAttributeDictionary()
        return self.__attributes

    def getTagName(self):
        return self.__node.tagName

    def loadDocument(self, file):
        self.__node = DOM.loadDocument(file)
        if hasattr(self.__node, 'documentElement'):
            self.__node = self.__node.documentElement

    def loadFromURL(self, url):
        self.__node = DOM.loadFromURL(url)
        if hasattr(self.__node, 'documentElement'):
            self.__node = self.__node.documentElement

 
class XMLBase: 
    """ These class variables are for string indentation.
    """ 
    __indent = 0
    __rlock = RLock()

    def __str__(self):
        XMLBase.__rlock.acquire()
        XMLBase.__indent += 1
        tmp = "<" + str(self.__class__) + '>\n'
        for k,v in self.__dict__.items():
            tmp += "%s* %s = %s\n" %(XMLBase.__indent*'  ', k, v)
        XMLBase.__indent -= 1 
        XMLBase.__rlock.release()
        return tmp

##########################################################
# Schema Components
#########################################################
class XMLSchemaComponent(XMLBase):
    """
       class variables: 
           required -- list of required attributes
           attributes -- dict of default attribute values, including None.
               Value can be a function for runtime dependencies.
           contents -- dict of namespace keyed content lists.
               'xsd' content of xsd namespace.
    """
    required = []
    attributes = {}
    contents = {}
    xmlns_key = ''
    def __init__(self, parent=None):
        """parent -- parent instance
           instance variables:
               attributes -- dictionary of node's attributes
        """
        self.attributes = None
        self._parent = parent
        if self._parent:
            self._parent = weakref.ref(parent)

        if not self.__class__ == XMLSchemaComponent\
           and not (type(self.__class__.required) == type(XMLSchemaComponent.required)\
           and type(self.__class__.attributes) == type(XMLSchemaComponent.attributes)\
           and type(self.__class__.contents) == type(XMLSchemaComponent.contents)):
            raise RuntimeError, 'Bad type for a class variable in %s' %self.__class__

    def getTargetNamespace(self):
        """return targetNamespace
        """
        parent = self
        tns = self.attributes.get('targetNamespace')
        while not tns:
            parent = parent._parent()
            tns = parent.attributes.get('targetNamespace')
        return tns

    def getTypeDefinition(self, attribute):
        """attribute -- attribute with a QName value (eg. type).
           collection -- check types collection in parent Schema instance
        """
        return self.getQNameAttribute('types', attribute)

    def getElementDeclration(self, attribute):
        """attribute -- attribute with a QName value (eg. element).
           collection -- check elements collection in parent Schema instance.
        """
        return self.getQNameAttribute('elements', attribute)

    def getQNameAttribute(self, collection, attribute):
        """attribute -- an information item attribute, with a QName value.
           collection -- collection in parent Schema instance to search.
        """
        type_def = None
        tdc = self.attributes.get(attribute)
        if tdc:
            parent = self
            while not isinstance(parent, Schema):
                parent = parent._parent()
            if parent.targetNamespace == tdc.getTargetNamespace():
                type_def = getattr(parent, collection)[tdc.getName()]
            elif parent.imports.has_key(tdc.getTargetNamespace()):
                schema = parent.imports[tdc.getTargetNamespace()].getSchema()
                type_def = getattr(schema, collection)[tdc.getName()]
            else:
                raise SchemaError, 'missing import %s' %tdc
        return type_def

    def getXMLNS(self, prefix=None):
        """retrieve contents
           empty string returns 'xmlns'
        """
        parent = self
        ns = self.attributes['xmlns'].get(prefix)
        while not ns:
            parent = parent._parent()
            ns = parent.attributes['xmlns'].get(prefix or self.__class__.xmlns_key)
        return ns

    def getAttribute(self, attribute):
        """return requested attribute or None
        """
        return self.attributes.get(attribute)
 
    def setAttributes(self, node):
        """Sets up attribute dictionary, checks for required attributes and 
           sets default attribute values. attr is for default attribute values 
           determined at runtime.
        """
        self.attributes = {'xmlns':{}}
        for k,v in node.getAttributeDictionary().items():
            prefix,value = SplitQName(k)
            if value == 'xmlns':
                self.attributes[value][prefix or self.__class__.xmlns_key] = v
            elif prefix:
                ns = node.getNamespace(prefix)
                if ns == XMLNS or prefix == 'xml':
                    self.attributes['xml'][k] = v
                elif ns in XSDNS:
                    self.attributes[value] = v
                else:
                    raise SchemaError, 'attribute %s, namespace unknown' %k
            else:
                self.attributes[k] = v

        self.__checkAttributes()
        self.__setAttributeDefaults()

        #set QNames
        for k in ['type', 'element', 'base', 'ref', 'substitutionGroup', 'itemType']:
            if self.attributes.has_key(k):
                prefix, value = SplitQName(self.attributes.get(k))
                self.attributes[k] = \
                    TypeDescriptionComponent((self.getXMLNS(prefix), value))

        #Union, memberTypes is a whitespace separated list of QNames
        if self.attributes.has_key('memberTypes'):
            qnames = self.attributes['memberTypes']
            

    def getContents(self, node):
        """retrieve xsd contents
        """
        return node.getContentList(*self.__class__.contents['xsd'])

    def __setAttributeDefaults(self):
        """Looks for default values for unset attributes.  If
           class variable representing attribute is None, then
           it must be defined as a instance variable.
        """
        for k,v in self.attributes.items():
            if (not v) and (k != 'xmlns'):
                default_attr = getattr(self.__class__.attributes, k)
                if isinstance(default_attr, types.FunctionType):
                    default_attr = default_attr()
                self.attributes[k] = default_attr

    def __checkAttributes(self):
        """Checks that required attributes have been defined,
           attributes w/default cannot be required.   Checks
           all defined attributes are legal.
        """
        for a in self.__class__.required:
            if not self.attributes.has_key(a):
                raise SchemaError,\
                    'class instance %s, missing required attribute %s'\
                    %(self.__class__, a)

        for a in self.attributes.keys():
            if a not in self.__class__.attributes.keys() + ['xmlns']:
                raise SchemaError, '%s, unknown attribute' %a


class WSDLToolsAdapter(XMLSchemaComponent):
    """WSDL Adapter to grab the attributes from the wsdl document node.
    """
    attributes = {'name':None, 'targetNamespace':None}

    def __init__(self, wsdl):
        XMLSchemaComponent.__init__(self, None)
        self.setAttributes(DOMAdapter(wsdl.document))


"""Marker Interface:  can determine something about an instances properties by using 
        the provided convenience functions.

"""
class DefinitionMarker: 
    """marker for definitions
    """
    pass

class DeclarationMarker: 
    """marker for declarations
    """
    pass

class AttributeMarker: 
    """marker for attributes
    """
    pass

class AttributeGroupMarker: 
    """marker for attribute groups
    """
    pass

class WildCardMarker: 
    """marker for wildcards
    """
    pass

class ElementMarker: 
    """marker for wildcards
    """
    pass

class ReferenceMarker: 
    """marker for references
    """
    pass

class ModelGroupMarker: 
    """marker for model groups
    """
    pass

class ExtensionMarker: 
    """marker for extensions
    """
    pass

class RestrictionMarker: 
    """marker for restrictions
    """
    facets = ['enumeration', 'length', 'maxExclusive', 'maxInclusive',\
        'maxLength', 'minExclusive', 'minInclusive', 'minLength',\
        'pattern', 'fractionDigits', 'totalDigits', 'whiteSpace']

class SimpleMarker: 
    """marker for simple type information
    """
    pass

class ComplexMarker: 
    """marker for complex type information
    """
    pass

class MarkerInterface:
    def isDefinition(self, what):
        return isinstance(what, DefinitionMarker)

    def isDeclaration(self, what):
        return isinstance(what, DeclarationMarker)

    def isAttribute(self, what):
        return isinstance(what, AttributeMarker)

    def isAttributeGroup(self, what):
        return isinstance(what, AttributeGroupMarker)

    def isReference(self, what):
        return isinstance(what, ReferenceMarker)

    def isWildCard(self, what):
        return isinstance(what, WildCardMarker)

    def isModelGroup(self, what):
        return isinstance(what, ModelGroupMarker)

    def isExtension(self, what):
        return isinstance(what, ModelGroupMarker)

    def isRestriction(self, what):
        return isinstance(what, ModelGroupMarker)

    def isSimple(self, what):
        return isinstance(what, SimpleMarker)

    def isComplex(self, what):
        return isinstance(what, ComplexMarker)


class Notation(XMLSchemaComponent):
    """<notation>
       parent:
           schema
       attributes:
           id -- ID
           name -- NCName, Required
           public -- token, Required
           system -- anyURI
       contents:
           annotation?
    """
    required = ['name', 'public']
    attributes = {'id':None, 'name':None, 'public':None, 'system':None}
    contents = {'xsd':('annotation')}

    def __init__(self):
        XMLSchemaComponent.__init__(self)
        self.annotation = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component == 'annotation' and not self.annotation:
                self.annotation = Annotation()
                self.annotation.fromDom(i)
            else:
                raise SchemaError, 'Unknown component (%s)' %(i.getTagName())


class Annotation(XMLSchemaComponent):
    """<annotation>
       parent:
           all,any,anyAttribute,attribute,attributeGroup,choice,complexContent,
           complexType,element,extension,field,group,import,include,key,keyref,
           list,notation,redefine,restriction,schema,selector,simpleContent,
           simpleType,union,unique
       attributes:
           id -- ID
       contents:
           (documentation | appinfo)*
    """
    attributes = {'id':None}
    contents = {'xsd':('documentation', 'appinfo')}

    def __init__(self):
        XMLSchemaComponent.__init__(self)
        self.content = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)
        content = []

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component == 'documentation':
                #print_debug('class %s, documentation skipped' %self.__class__, 5)
                continue
            elif component == 'appinfo':
                #print_debug('class %s, appinfo skipped' %self.__class__, 5)
                continue
            else:
                raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
        self.content = tuple(content)


    class Documentation(XMLSchemaComponent):
        """<documentation>
           parent:
               annotation
           attributes:
               source, anyURI
               xml:lang, language
           contents:
               mixed, any
        """
        attributes = {'source':None, 'xml:lang':None}
        contents = {'xsd':('mixed', 'any')}

        def __init__(self):
            XMLSchemaComponent.__init__(self)
            self.content = None

        def fromDom(self, node):
            self.setAttributes(node)
            contents = self.getContents(node)
            content = []

            for i in contents:
                component = SplitQName(i.getTagName())[1]
                if component == 'mixed':
                    #print_debug('class %s, mixed skipped' %self.__class__, 5)
                    continue
                elif component == 'any':
                    #print_debug('class %s, any skipped' %self.__class__, 5)
                    continue
                else:
                    raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
            self.content = tuple(content)


    class Appinfo(XMLSchemaComponent):
        """<appinfo>
           parent:
               annotation
           attributes:
               source, anyURI
           contents:
               mixed, any
        """
        attributes = {'source':None, 'anyURI':None}
        contents = {'xsd':('mixed', 'any')}

        def __init__(self):
            XMLSchemaComponent.__init__(self)
            self.content = None

        def fromDom(self, node):
            self.setAttributes(node)
            contents = self.getContents(node)
            content = []

            for i in contents:
                component = SplitQName(i.getTagName())[1]
                if component == 'mixed':
                    #print_debug('class %s, mixed skipped' %self.__class__, 5)
                    continue
                elif component == 'any':
                    #print_debug('class %s, any skipped' %self.__class__, 5)
                    continue
                else:
                    raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
            self.content = tuple(content)


class XMLSchemaFake:
    # This is temporary, for the benefit of WSDL until the real thing works.
    def __init__(self, element):
        self.targetNamespace = DOM.getAttr(element, 'targetNamespace')
        self.element = element

class XMLSchema(XMLSchemaComponent):
    """A schema is a collection of schema components derived from one
       or more schema documents, that is, one or more <schema> element
       information items. It represents the abstract notion of a schema
       rather than a single schema document (or other representation).

       <schema>
       parent:
           ROOT
       attributes:
           id -- ID
           version -- token
           xml:lang -- language
           targetNamespace -- anyURI
           attributeFormDefault -- 'qualified' | 'unqualified', 'unqualified'
           elementFormDefault -- 'qualified' | 'unqualified', 'unqualified'
           blockDefault -- '#all' | list of 
               ('substitution | 'extension' | 'restriction')
           finalDefault -- '#all' | list of 
               ('extension' | 'restriction' | 'list' | 'union')
        
       contents:
           ((include | import | redefine | annotation)*, 
            (attribute, attributeGroup, complexType, element, group, 
             notation, simpleType)*, annotation*)*


        attributes -- schema attributes
        imports -- import statements
        includes -- include statements
        redefines -- 
        types    -- global simpleType, complexType definitions
        elements -- global element declarations
        attr_decl -- global attribute declarations
        attr_groups -- attribute Groups
        model_groups -- model Groups
        notations -- global notations
    """
    attributes = {'id':None, 
        'version':None, 
        'xml:lang':None, 
        'targetNamespace':None,
        'attributeFormDefault':'unqualified',
        'elementFormDefault':'unqualified',
        'blockDefault':None,
        'finalDefault':None}
    contents = {'xsd':('include', 'import', 'redefine', 'annotation', 'attribute',\
                'attributeGroup', 'complexType', 'element', 'group',\
                'notation', 'simpleType', 'annotation')}
    empty_namespace = ''

    def __init__(self, parent=None): 
        """parent -- 
           instance variables:
           targetNamespace -- schema's declared targetNamespace, or empty string.
           _imported_schemas -- namespace keyed dict of schema dependencies, if 
              a schema is provided instance will not resolve import statement.
           _included_schemas -- schemaLocation keyed dict of component schemas, 
              if schema is provided instance will not resolve include statement.
           _base_url -- needed for relative URLs support, only works with URLs
               relative to initial document.
           includes -- collection of include statements
           imports -- collection of import statements
           elements -- collection of global element declarations
           types -- collection of global type definitions
           attr_decl -- collection of global attribute declarations
           attr_groups -- collection of global attribute group definitions
           model_groups -- collection of model group definitions
           notations -- collection of notations

        """
        self.targetNamespace = None
        XMLSchemaComponent.__init__(self, parent)
        self.includes = Collection(self)
        self.imports = Collection(self)
        self.elements = Collection(self)
        self.types = Collection(self)
        self.attr_decl = Collection(self)
        self.attr_groups = Collection(self)
        self.model_groups = Collection(self)
        self.notations = Collection(self)

        self._imported_schemas = {}
        self._included_schemas = {}
        self._base_url = None

    def addImportSchema(self, schema):
        """for resolving import statements in Schema instance
           schema -- schema instance
           _imported_schemas 
        """
        if not isinstance(schema, Schema):
            raise TypeError, 'expecting a Schema instance'
        if schema.targetNamespace != self.targetNamespace:
            self._imported_schemas[schema.targetNamespace]
        else:
            raise SchemaError, 'import schema bad targetNamespace'

    def addIncludeSchema(self, schemaLocation, schema):
        """for resolving include statements in Schema instance
           schemaLocation -- schema location
           schema -- schema instance
           _included_schemas 
        """
        if not isinstance(schema, Schema):
            raise TypeError, 'expecting a Schema instance'
        if not schema.targetNamespace or\
             schema.targetNamespace == self.targetNamespace:
            self._included_schemas[schemaLocation] = schema
        else:
            raise SchemaError, 'include schema bad targetNamespace'
        
    def setImportSchemas(self, schema_dict):
        """set the import schema dictionary, which is used to 
           reference depedent schemas.
        """
        self._imported_schemas = schema_dict

    def getImportSchemas(self):
        """get the import schema dictionary, which is used to 
           reference depedent schemas.
        """
        return self._imported_schemas

    def getSchemaNamespacesToImport(self):
        """returns tuple of namespaces the schema instance has declared
           itself to be depedent upon.
        """
        return tuple(self.includes.keys())

    def setIncludeSchemas(self, schema_dict):
        """set the include schema dictionary, which is keyed with 
           schemaLocation (uri).  
           This is a means of providing 
           schemas to the current schema for content inclusion.
        """
        self._included_schemas = schema_dict

    def getIncludeSchemas(self):
        """get the include schema dictionary, which is keyed with 
           schemaLocation (uri). 
        """
        return self._included_schemas

    def getBaseUrl(self):
        """get base url, used for normalizing all relative uri's 
        """
        return self._base_url

    def setBaseUrl(self, url):
        """set base url, used for normalizing all relative uri's 
        """
        self._base_url = url

    def load(self, node):
        self.setAttributes(node)
        self.targetNamespace = self.getTargetNamespace()
        contents = self.getContents(node)

        indx = 0
        num = len(contents)
        while indx < num:
            while indx < num:
                node = contents[indx]
                component = SplitQName(node.getTagName())[1]

                if component == 'include':
                    tp = self.__class__.Include(self)
                    tp.fromDom(node)
                    self.includes[tp.attributes['schemaLocation']] = tp

                    schema = tp.getSchema()
                    if schema.targetNamespace and \
                        schema.targetNamespace != self.targetNamespace:
                        raise SchemaError, 'included schema bad targetNamespace'

                    for collection in ['imports','elements','types',\
                        'attr_decl','attr_groups','model_groups','notations']:
                        for k,v in getattr(schema,collection).items():
                            if not getattr(self,collection).has_key(k):
                                setattr(self,collection,v)                             

                elif component == 'import':
                    tp = self.__class__.Import(self)
                    tp.fromDom(node)
                    if tp.attributes['namespace']:
                        if tp.attributes['namespace'] == self.targetNamespace:
                            raise SchemaError,\
                                'import and schema have same targetNamespace'
                        self.imports[tp.attributes['namespace']] = tp
                    else:
                        self.imports[self.__class__.empty_namespace] = tp
                elif component == 'redefine':
                    #print_debug('class %s, redefine skipped' %self.__class__, 5)
                    pass
                elif component == 'annotation':
                    #print_debug('class %s, annotation skipped' %self.__class__, 5)
                    pass
                else:
                    break
                indx += 1
            while indx < num:
                node = contents[indx]
                component = SplitQName(node.getTagName())[1]

                if component == 'complexType':
                    tp = ComplexType(self)
                    tp.fromDom(node)
                    self.types[tp.getAttribute('name')] = tp
                elif component == 'element':
                    tp = ElementDeclaration(self)
                    tp.fromDom(node)
                    self.elements[tp.getAttribute('name')] = tp
                elif component == 'simpleType':
                    tp = SimpleType(self)
                    tp.fromDom(node)
                    self.types[tp.getAttribute('name')] = tp
                elif component == 'group':
                    tp = ModelGroupDefinition(self)
                    tp.fromDom(node)
                    self.modelGroups[tp.getAttribute('name')] = tp
                elif component == 'notation':
                    tp = Notation(self)
                    tp.fromDom(node)
                    self.notations[tp.getAttribute('name')] = tp
                else:
                    break
                indx += 1

            while indx < num:
                node = contents[indx]
                component = SplitQName(node.getTagName())[1]

                if component == 'annotation':
                    #print_debug('class %s, annotation 2 skipped' %self.__class__, 5)
                    pass
                else:
                    break
                indx += 1


    class Import(XMLSchemaComponent):
        """<import> 
           parent:
               schema
           attributes:
               id -- ID
               namespace -- anyURI
               schemaLocation -- anyURI
           contents:
               annotation?
        """
        attributes = {'id':None,
            'namespace':None,
            'schemaLocation':None}
        contents = {'xsd':['annotation']}

        def __init__(self, parent):
            XMLSchemaComponent.__init__(self, parent)
            self.annotation = None

        def fromDom(self, node):
            self.setAttributes(node)
            contents = self.getContents(node)

            if self.attributes['namespace'] == self._parent().attributes['targetNamespace']:
                raise SchemaError, 'namespace (%s) of schema and import match'

            for i in contents:
                component = SplitQName(i.getTagName())[1]
                if component == 'annotation' and not self.annotation:
                    self.annotation = Annotation()
                    self.annotation.fromDom(i)
                else:
                    raise SchemaError, 'Unknown component (%s)' %(i.getTagName())

        def getSchema(self):
            """if schema is not defined, first look for a Schema class instance
               in parent Schema.  Else if not defined resolve schemaLocation
               and create a new Schema class instance.  
            """
            if not self._schema:
                schema = self._parent()._parent()
                self._schema = schema.getImportSchemas()[self.attributes['namespace']]
                if not self._schema:
                    url = urllib.basejoin(schema.getBaseUrl(),\
                           self.attributes['schemaLocation'])
                    reader = SchemaReader()
                    reader._imports = schema.getImportSchemas()
                    reader._includes = schema.getIncludeSchemas()
                    self._schema = reader.readFromUrl(url)
                    self._schema.setBaseUrl(url)
            return self._schema


    class Include(XMLSchemaComponent):
        """<include schemaLocation>
           parent:
               schema
           attributes:
               id -- ID
               schemaLocation -- anyURI, required
           contents:
               annotation?
        """
        required = ['schemaLocation']
        attributes = {'id':None,
            'schemaLocation':None}
        contents = {'xsd':['annotation']}

        def __init__(self, parent):
            XMLSchemaComponent.__init__(self, parent)
            self.annotation = None
            self._schema = None

        def fromDom(self, node):
            self.setAttributes(node)
            contents = self.getContents(node)

            for i in contents:
                component = SplitQName(i.getTagName())[1]
                if component == 'annotation' and not self.annotation:
                    self.annotation = Annotation()
                    self.annotation.fromDom(i)
                else:
                    raise SchemaError, 'Unknown component (%s)' %(i.getTagName())

        def getSchema(self):
            """if schema is not defined, first look for a Schema class instance
               in parent Schema.  Else if not defined resolve schemaLocation
               and create a new Schema class instance.  
            """
            if not self._schema:
                schema = self._parent()._parent()
                self._schema = schema.getIncludeSchemas(\
                    self.attributes['schemaLocation'])
                if not self._schema:
                    url = BaseUriResolver().normalize(\
                       self.attributes['schemaLocation'], schema.getBaseUrl())
                    reader = SchemaReader()
                    reader._imports = schema.getImportSchemas()
                    reader._includes = schema.getIncludeSchemas()
                    self._schema = reader.readFromUrl(url)
                    self._schema.setBaseUrl(url)
            return self._schema


class AttributeDeclaration(XMLSchemaComponent,\
                           MarkerInterface,\
                           AttributeMarker,\
                           DeclarationMarker):
    """<attribute name>
       parent: 
           schema
       attributes:
           id -- ID
           name -- NCName, required
           type -- QName
           default -- string
           fixed -- string
       contents:
           annotation?, simpleType?
    """
    required = ['name']
    attributes = {'id':None,
        'name':None,
        'type':None,
        'default':None,
        'fixed':None}
    contents = {'xsd':['annotation','simpleType']}

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.annotation = None
        self.content = None

    def fromDom(self, node):
        """ No list or union support
        """
        self.setAttributes(node)
        contents = self.getContents(node)

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component == 'annotation' and not self.annotation:
                self.annotation = Annotation(self)
                self.annotation.fromDom(i)
            elif component == 'simpleType':
                self.content = SimpleType(self)
                self.content.fromDom(i)
            else:
                raise SchemaError, 'Unknown component (%s)' %(i.getTagName())


class LocalAttributeDeclaration(AttributeDeclaration,\
                                MarkerInterface,\
                                AttributeMarker,\
                                DeclarationMarker):
    """<attribute name>
       parent: 
           complexType, restriction, extension, attributeGroup
       attributes:
           id -- ID
           name -- NCName,  required
           type -- QName
           form -- ('qualified' | 'unqualified'), schema.attributeFormDefault
           use -- ('optional' | 'prohibited' | 'required'), optional
           default -- string
           fixed -- string
       contents:
           annotation?, simpleType?
    """
    required = ['name']
    attributes = {'id':None, 
        'name':None,
        'type':None,
        'form':lambda: self._parent.parent().getAttributeFormDefault(),
        'use':'optional',
        'default':None,
        'fixed':None}
    contents = {'xsd':['annotation','simpleType']}

    def __init__(self, parent):
        AttributeDeclaration.__init__(self, parent)
        self.annotation = None
        self.content = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component == 'annotation' and not self.annotation:
                self.annotation = Annotation(self)
                self.annotation.fromDom(i)
            elif component == 'simpleType':
                self.content = SimpleType(self)
                self.content.fromDom(i)
            else:
                raise SchemaError, 'Unknown component (%s)' %(i.getTagName())


class AttributeWildCard(XMLSchemaComponent,\
                        MarkerInterface,\
                        AttributeMarker,\
                        DeclarationMarker,\
                        WildCardMarker):
    """<anyAttribute>
       parents: 
           complexType, restriction, extension, attributeGroup
       attributes:
           id -- ID
           namespace -- '##any' | '##other' | 
                        (anyURI* | '##targetNamespace' | '##local'), ##any
           processContents -- 'lax' | 'skip' | 'strict', strict
       contents:
           annotation?
    """
    attributes = {'id':None, 
        'namespace':'##any',
        'processContents':'strict'}
    contents = {'xsd':['annotation']}

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.annotation = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component == 'annotation' and not self.annotation:
                self.annotation = Annotation()
                self.annotation.fromDom(i)
            else:
                raise SchemaError, 'Unknown component (%s)' %(i.getTagName())


class AttributeReference(XMLSchemaComponent,\
                         MarkerInterface,\
                         AttributeMarker,\
                         ReferenceMarker):
    """<attribute ref>
       parents: 
           complexType, restriction, extension, attributeGroup
       attributes:
           id -- ID
           ref -- QName, required
           use -- ('optional' | 'prohibited' | 'required'), optional
           default -- string
           fixed -- string
       contents:
           annotation?
    """
    required = ['ref']
    attributes = {'id':None, 
        'ref':None,
        'use':'optional',
        'default':None,
        'fixed':None}
    contents = {'xsd':['annotation']}

    def __init__(self, schemaEval):
        XMLSchemaComponent.__init__(self)
        self.annotation = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component == 'annotation' and not self.annotation:
                self.annotation = Annotation()
                self.annotation.fromDom(i)
            else:
                raise SchemaError, 'Unknown component (%s)' %(i.getTagName())


class AttributeGroupDefinition(XMLSchemaComponent,\
                               MarkerInterface,\
                               AttributeGroupMarker,\
                               DefinitionMarker):
    """<attributeGroup name>
       parents: 
           schema, redefine
       attributes:
           id -- ID
           name -- NCName,  required
       contents:
           annotation?
    """
    required = ['name']
    attributes = {'id':None, 
        'name':None}
    contents = {'xsd':['annotation']}

    def __init__(self, schemaEval):
        XMLSchemaComponent.__init__(self)
        self.annotation = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component == 'annotation' and not self.annotation:
                self.annotation = Annotation()
                self.annotation.fromDom(i)
            else:
                raise SchemaError, 'Unknown component (%s)' %(i.getTagName())


class AttributeGroupReference(XMLSchemaComponent,\
                              MarkerInterface,\
                              AttributeGroupMarker,\
                              ReferenceMarker):
    """<attributeGroup ref>
       parents: 
           complexType, restriction, extension, attributeGroup
       attributes:
           id -- ID
           ref -- QName, required
       contents:
           annotation?
    """
    required = ['ref']
    attributes = {'id':None, 
        'ref':None}
    contents = {'xsd':['annotation']}

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.annotation = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component == 'annotation' and not self.annotation:
                self.annotation = Annotation()
                self.annotation.fromDom(i)
            else:
                raise SchemaError, 'Unknown component (%s)' %(i.getTagName())



######################################################
# Elements
#####################################################
class IdentityConstrants(XMLSchemaComponent):
    """Allow one to uniquely identify nodes in a document and ensure the 
       integrity of references between them.

       attributes -- dictionary of attributes
       selector -- XPath to selected nodes
       fields -- list of XPath to key field
    """
    def __init__(self):
        XMLSchemaComponent.__init__(self)
        self.selector = None
        self.fields = None
        self.annotation = None

    def fromDom(node):
        self.setAttributes(node)
        contents = self.getContents(node)
        fields = []

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component in self.__class__.contents['xsd']:
                if component == 'annotation' and not self.annotation:
                    self.annotation = Annotation()
                    self.annotation.fromDom(i)
                elif component == 'selector':
                    self.selector = self.Selector()
                    self.selector.fromDom(i)
                    continue
                elif component == 'field':
                    fields.append(self.Field())
                    fields[-1].fromDom(i)
                    continue
                else:
                    raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
            else:
                raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
            self.fields = tuple(fields)


    class Constraint(XMLSchemaComponent):
        def __init__(self):
            XMLSchemaComponent.__init__(self)
            self.annotation = None

        def fromDom(node):
            self.setAttributes(node)
            contents = self.getContents(node)

            for i in contents:
                component = SplitQName(i.getTagName())[1]
                if component in self.__class__.contents['xsd']:
                    if component == 'annotation' and not self.annotation:
                        self.annotation = Annotation()
                        self.annotation.fromDom(i)
                    else:
                        raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
                else:
                    raise SchemaError, 'Unknown component (%s)' %(i.getTagName())

    class Selector(Constraint):
        """<selector xpath>
           parent: 
               unique, key, keyref
           attributes:
               id -- ID
               xpath -- XPath subset,  required
           contents:
               annotation?
        """
        required = ['xpath']
        attributes = {'id':None, 
            'xpath':None}
        contents = {'xsd':['annotation']}

    class Field(Constraint): 
        """<field xpath>
           parent: 
               unique, key, keyref
           attributes:
               id -- ID
               xpath -- XPath subset,  required
           contents:
               annotation?
        """
        required = ['xpath']
        attributes = {'id':None, 
            'xpath':None}
        contents = {'xsd':['annotation']}


class Unique(IdentityConstrants):
    """<unique name> Enforce fields are unique w/i a specified scope.

       parent: 
           element
       attributes:
           id -- ID
           name -- NCName,  required
       contents:
           annotation?, selector, field+
    """
    required = ['name']
    attributes = {'id':None, 
        'name':None}
    contents = {'xsd':['annotation', 'selector', 'field']}


class Key(IdentityConstrants):
    """<key name> Enforce fields are unique w/i a specified scope, and all
           field values are present w/i document.  Fields cannot
           be nillable.

       parent: 
           element
       attributes:
           id -- ID
           name -- NCName,  required
       contents:
           annotation?, selector, field+
    """
    required = ['name']
    attributes = {'id':None, 
        'name':None}
    contents = {'xsd':['annotation', 'selector', 'field']}


class KeyRef(IdentityConstrants):
    """<keyref name refer> Ensure a match between two sets of values in an 
           instance.
       parent: 
           element
       attributes:
           id -- ID
           name -- NCName,  required
           refer -- QName,  required
       contents:
           annotation?, selector, field+
    """
    required = ['name', 'refer']
    attributes = {'id':None, 
        'name':None,
        'refer':None}
    contents = {'xsd':['annotation', 'selector', 'field']}


class ElementDeclaration(XMLSchemaComponent,\
                         MarkerInterface,\
                         ElementMarker,\
                         DeclarationMarker):
    """<element name>
       parents:
           schema
       attributes:
           id -- ID
           name -- NCName,  required
           type -- QName
           default -- string
           fixed -- string
           nillable -- boolean,  false
           abstract -- boolean,  false
           substitutionGroup -- QName
           block -- ('#all' | ('substition' | 'extension' | 'restriction')*), 
               schema.blockDefault 
           final -- ('#all' | ('extension' | 'restriction')*), 
               schema.finalDefault 
       contents:
           annotation?, (simpleType,complexType)?, (key | keyref | unique)*
           
    """
    required = ['name']
    attributes = {'id':None, 
        'name':None,
        'type':None,
        'default':None,
        'fixed':None,
        'nillable':0,
        'abstract':0,
        'block':lambda: self.parent.parent().getBlockDefault(),
        'final':lambda: self.parent.parent().getFinalDefault()}
    contents = {'xsd':['annotation', 'simpleType', 'complexType', 'key',\
        'keyref', 'unique']}

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.annotation = None
        self.content = None
        self.constraints = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)
        constraints = []

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component in self.__class__.contents['xsd']:
                if component == 'annotation' and not self.annotation:
                    self.annotation = Annotation(self)
                    self.annotation.fromDom(i)
                elif component == 'simpleType' and not self.content:
	            self.content = AnonymousSimpleType(self)
                    self.content.fromDom(i)
                elif component == 'complexType' and not self.content:
	            self.content = LocalComplexType(self)
                    self.content.fromDom(i)
                elif component == 'key':
	            constraints.append(Key(self))
	            constraints[-1].fromDom(i)
                elif component == 'keyref':
	            constraints.append(KeyRef(self))
	            constraints[-1].fromDom(i)
                elif component == 'unique':
	            constraints.append(Unique(self))
	            constraints[-1].fromDom(i)
                else:
	            raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
            else:
	        raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
        self.constraints = tuple(constraints)


class LocalElementDeclaration(ElementDeclaration,\
                              MarkerInterface,\
                              ElementMarker,\
                              DeclarationMarker):
    """<element>
       parents:
           all, choice, sequence
       attributes:
           id -- ID
           name -- NCName,  required
           form -- ('qualified' | 'unqualified'), schema.elementFormDefault
           type -- QName
           minOccurs -- Whole Number, 1
           maxOccurs -- (Whole Number | 'unbounded'), 1
           default -- string
           fixed -- string
           nillable -- boolean,  false
           block -- ('#all' | ('extension' | 'restriction')*), schema.blockDefault 
       contents:
           annotation?, (simpleType,complexType)?, (key | keyref | unique)*
    """
    required = ['name']
    attributes = {'id':None, 
        'name':None,
        'form':lambda: self._parent.parent().getElementFormDefault(),
        'type':None,
        'minOccurs':'1',
        'maxOccurs':'1',
        'default':None,
        'fixed':None,
        'nillable':0,
        'abstract':0,
        'block':lambda: self.parent.parent().getBlockDefault()}
    contents = {'xsd':['annotation', 'simpleType', 'complexType', 'key',\
        'keyref', 'unique']}


class ElementReference(ElementDeclaration,\
                       MarkerInterface,\
                       ElementMarker,\
                       ReferenceMarker):
    """<element ref>
       parents: 
           all, choice, sequence
       attributes:
           id -- ID
           ref -- QName, required
           minOccurs -- Whole Number, 1
           maxOccurs -- (Whole Number | 'unbounded'), 1
       contents:
           annotation?
    """
    required = ['ref']
    attributes = {'id':None, 
        'ref':None,
        'minOccurs':'1',
        'maxOccurs':'1'}
    contents = {'xsd':['annotation']}

 
class ElementWildCard(LocalElementDeclaration,\
                      MarkerInterface,\
                      ElementMarker,\
                      DeclarationMarker,\
                      WildCardMarker):
    """<any>
       parents: 
           choice, sequence
       attributes:
           id -- ID
           minOccurs -- Whole Number, 1
           maxOccurs -- (Whole Number | 'unbounded'), 1
           namespace -- '##any' | '##other' | 
                        (anyURI* | '##targetNamespace' | '##local'), ##any
           processContents -- 'lax' | 'skip' | 'strict', strict
       contents:
           annotation?
    """
    required = []
    attributes = {'id':None, 
        'minOccurs':'1',
        'maxOccurs':'1',
        'namespace':'##any',
        'processContents':'strict'}
    contents = {'xsd':['annotation']}


######################################################
# Model Groups
#####################################################
class Sequence(XMLSchemaComponent,\
               MarkerInterface,\
               ModelGroupMarker):
    """<sequence>
       parents: 
           complexType, extension, restriction, group, choice, sequence
       attributes:
           id -- ID
           minOccurs -- Whole Number, 1
           maxOccurs -- (Whole Number | 'unbounded'), 1

       contents:
           annotation?, (element | group | choice | sequence | any)*
    """
    attributes = {'id':None, 
        'minOccurs':'1',
        'maxOccurs':'1'}
    contents = {'xsd':['annotation', 'element', 'group', 'choice', 'sequence',\
         'any']}

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.annotation = None
        self.content = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)
        content = []

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component in self.__class__.contents['xsd']:
                if component == 'annotation' and not self.annotation:
                    self.annotation = Annotation()
                    self.annotation.fromDom(i)
                    continue
                elif component == 'element':
                    if i.hasattr('ref'):
	                content.append(ElementReference(self))
                    else:
	                content.append(LocalElementDeclaration(self))
                elif component == 'group':
	            content.append(ModelGroupReference(self))
                elif component == 'choice':
	            content.append(Choice(self))
                elif component == 'sequence':
	            content.append(Sequence(self))
                elif component == 'any':
	            content.append(ElementWildCard(self))
                else:
	            raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
                content[-1].fromDom(i)
            else:
	        raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
        self.content = tuple(content)


class All(XMLSchemaComponent,\
          MarkerInterface,\
          ModelGroupMarker):
    """<all>
       parents: 
           complexType, extension, restriction, group
       attributes:
           id -- ID
           minOccurs -- '0' | '1', 1
           maxOccurs -- '1', 1

       contents:
           annotation?, element*
    """
    attributes = {'id':None, 
        'minOccurs':'1',
        'maxOccurs':'1'}
    contents = {'xsd':['annotation', 'element']}

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.annotation = None
        self.content = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)
        content = []

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component in self.__class__.contents['xsd']:
                if component == 'annotation' and not self.annotation:
                    self.annotation = Annotation()
                    self.annotation.fromDom(i)
                    continue
                elif component == 'element':
                    if i.hasattr('ref'):
	                content.append(ElementReference())
                    else:
	                content.append(LocalElementDeclaration())
                else:
	            raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
                content[-1].fromDom(i)
            else:
	        raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
        self.content = tuple(content)


class Choice(XMLSchemaComponent,\
             MarkerInterface,\
             ModelGroupMarker):
    """<choice>
       parents: 
           complexType, extension, restriction, group, choice, sequence
       attributes:
           id -- ID
           minOccurs -- Whole Number, 1
           maxOccurs -- (Whole Number | 'unbounded'), 1

       contents:
           annotation?, (element | group | choice | sequence | any)*
    """
    attributes = {'id':None, 
        'minOccurs':'1',
        'maxOccurs':'1'}
    contents = {'xsd':['annotation', 'element', 'group', 'choice', 'sequence',\
         'any']}

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.annotation = None
        self.content = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)
        content = []

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component in self.__class__.contents['xsd']:
                if component == 'annotation' and not self.annotation:
                    self.annotation = Annotation()
                    self.annotation.fromDom(i)
                    continue
                elif component == 'element':
                    if i.hasattr('ref'):
	                content.append(ElementReference())
                    else:
	                content.append(LocalElementDeclaration())
                elif component == 'group':
	            content.append(ModelGroupReference())
                elif component == 'choice':
	            content.append(Choice())
                elif component == 'sequence':
	            content.append(Sequence())
                elif component == 'any':
	            content.append(ElementWildCard())
                else:
	            raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
                content[-1].fromDom(i)
            else:
	        raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
        self.content = tuple(content)


class ModelGroupDefinition(XMLSchemaComponent,\
                           MarkerInterface,\
                           ModelGroupMarker,\
                           DefinitionMarker):
    """<group name>
       parents:
           redefine, schema
       attributes:
           id -- ID
           name -- NCName,  required

       contents:
           annotation?, (all | choice | sequence)?
    """
    required = ['name']
    attributes = {'id':None, 
        'name':None}
    contents = {'xsd':['annotation', 'all', 'choice', 'sequence']}

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.annotation = None
        self.content = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component in self.__class__.contents['xsd']:
                if component == 'annotation' and not self.annotation:
                    self.annotation = Annotation()
                    self.annotation.fromDom(i)
                    continue
                elif component == 'all' and not self.content:
                    self.content = All()
                elif component == 'choice' and not self.content:
                    self.content = Choice()
                elif component == 'sequence' and not self.content:
                    self.content = Sequence()
                else:
	            raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
                self.content.fromDom(i)
            else:
	        raise SchemaError, 'Unknown component (%s)' %(i.getTagName())


class ModelGroupReference(XMLSchemaComponent,\
                          MarkerInterface,\
                          ModelGroupMarker,\
                          ReferenceMarker):
    """<group ref>
       parents:
           choice, complexType, extension, restriction, sequence
       attributes:
           id -- ID
           ref -- NCName,  required

       contents:
           annotation?
    """
    required = ['ref']
    attributes = {'id':None, 
        'ref':None}
    contents = {'xsd':['annotation']}

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.annotation = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component in self.__class__.contents['xsd']:
                if component == 'annotation' and not self.annotation:
                    self.annotation = Annotation()
                    self.annotation.fromDom(i)
                else:
	            raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
            else:
	        raise SchemaError, 'Unknown component (%s)' %(i.getTagName())



class ComplexType(XMLSchemaComponent,\
                  MarkerInterface,\
                  DefinitionMarker,\
                  ComplexMarker):
    """<complexType name>
       parents:
           redefine, schema
       attributes:
           id -- ID
           name -- NCName,  required
           mixed -- boolean, false
           abstract -- boolean,  false
           block -- ('#all' | ('extension' | 'restriction')*), schema.blockDefault 
           final -- ('#all' | ('extension' | 'restriction')*), schema.finalDefault 

       contents:
           annotation?, (simpleContent | complexContent | 
           ((group | all | choice | sequence)?, (attribute | attributeGroup)*, anyAttribute?))
    """
    required = ['name']
    attributes = {'id':None, 
        'name':None,
        'mixed':0,
        'abstract':0,
        'block':lambda: self._parent.parent().getBlockDefault(),
        'final':lambda: self._parent.parent().getFinalDefault()}
    contents = {'xsd':['annotation', 'simpleContent', 'complexContent',\
        'group', 'all', 'choice', 'sequence', 'attribute', 'attributeGroup',\
        'anyAttribute', 'any']}

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.annotation = None
        self.content = None
        self.attr_content = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)
      
        indx = 0
        num = len(contents)
        #XXX ugly
        if not num:
            return
        component = SplitQName(contents[indx].getTagName())[1]
        if component == 'annotation':
            self.annotation = Annotation()
            self.annotation.fromDom(contents[indx])
            indx += 1
            component = SplitQName(contents[indx].getTagName())[1]

        self.content = None
        if component == 'simpleContent':
            self.content = self.__class__.SimpleContent(self)
            self.content.fromDom(contents[indx])
        elif component == 'complexContent':
            self.content = self.__class__.ComplexContent(self)
            self.content.fromDom(contents[indx])
        else:
            if component == 'all':
                self.content = All(self)
            elif component == 'choice':
                self.content = Choice(self)
            elif component == 'sequence':
                self.content = Sequence(self)
            elif component == 'group':
                self.content = ModelGroupReference(self)

            if self.content:
                self.content.fromDom(contents[indx])
                indx += 1

            self.attr_content = []
            while indx < num:
                component = SplitQName(contents[indx].getTagName())[1]
                if component == 'attribute':
                    if contents[indx].hasattr('ref'):
                        self.attr_content.append(AttributeReference(self))
                    else:
                        self.attr_content.append(LocalAttributeDeclaration(self))
                elif component == 'attributeGroup':
                    self.attr_content.append(AttributeGroupDefinition(self))
                elif component == 'anyAttribute':
                    self.attr_content.append(AttributeWildCard(self))
                else:
	            raise SchemaError, 'Unknown component (%s)' %(contents[indx].getTagName())
                self.attr_content[-1].fromDom(contents[indx])
                indx += 1

    class _DerivedType(XMLSchemaComponent):
	def __init__(self, parent):
            XMLSchemaComponent.__init__(self, parent)
            self.annotation = None
            self.derivation = None

        def fromDom(self, node):
            self.setAttributes(node)
            contents = self.getContents(node)

            for i in contents:
                component = SplitQName(i.getTagName())[1]
                if component in self.__class__.contents['xsd']:
                    if component == 'annotation' and not self.annotation:
                        self.annotation = Annotation()
                        self.annotation.fromDom(i)
                        continue
                    elif component == 'restriction' and not self.derivation:
                        self.derivation = self.__class__.Restriction(self)
                    elif component == 'extension' and not self.derivation:
                        self.derivation = self.__class__.Extension(self)
                    else:
	                raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
                else:
	            raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
                self.derivation.fromDom(i)

    class ComplexContent(_DerivedType,\
                         MarkerInterface,\
                         ComplexMarker):
        """<complexContent>
           parents:
               complexType
           attributes:
               id -- ID
               mixed -- boolean, false

           contents:
               annotation?, (restriction | extension)
        """
        attributes = {'id':None, 
            'mixed':0 }
        contents = {'xsd':['annotation', 'restriction', 'extension']}

        class _DerivationBase(XMLSchemaComponent):
            """<extension>,<restriction>
               parents:
                   complexContent
               attributes:
                   id -- ID
                   base -- QName, required

               contents:
                   annotation?, (group | all | choice | sequence)?, 
                       (attribute | attributeGroup)*, anyAttribute?
            """
            required = ['base']
            attributes = {'id':None, 
                'base':None }
            contents = {'xsd':['annotation', 'group', 'all', 'choice',\
                'sequence', 'attribute', 'attributeGroup', 'anyAttribute']}

            def fromDom(self, node):
                self.setAttributes(node)
                contents = self.getContents(node)

                indx = 0
                num = len(contents)
                #XXX ugly
                if not num:
                    return
                component = SplitQName(contents[indx].getTagName())[1]
                if component == 'annotation':
                    self.annotation = Annotation()
                    self.annotation.fromDom(contents[indx])
                    indx += 1
                    component = SplitQName(contents[indx].getTagName())[1]

                if component == 'all':
                    self.content = All(self)
                elif component == 'choice':
                    self.content = Choice(self)
                elif component == 'sequence':
                    self.content = Sequence(self)
                elif component == 'group':
                    self.content = ModelGroupReference(self)
                else:
	            raise SchemaError, 'Unknown component (%s)' %(contents[indx].getTagName())

                self.content.fromDom(contents[indx])
                indx += 1
                self.attr_content = []
                while indx < num:
                    component = SplitQName(contents[indx].getTagName())[1]
                    if component == 'attribute':
                        if contents[indx].hasattr('ref'):
                            self.attr_content.append(AttributeReference(self))
                        else:
                            self.attr_content.append(LocalAttributeDeclaration(self))
                    elif component == 'attributeGroup':
                        self.attr_content.append(AttributeGroupDefinition(self))
                    elif component == 'anyAttribute':
                        self.attr_content.append(AttributeWildCard(self))
                    else:
	                raise SchemaError, 'Unknown component (%s)' %(contents[indx].getTagName())
                    self.attr_content[-1].fromDom(contents[indx])
                    indx += 1

        class Extension(_DerivationBase, MarkerInterface, ExtensionMarker):
            """<extension base>
               parents:
                   complexContent
               attributes:
                   id -- ID
                   base -- QName, required

               contents:
                   annotation?, (group | all | choice | sequence)?, 
                       (attribute | attributeGroup)*, anyAttribute?
            """
            pass

        class Restriction(_DerivationBase,\
                          MarkerInterface,\
                          RestrictionMarker):
            """<restriction base>
               parents:
                   complexContent
               attributes:
                   id -- ID
                   base -- QName, required

               contents:
                   annotation?, (group | all | choice | sequence)?, 
                       (attribute | attributeGroup)*, anyAttribute?
            """
            pass


    class SimpleContent(_DerivedType,\
                        MarkerInterface,\
                        SimpleMarker):
        """<simpleContent>
           parents:
               complexType
           attributes:
               id -- ID

           contents:
               annotation?, (restriction | extension)
        """
        attributes = {'id':None}
        contents = {'xsd':['annotation', 'restriction', 'extension']}

        class Extension(XMLSchemaComponent,\
                        MarkerInterface,\
                        ExtensionMarker):
            """<extension base>
               parents:
                   simpleContent
               attributes:
                   id -- ID
                   base -- QName, required

               contents:
                   annotation?, (group | all | choice | sequence)?, 
                       (attribute | attributeGroup)*, anyAttribute?
            """
            required = ['base']
            attributes = {'id':None, 
                'base':None }
            contents = {'xsd':['annotation', 'group', 'all', 'choice',\
                'sequence', 'attribute', 'attributeGroup', 'anyAttribute']}

            def fromDom(self, node):
                self.setAttributes(node)
                contents = self.getContents(node)

                indx = 0
                num = len(contents)
                component = SplitQName(contents[indx].getTagName())[1]
                if component == 'annotation':
                    self.annotation = Annotation()
                    self.annotation.fromDom(contents[indx])
                    indx += 1
                    component = SplitQName(contents[indx].getTagName())[1]

                if component == 'all':
                    self.content = All(self)
                elif component == 'choice':
                    self.content = Choice(self)
                elif component == 'sequence':
                    self.content = Sequence(self)
                elif component == 'group':
                    self.content = ModelGroupReference(self)
                else:
	            raise SchemaError, 'Unknown component (%s)' %(contents[indx].getTagName())

                self.content.fromDom(contents[indx])
                indx += 1
                self.attr_content = []
                while indx < num:
                    component = SplitQName(contents[indx].getTagName())[1]
                    if component == 'attribute':
                        if contents[indx].hasattr('ref'):
                            self.attr_content.append(AttributeReference(self))
                        else:
                            self.attr_content.append(LocalAttributeDeclaration(self))
                    elif component == 'attributeGroup':
                        self.attr_content.append(AttributeGroupDefinition(self))
                    elif component == 'anyAttribute':
                        self.attr_content.append(AttributeWildCard(self))
                    else:
	                raise SchemaError, 'Unknown component (%s)' %(contents[indx].getTagName())
                    self.attr_content[-1].fromDom(contents[indx])
                    indx += 1


        class Restriction(XMLSchemaComponent,\
                          MarkerInterface,\
                          RestrictionMarker):
            """<restriction base>
               parents:
                   simpleContent
               attributes:
                   id -- ID
                   base -- QName, required

               contents:
                   annotation?, simpleType?, (enumeration | length | 
                   maxExclusive | maxInclusive | maxLength | minExclusive | 
                   minInclusive | minLength | pattern | fractionDigits | 
                   totalDigits | whiteSpace)*, (attribute | attributeGroup)*, 
                   anyAttribute?
            """
            required = ['base']
            attributes = {'id':None, 
                'base':None }
            contents = {'xsd':['annotation', 'simpleType', 'attribute',\
                'attributeGroup', 'anyAttribute'] + RestrictionMarker.facets}


class LocalComplexType(ComplexType):
    """<complexType>
       parents:
           element
       attributes:
           id -- ID
           mixed -- boolean, false

       contents:
           annotation?, (simpleContent | complexContent | 
           ((group | all | choice | sequence)?, (attribute | attributeGroup)*, anyAttribute?))
    """
    required = []
    attributes = {'id':None, 
        'mixed':0}
    

class SimpleType(XMLSchemaComponent,\
                 MarkerInterface,\
                 DefinitionMarker,\
                 SimpleMarker):
    """<simpleType name>
       parents:
           redefine, schema
       attributes:
           id -- ID
           name -- NCName, required
           final -- ('#all' | ('extension' | 'restriction' | 'list' | 'union')*), 
               schema.finalDefault 

       contents:
           annotation?, (restriction | list | union)
    """
    required = ['name']
    attributes = {'id':None,
        'name':None,
        'final':lambda: self._parent.parent().getFinalDefault()}
    contents = {'xsd':['annotation', 'restriction', 'list', 'union']}

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.annotation = None
        self.content = None
        self.attr_content = None

    def setType(self, qname, namespace):
        self.type = TypeDescriptionComponent(namespace, qname)
            
    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)
        for child in contents:
            component = SplitQName(child.getTagName())[1]
            if component == 'annotation':
                self.annotation = Annotation()
                self.annotation.fromDom(child)
            break
        else:
            return
        if component == 'restriction':
            self.content = self.__class__.Restriction(self)
        elif component == 'list':
            self.content = self.__class__.List(self)
        elif component == 'union':
            self.content = self.__class__.Union(self)
        else:
            raise SchemaError, 'Unknown component (%s)' %(contents[indx].getTagName())
        self.content.fromDom(child)

    class Restriction(XMLSchemaComponent,\
                      MarkerInterface,\
                      RestrictionMarker):
        """<restriction base>
           parents:
               simpleType
           attributes:
               id -- ID
               base -- QName, required or simpleType child

           contents:
               annotation?, simpleType?, (enumeration | length | 
               maxExclusive | maxInclusive | maxLength | minExclusive | 
               minInclusive | minLength | pattern | fractionDigits | 
               totalDigits | whiteSpace)*
        """
        attributes = {'id':None, 
            'base':None }
        contents = {'xsd':['annotation', 'simpleType']+RestrictionMarker.facets}

        def __init__(self, parent):
            XMLSchemaComponent.__init__(self, parent)
            self.annotation = None
            self.content = None
            self.attr_content = None

        def fromDom(self, node):
            self.setAttributes(node)
            contents = self.getContents(node)
            self.content = []
            self.attr_content = []

            for indx in range(len(contents)):
                component = SplitQName(contents[indx].getTagName())[1]
                if (component == 'annotation') and (not indx):
                    self.annotation = Annotation()
                    self.annotation.fromDom(contents[indx])
                    continue
                elif (component == 'simpleType') and (not indx or indx == 1):
                    self.content.append(SimpleType(self))
                    self.content[-1].fromDom(contents[indx])
                elif component in RestrictionMarker.facets:
                    #print_debug('%s class instance, skipping %s' %(self.__class__, component))
                    pass
                else:
                    raise SchemaError, 'Unknown component (%s)' %(i.getTagName())


    class Union(XMLSchemaComponent):
        """<union>
           parents:
               simpleType
           attributes:
               id -- ID
               memberTypes -- list of QNames, required or simpleType child.

           contents:
               annotation?, simpleType*
        """
        attributes = {'id':None, 
            'memberTypes':None }
        contents = {'xsd':['annotation', 'simpleType']}

    class List(XMLSchemaComponent):
        """<union>
           parents:
               simpleType
           attributes:
               id -- ID
               itemType -- QName, required or simpleType child.

           contents:
               annotation?, simpleType?
        """
        attributes = {'id':None, 
            'memberTypes':None }
        contents = {'xsd':['annotation', 'simpleType']}

                 
class AnonymousSimpleType(SimpleType,\
                          MarkerInterface,\
                          SimpleMarker):
    """<simpleType>
       parents:
           attribute, element, list, restriction, union
       attributes:
           id -- ID

       contents:
           annotation?, (restriction | list | union)
    """
    required = []
    attributes = {'id':None}


class Redefine:
    """<redefine>
       parents:
       attributes:

       contents:
    """
    pass

###########################
###########################
class TypeDescriptionComponent(tuple):
    """Tuple of length 2, consisting of
       a namespace and unprefixed name.
    """
    def __init__(self, args):
        """args -- (namespace, name)
           Remove the name's prefix, irrelevant.
        """
        if len(args) != 2:
            raise TypeError, 'expecting tuple (namespace, name), got %s' %args
        elif args[1].find(':') >= 0:
            args = (args[0], SplitQName(args[1])[1])
        tuple.__init__(self, args)
        return

    def getTargetNamespace(self):
        return self[0]

    def getName(self):
        return self[1]


'''
import string, types, base64, re
from Utility import DOM, Collection
from StringIO import StringIO


class SchemaReader:
    """A SchemaReader creates XMLSchema objects from urls and xml data."""

    def loadFromStream(self, file):
        """Return an XMLSchema instance loaded from a file object."""
        document = DOM.loadDocument(file)
        schema = XMLSchema()
        schema.load(document)
        return schema

    def loadFromString(self, data):
        """Return an XMLSchema instance loaded from an xml string."""
        return self.loadFromStream(StringIO(data))

    def loadFromURL(self, url):
        """Return an XMLSchema instance loaded from the given url."""
        document = DOM.loadFromURL(url)
        schema = XMLSchema()
        schema.location = url
        schema.load(document)
        return schema

    def loadFromFile(self, filename):
        """Return an XMLSchema instance loaded from the given file."""
        file = open(filename, 'rb')
        try:     schema = self.loadFromStream(file)
        finally: file.close()
        return schema

class SchemaError(Exception):
    pass

class XMLSchema:
    # This is temporary, for the benefit of WSDL until the real thing works.
    def __init__(self, element):
        self.targetNamespace = DOM.getAttr(element, 'targetNamespace')
        self.element = element

class realXMLSchema:
    """A schema is a collection of schema components derived from one
       or more schema documents, that is, one or more <schema> element
       information items. It represents the abstract notion of a schema
       rather than a single schema document (or other representation)."""
    def __init__(self):
        self.simpleTypes = Collection(self)
        self.complexTypes = Collection(self)
        self.attributes = Collection(self)
        self.elements = Collection(self)
        self.attrGroups = Collection(self)
        self.idConstraints=None
        self.modelGroups = None
        self.notations = None
        self.extensions = []

    targetNamespace = None
    attributeFormDefault = 'unqualified'
    elementFormDefault = 'unqualified'
    blockDefault = None
    finalDefault = None
    location = None
    version = None
    id = None

    def load(self, document):
        if document.nodeType == document.DOCUMENT_NODE:
            schema = DOM.getElement(document, 'schema', None, None)
        else:
            schema = document
        if schema is None:
            raise SchemaError('Missing <schema> element.')

        self.namespace = namespace = schema.namespaceURI
        if not namespace in DOM.NS_XSD_ALL:
            raise SchemaError(
                'Unknown XML schema namespace: %s.' % self.namespace
                )

        for attrname in (
            'targetNamespace', 'attributeFormDefault', 'elementFormDefault',
            'blockDefault', 'finalDefault', 'version', 'id'
            ):
            value = DOM.getAttr(schema, attrname, None, None)
            if value is not None:
                setattr(self, attrname, value)


        # Resolve imports and includes here?
##         imported = {}
##         while 1:
##             imports = []
##             for element in DOM.getElements(definitions, 'import', NS_WSDL):
##                 location = DOM.getAttr(element, 'location')
##                 if not imported.has_key(location):
##                     imports.append(element)
##             if not imports:
##                 break
##             for element in imports:
##                 self._import(document, element)
##                 imported[location] = 1

        for element in DOM.getElements(schema, None, None):
            localName = element.localName

            if not DOM.nsUriMatch(element.namespaceURI, namespace):
                self.extensions.append(element)
                continue

            elif localName == 'message':
                name = DOM.getAttr(element, 'name')
                docs = GetDocumentation(element)
                message = self.addMessage(name, docs)
                parts = DOM.getElements(element, 'part', NS_WSDL)
                message.load(parts)
                continue

    def _import(self, document, element):
        namespace = DOM.getAttr(element, 'namespace', default=None)
        location = DOM.getAttr(element, 'location', default=None)
        if namespace is None or location is None:
            raise WSDLError(
                'Invalid import element (missing namespace or location).'
                )

        # Sort-of support relative locations to simplify unit testing. The
        # WSDL specification actually doesn't allow relative URLs, so its
        # ok that this only works with urls relative to the initial document.
        location = urllib.basejoin(self.location, location)

        obimport = self.addImport(namespace, location)
        obimport._loaded = 1

        importdoc = DOM.loadFromURL(location)
        try:
            if location.find('#') > -1:
                idref = location.split('#')[-1]
                imported = DOM.getElementById(importdoc, idref)
            else:
                imported = importdoc.documentElement
            if imported is None:
                raise WSDLError(
                    'Import target element not found for: %s' % location
                    )

            imported_tns = DOM.getAttr(imported, 'targetNamespace')
            importer_tns = namespace

            if imported_tns != importer_tns:
                return

            if imported.localName == 'definitions':
                imported_nodes = imported.childNodes
            else:
                imported_nodes = [imported]
            parent = element.parentNode
            for node in imported_nodes:
                if node.nodeType != node.ELEMENT_NODE:
                    continue
                child = DOM.importNode(document, node, 1)
                parent.appendChild(child)
                child.setAttribute('targetNamespace', importer_tns)
                attrsNS = imported._attrsNS
                for attrkey in attrsNS.keys():
                    if attrkey[0] == DOM.NS_XMLNS:
                        attr = attrsNS[attrkey].cloneNode(1)
                        child.setAttributeNode(attr)
        finally:
            importdoc.unlink()


class Element:
    """Common base class for element representation classes."""
    def __init__(self, name=None, documentation=''):
        self.name = name
        self.documentation = documentation
        self.extensions = []

    def addExtension(self, item):
        self.extensions.append(item)


class SimpleTypeDefinition:
    """Represents an xml schema simple type definition."""

class ComplexTypeDefinition:
    """Represents an xml schema complex type definition."""

class AttributeDeclaration:
    """Represents an xml schema attribute declaration."""

class ElementDeclaration:
    """Represents an xml schema element declaration."""
    def __init__(self, name, type=None, targetNamespace=None):
        self.name = name

    targetNamespace = None
    annotation = None
    nillable = 0
    abstract = 0
    default = None
    fixed = None
    scope = 'global'
    type = None
    form = 0
    # Things we will not worry about for now.
    id_constraint_defs = None
    sub_group_exclude = None
    sub_group_affils = None
    disallowed_subs = None










class AttributeGroupDefinition:
    """Represents an xml schema attribute group definition."""

class IdentityConstraintDefinition:
    """Represents an xml schema identity constraint definition."""

class ModelGroupDefinition:
    """Represents an xml schema model group definition."""

class NotationDeclaration:
    """Represents an xml schema notation declaration."""

class Annotation:
    """Represents an xml schema annotation."""

class ModelGroup:
    """Represents an xml schema model group."""

class Particle:
    """Represents an xml schema particle."""

class WildCard:
    """Represents an xml schema wildcard."""

class AttributeUse:
    """Represents an xml schema attribute use."""


class ElementComponent:
    namespace = ''
    name = ''
    type = None
    form = 'qualified | unqualified'
    scope = 'global or complex def'
    constraint = ('value', 'default | fixed')
    nillable = 0
    id_constraint_defs = None
    sub_group_affil = None
    sub_group_exclusions = None
    disallowed_subs = 'substitution, extension, restriction'
    abstract = 0
    minOccurs = 1
    maxOccurs = 1
    ref = ''

class AttributeThing:
    name = ''
    namespace = ''
    typeName = ''
    typeUri = ''
    scope = 'global | local to complex def'
    constraint = ('value:default', 'value:fixed')
    use = 'optional | prohibited | required'

class ElementDataType:
    namespace = ''
    name = ''
    element_form = 'qualified | unqualified'
    attr_form = None
    type_name = ''
    type_uri = ''
    def __init__(self, name, namespace, type_name, type_uri):
        self.namespace = namespace
        self.name = name
        # type may be anonymous...
        self.type_name = type_name
        self.type_uri = type_uri

    def checkValue(self, value, context):
        # Delegate value checking to the type of the element.
        typeref = (self.type_uri, self.type_name)
        handler = context.serializer.getType(typeref)
        return handler.checkValue(value, context)

    def serialize(self, name, namespace, value, context, **kwargs):
        if context.check_values:
            self.checkValue(value, context)
        # Delegate serialization to the type of the element.
        typeref = (self.type_uri, self.type_name)
        handler = context.serializer.getType(typeref)
        return handler.serialize(self.name, self.namespace, value, context)

    def deserialize(self, element, context):
        if element_is_null(element, context):
            return None
        # Delegate deserialization to the type of the element.
        typeref = (self.type_uri, self.type_name)
        handler = context.serializer.getType(typeref)
        return handler.deserialize(element, context)



def parse_schema(data):
    targetNS = ''
    attributeFormDefault = 0
    elementFormDefault = 0
    blockDefault = ''
    finalDefault = ''
    language = None
    version = None
    id = ''
'''
