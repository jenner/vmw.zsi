# Copyright (c) 2003, The Regents of the University of California,
# through Lawrence Berkeley National Laboratory (subject to receipt of
# any required approvals from the U.S. Dept. of Energy).  All rights
# reserved. 
#
# Copyright (c) 2001 Zope Corporation and Contributors. All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.0 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.

ident = "$Id$"

import types, weakref, urllib, sys
from threading import RLock
try:
    from xml.ns import XMLNS
except ImportError:
    # ref:
    # http://cvs.sourceforge.net/viewcvs.py/pyxml/xml/xml/ns.py?view=markup
    class XMLNS:
        """XMLNS, Namespaces in XML

        XMLNS (14-Jan-1999) is a W3C Recommendation.  It is specified in
        http://www.w3.org/TR/REC-xml-names
            BASE -- the basic namespace defined by the specification
            XML -- the namespace for XML 1.0
            HTML -- the namespace for HTML4.0
        """

        BASE        = "http://www.w3.org/2000/xmlns/"
        XML         = "http://www.w3.org/XML/1998/namespace"
        HTML        = "http://www.w3.org/TR/REC-html40"

from Utility import DOM, Collection
from StringIO import StringIO
try:
    from xml.dom.ext import SplitQName
except ImportError, ex:
    def SplitQName(qname):
        l = qname.split(':')
        if len(l) == 1:
            l.insert(0, None)
        elif len(l) == 2:
            if l[0] == 'xmlns':
                l.reverse()
        else:
            return
        return tuple(l)

def GetSchema(component):
    """convience function for finding the parent XMLSchema instance.
    """
    parent = component
    while not isinstance(parent, XMLSchema):
        parent = parent._parent()
    return parent
    
class SchemaReader:
    """A SchemaReader creates XMLSchema objects from urls and xml data.
    """
    def __init__(self, domReader=None, base_url=None):
        """domReader -- class must implement DOMAdapterInterface
           base_url -- base url string
        """
        self.__base_url = base_url
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
        schema.setBaseUrl(self.__base_url)
        schema.load(reader)
        return schema
        
    def loadFromStream(self, file):
        """Return an XMLSchema instance loaded from a file object.
           file -- file object
        """
        reader = self.__readerClass()
        reader.loadDocument(file)
        schema = XMLSchema()
        schema.setBaseUrl(self.__base_url)
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
        if self.__base_url:
            url = urllib.basejoin(self.__base_url,url)
        reader.loadFromURL(url)
        schema = XMLSchema()
        schema.setBaseUrl(self.__base_url)
        schema.load(reader)
        self.__setIncludes(schema)
        self.__setImports(schema)
        return schema

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
    def hasattr(self, attr, ns=None):
        """return true if node has attribute 
           attr -- attribute to check for
           ns -- namespace of attribute, by default None
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

    def getNamespace(self, prefix):
        """returns namespace referenced by prefix.
        """
        raise NotImplementedError, 'adapter method not implemented'

    def getTagName(self):
        """returns tagName of node
        """
        raise NotImplementedError, 'adapter method not implemented'


    def getParentNode(self):
        """returns parent element in DOMAdapter or None
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

    def hasattr(self, attr, ns=None):
        """attr -- attribute 
           ns -- optional namespace, None means unprefixed attribute.
        """
        if not self.__attributes:
            self.setAttributeDictionary()
        if ns:
            return self.__attributes.get(ns,{}).has_key(attr)
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

    def getParentNode(self):
        if self.__node.parentNode.nodeType == self.__node.ELEMENT_NODE:
            return DOMAdapter(self.__node.parentNode)
        return None

    def getNamespace(self, prefix):
        """prefix -- deference namespace prefix in node's context.
           Ascends parent nodes until found.
        """
        namespace = None
        if prefix == 'xmlns':
            namespace = DOM.findDefaultNS(prefix, self.__node)
        else:
            try:
                namespace = DOM.findNamespaceURI(prefix, self.__node)
            except DOMException, ex:
                if prefix != 'xml':
                    raise SchemaError, '%s namespace not declared for %s'\
                        %(prefix, self.__node._get_tagName())
                namespace = XMLNS
        return namespace
           
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
           xmlns_key -- key for declared xmlns namespace.
           xmlns -- xmlns is special prefix for namespace dictionary
           xml -- special xml prefix for xml namespace.
    """
    required = []
    attributes = {}
    contents = {}
    xmlns_key = ''
    xmlns = 'xmlns'
    xml = 'xml'

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
        targetNamespace = 'targetNamespace'
        tns = self.attributes.get(targetNamespace)
        while not tns:
            parent = parent._parent()
            tns = parent.attributes.get(targetNamespace)
        return tns

    def getTypeDefinition(self, attribute):
        """attribute -- attribute with a QName value (eg. type).
           collection -- check types collection in parent Schema instance
        """
        return self.getQNameAttribute('types', attribute)

    def getElementDeclaration(self, attribute):
        """attribute -- attribute with a QName value (eg. element).
           collection -- check elements collection in parent Schema instance.
        """
        return self.getQNameAttribute('elements', attribute)

    def getQNameAttribute(self, collection, attribute):
        """returns object instance representing QName --> (namespace,name),
           or if does not exist return None.
           attribute -- an information item attribute, with a QName value.
           collection -- collection in parent Schema instance to search.
        """
        obj = None
        tdc = self.attributes.get(attribute)
        if tdc:
            parent = GetSchema(self)
            if parent.targetNamespace == tdc.getTargetNamespace():
                obj = getattr(parent, collection)[tdc.getName()]
            elif parent.imports.has_key(tdc.getTargetNamespace()):
                schema = parent.imports[tdc.getTargetNamespace()].getSchema()
                obj = getattr(schema, collection)[tdc.getName()]
        return obj

    def getXMLNS(self, prefix=None):
        """deference prefix or by default xmlns, returns namespace. 
        """
        parent = self
        ns = self.attributes[XMLSchemaComponent.xmlns].get(prefix or\
                XMLSchemaComponent.xmlns_key)
        while not ns:
            parent = parent._parent()
            ns = parent.attributes[XMLSchemaComponent.xmlns].get(prefix or\
                    XMLSchemaComponent.xmlns_key)
            if not ns and isinstance(parent, WSDLToolsAdapter):
                raise SchemaError, 'unknown prefix %s' %prefix
        return ns

    def getAttribute(self, attribute):
        """return requested attribute or None
        """
        return self.attributes.get(attribute)
 
    def setAttributes(self, node):
        """Sets up attribute dictionary, checks for required attributes and 
           sets default attribute values. attr is for default attribute values 
           determined at runtime.
           
           structure of attributes dictionary
               ['xmlns'][xmlns_key] --  xmlns namespace
               ['xmlns'][prefix] --  declared namespace prefix 
               [namespace][prefix] -- attributes declared in a namespace
               [attribute] -- attributes w/o prefix, default namespaces do
                   not directly apply to attributes, ie Name can't collide 
                   with QName.
        """
        self.attributes = {XMLSchemaComponent.xmlns:{}}
        for k,v in node.getAttributeDictionary().items():
            prefix,value = SplitQName(k)
            if value == XMLSchemaComponent.xmlns:
                self.attributes[value][prefix or XMLSchemaComponent.xmlns_key] = v
            elif prefix:
                ns = node.getNamespace(prefix)
                if not ns: 
                    raise SchemaError, 'no namespace for attribute prefix %s'\
                        %prefix
                if not self.attributes.has_key(ns):
                    self.attributes[ns] = {}
                elif self.attributes[ns].has_key(value):
                    raise SchemaError, 'attribute %s declared multiple times in %s'\
                        %(value, ns)
                self.attributes[ns][value] = v
            elif not self.attributes.has_key(value):
                self.attributes[value] = v
            else:
                raise SchemaError, 'attribute %s declared multiple times' %value

        self.__checkAttributes()
        self.__setAttributeDefaults()

        #set QNames
        for k in ['type', 'element', 'base', 'ref', 'substitutionGroup', 'itemType']:
            if self.attributes.has_key(k):
                prefix, value = SplitQName(self.attributes.get(k))
                self.attributes[k] = \
                    TypeDescriptionComponent((self.getXMLNS(prefix), value))

        #Union, memberTypes is a whitespace separated list of QNames 
        for k in ['memberTypes']:
            if self.attributes.has_key(k):
                qnames = self.attributes[k]
                self.attributes[k] = []
                for qname in qnames.split():
                    prefix, value = SplitQName(qname)
                    self.attributes['memberTypes'].append(\
                        TypeDescriptionComponent(\
                            (self.getXMLNS(prefix), value)))

    def getContents(self, node):
        """retrieve xsd contents
        """
        return node.getContentList(*self.__class__.contents['xsd'])

    def __setAttributeDefaults(self):
        """Looks for default values for unset attributes.  If
           class variable representing attribute is None, then
           it must be defined as an instance variable.
        """
        for k,v in self.__class__.attributes.items():
            if v and not self.attributes.has_key(k):
                if isinstance(v, types.FunctionType):
                    self.attributes[k] = v(self)
                else:
                    self.attributes[k] = v

    def __checkAttributes(self):
        """Checks that required attributes have been defined,
           attributes w/default cannot be required.   Checks
           all defined attributes are legal, attribute 
           references are not subject to this test.
        """
        for a in self.__class__.required:
            if not self.attributes.has_key(a):
                raise SchemaError,\
                    'class instance %s, missing required attribute %s'\
                    %(self.__class__, a)

        for a in self.attributes.keys():
            if (a != XMLSchemaComponent.xmlns) and\
                (a not in self.__class__.attributes.keys()) and not\
                (self.isAttribute() and self.isReference()):
                raise SchemaError, '%s, unknown attribute' %a


class WSDLToolsAdapter(XMLSchemaComponent):
    """WSDL Adapter to grab the attributes from the wsdl document node.
    """
    attributes = {'name':None, 'targetNamespace':None}

    def __init__(self, wsdl):
        #XMLSchemaComponent.__init__(self, None)
        XMLSchemaComponent.__init__(self, parent=wsdl)
        self.setAttributes(DOMAdapter(wsdl.document))

    def getImportSchemas(self):
        """returns WSDLTools.WSDL types Collection
        """
        return self._parent().types

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
    def isDefinition(self):
        return isinstance(self, DefinitionMarker)

    def isDeclaration(self):
        return isinstance(self, DeclarationMarker)

    def isAttribute(self):
        return isinstance(self, AttributeMarker)

    def isAttributeGroup(self):
        return isinstance(self, AttributeGroupMarker)

    def isElement(self):
        return isinstance(self, ElementMarker)

    def isReference(self):
        return isinstance(self, ReferenceMarker)

    def isWildCard(self):
        return isinstance(self, WildCardMarker)

    def isModelGroup(self):
        return isinstance(self, ModelGroupMarker)

    def isExtension(self):
        return isinstance(self, ExtensionMarker)

    def isRestriction(self):
        return isinstance(self, RestrictionMarker)

    def isSimple(self):
        return isinstance(self, SimpleMarker)

    def isComplex(self):
        return isinstance(self, ComplexMarker)


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

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.annotation = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component == 'annotation' and not self.annotation:
                self.annotation = Annotation(self)
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

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
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

        def __init__(self, parent):
            XMLSchemaComponent.__init__(self, parent)
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

        def __init__(self, parent):
            XMLSchemaComponent.__init__(self, parent)
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
        f = lambda k: k.attributes['name']
        ns = lambda k: k.attributes['namespace']
        sl = lambda k: k.attributes['schemaLocation']
        self.includes = Collection(self, key=sl)
        self.imports = Collection(self, key=ns)
        self.elements = Collection(self, key=f)
        self.types = Collection(self, key=f)
        self.attr_decl = Collection(self, key=f)
        self.attr_groups = Collection(self, key=f)
        self.model_groups = Collection(self, key=f)
        self.notations = Collection(self, key=f)

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

    def getElementFormDefault(self):
        """return elementFormDefault attribute
        """
        return self.attributes.get('elementFormDefault')

    def getAttributeFormDefault(self):
        """return attributeFormDefault attribute
        """
        return self.attributes.get('attributeFormDefault')

    def getBlockDefault(self):
        """return blockDefault attribute
        """
        return self.attributes.get('blockDefault')

    def getFinalDefault(self):
        """return finalDefault attribute 
        """
        return self.attributes.get('finalDefault')

    def load(self, node):
        pnode = node.getParentNode()
        if pnode:
            pname = SplitQName(pnode.getTagName())[1]
            if pname == 'types':
                attributes = {}
                self.setAttributes(pnode)
                attributes.update(self.attributes)
                self.setAttributes(node)
                for k,v in attributes['xmlns'].items():
                    if not self.attributes['xmlns'].has_key(k):
                        self.attributes['xmlns'][k] = v
            else:
                self.setAttributes(node)
        else:
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
                                v._parent = weakref.ref(self)
                                getattr(self,collection)[k] = v

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

            # (attribute, attributeGroup, complexType, element, group, 
            # notation, simpleType)*, annotation*)*
            while indx < num:
                node = contents[indx]
                component = SplitQName(node.getTagName())[1]

                if component == 'attribute':
                    tp = AttributeDeclaration(self)
                    tp.fromDom(node)
                    self.attr_decl[tp.getAttribute('name')] = tp
                elif component == 'attributeGroup':
                    tp = AttributeGroupDefinition(self)
                    tp.fromDom(node)
                    self.attr_groups[tp.getAttribute('name')] = tp
                elif component == 'complexType':
                    tp = ComplexType(self)
                    tp.fromDom(node)
                    self.types[tp.getAttribute('name')] = tp
                elif component == 'element':
                    tp = ElementDeclaration(self)
                    tp.fromDom(node)
                    self.elements[tp.getAttribute('name')] = tp
                elif component == 'group':
                    tp = ModelGroupDefinition(self)
                    tp.fromDom(node)
                    self.model_groups[tp.getAttribute('name')] = tp
                elif component == 'notation':
                    tp = Notation(self)
                    tp.fromDom(node)
                    self.notations[tp.getAttribute('name')] = tp
                elif component == 'simpleType':
                    tp = SimpleType(self)
                    tp.fromDom(node)
                    self.types[tp.getAttribute('name')] = tp
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


    class Import(XMLSchemaComponent, MarkerInterface):
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
            self._schema = None

        def fromDom(self, node):
            self.setAttributes(node)
            contents = self.getContents(node)

            if self.attributes['namespace'] == self._parent().attributes['targetNamespace']:
                raise SchemaError, 'namespace of schema and import match'

            for i in contents:
                component = SplitQName(i.getTagName())[1]
                if component == 'annotation' and not self.annotation:
                    self.annotation = Annotation(self)
                    self.annotation.fromDom(i)
                else:
                    raise SchemaError, 'Unknown component (%s)' %(i.getTagName())

        def getSchema(self):
            """if schema is not defined, first look for a Schema class instance
               in parent Schema.  Else if not defined resolve schemaLocation
               and create a new Schema class instance, and keep a hard reference. 
            """
            if not self._schema:
                ns = self.attributes['namespace']
                schema = self._parent().getImportSchemas().get(ns)
                if not schema and self._parent()._parent:
                    schema = self._parent()._parent().getImportSchemas().get(ns)
                if not schema:
                    if not self.attributes.has_key('schemaLocation'):
                        raise SchemaError, 'namespace(%s) is unknown' %ns
                    base_url = self._parent().getBaseUrl()
                    reader = SchemaReader(base_url=base_url)
                    reader._imports = self._parent().getImportSchemas()
                    reader._includes = self._parent().getIncludeSchemas()
                    self._schema = reader.loadFromURL(url)
            return self._schema or schema


    class Include(XMLSchemaComponent, MarkerInterface):
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
                    self.annotation = Annotation(self)
                    self.annotation.fromDom(i)
                else:
                    raise SchemaError, 'Unknown component (%s)' %(i.getTagName())

        def getSchema(self):
            """if schema is not defined, first look for a Schema class instance
               in parent Schema.  Else if not defined resolve schemaLocation
               and create a new Schema class instance.  
            """
            if not self._schema:
                #schema = self._parent()._parent()
                schema = self._parent()
                #self._schema = schema.getIncludeSchemas(\
                #    self.attributes['schemaLocation'])
                self._schema = schema.getIncludeSchemas().get(\
                                   self.attributes['schemaLocation']
                                   )
                if not self._schema:
                    url = self.attributes['schemaLocation']
                    reader = SchemaReader(base_url=schema.getBaseUrl())
                    reader._imports = schema.getImportSchemas()
                    reader._includes = schema.getIncludeSchemas()
                    self._schema = reader.loadFromURL(url)
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
                self.content = AnonymousSimpleType(self)
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
        'form':lambda self: GetSchema(self).getAttributeFormDefault(),
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
                self.content = AnonymousSimpleType(self)
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
                self.annotation = Annotation(self)
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

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.annotation = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component == 'annotation' and not self.annotation:
                self.annotation = Annotation(self)
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
           annotation?, (attribute | attributeGroup)*, anyAttribute?
    """
    required = ['name']
    attributes = {'id':None, 
        'name':None}
    contents = {'xsd':['annotation']}

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.annotation = None
        self.attr_content = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)
        content = []

        for indx in range(len(contents)):
            component = SplitQName(i.getTagName())[1]
            if (component == 'annotation') and (not indx):
                self.annotation = Annotation(self)
                self.annotation.fromDom(contents[indx])
            elif (component == 'attribute'):
                if contents[indx].hasattr('name'):
                    content.append(AttributeDeclaration())
                elif contents[indx].hasattr('ref'):
                    content.append(AttributeReference())
                else:
                    raise SchemaError, 'Unknown attribute type'
                content[-1].fromDom(contents[indx])
            elif (component == 'attributeGroup'):
                content.append(AttributeGroupReference())
                content[-1].fromDom(contents[indx])
            elif (component == 'anyAttribute') and (len(contents) == x+1):
                content.append(AttributeWildCard())
                content[-1].fromDom(contents[indx])
            else:
                raise SchemaError, 'Unknown component (%s)' %(i.getTagName())

        self.attr_content = tuple(content)

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
                self.annotation = Annotation(self)
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
    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.selector = None
        self.fields = None
        self.annotation = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)
        fields = []

        for i in contents:
            component = SplitQName(i.getTagName())[1]
            if component in self.__class__.contents['xsd']:
                if component == 'annotation' and not self.annotation:
                    self.annotation = Annotation(self)
                    self.annotation.fromDom(i)
                elif component == 'selector':
                    self.selector = self.Selector(self)
                    self.selector.fromDom(i)
                    continue
                elif component == 'field':
                    fields.append(self.Field(self))
                    fields[-1].fromDom(i)
                    continue
                else:
                    raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
            else:
                raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
            self.fields = tuple(fields)


    class Constraint(XMLSchemaComponent):
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
                        self.annotation = Annotation(self)
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
        'block':lambda self: self._parent().getBlockDefault(),
        'final':lambda self: self._parent().getFinalDefault()}
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


class LocalElementDeclaration(ElementDeclaration):
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
        'form':lambda self: GetSchema(self).getElementFormDefault(),
        'type':None,
        'minOccurs':'1',
        'maxOccurs':'1',
        'default':None,
        'fixed':None,
        'nillable':0,
        'abstract':0,
        'block':lambda self: GetSchema(self).getBlockDefault()}
    contents = {'xsd':['annotation', 'simpleType', 'complexType', 'key',\
        'keyref', 'unique']}


class ElementReference(XMLSchemaComponent,\
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

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.annotation = None
 
    def fromDom(self, node):
        self.annotation = None
        self.setAttributes(node)
        for i in self.getContents(node):
            component = SplitQName(i.getTagName())[1]
            if component in self.__class__.contents['xsd']:
                if component == 'annotation' and not self.annotation:
                    self.annotation = Annotation(self)
                    self.annotation.fromDom(i)
                else:
	            raise SchemaError, 'Unknown component (%s)' %(i.getTagName())


class ElementWildCard(LocalElementDeclaration,\
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

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.annotation = None

    def fromDom(self, node):
        self.annotation = None
        self.setAttributes(node)
        for i in self.getContents(node):
            component = SplitQName(i.getTagName())[1]
            if component in self.__class__.contents['xsd']:
                if component == 'annotation' and not self.annotation:
                    self.annotation = Annotation(self)
                    self.annotation.fromDom(i)
                else:
	            raise SchemaError, 'Unknown component (%s)' %(i.getTagName())


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
                    self.annotation = Annotation(self)
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
                    self.annotation = Annotation(self)
                    self.annotation.fromDom(i)
                    continue
                elif component == 'element':
                    if i.hasattr('ref'):
	                content.append(ElementReference(self))
                    else:
	                content.append(LocalElementDeclaration(self))
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
                    self.annotation = Annotation(self)
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
                    self.content = All(self)
                elif component == 'choice' and not self.content:
                    self.content = Choice(self)
                elif component == 'sequence' and not self.content:
                    self.content = Sequence(self)
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
                    self.annotation = Annotation(self)
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
        'block':lambda self: self._parent().getBlockDefault(),
        'final':lambda self: self._parent().getFinalDefault()}
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
            self.annotation = Annotation(self)
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
                    self.attr_content.append(AttributeGroupReference(self))
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
                        self.annotation = Annotation(self)
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
                    self.annotation = Annotation(self)
                    self.annotation.fromDom(contents[indx])
                    indx += 1
                    component = SplitQName(contents[indx].getTagName())[1]

                if component == 'all':
                    self.content = All(self)
                    self.content.fromDom(contents[indx])
                    indx += 1
                elif component == 'choice':
                    self.content = Choice(self)
                    self.content.fromDom(contents[indx])
                    indx += 1
                elif component == 'sequence':
                    self.content = Sequence(self)
                    self.content.fromDom(contents[indx])
                    indx += 1
                elif component == 'group':
                    self.content = ModelGroupReference(self)
                    self.content.fromDom(contents[indx])
                    indx += 1
                else:
	            self.content = None

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
                   annotation?, (attribute | attributeGroup)*, anyAttribute?
            """
            required = ['base']
            attributes = {'id':None, 
                'base':None }
            contents = {'xsd':['annotation', 'attribute', 'attributeGroup', 
                'anyAttribute']}

	    def __init__(self, parent):
                XMLSchemaComponent.__init__(self, parent)
                self.annotation = None
                self.attr_content = None

            def fromDom(self, node):
                self.setAttributes(node)
                contents = self.getContents(node)

                indx = 0
                num = len(contents)
                component = SplitQName(contents[indx].getTagName())[1]
                if component == 'annotation':
                    self.annotation = Annotation(self)
                    self.annotation.fromDom(contents[indx])
                    indx += 1
                    component = SplitQName(contents[indx].getTagName())[1]

                content = []
                while indx < num:
                    component = SplitQName(contents[indx].getTagName())[1]
                    if component == 'attribute':
                        if contents[indx].hasattr('ref'):
                            content.append(AttributeReference(self))
                        else:
                            content.append(LocalAttributeDeclaration(self))
                    elif component == 'attributeGroup':
                        content.append(AttributeGroupReference(self))
                    elif component == 'anyAttribute':
                        content.append(AttributeWildCard(self))
                    else:
	                raise SchemaError, 'Unknown component (%s)'\
                            %(contents[indx].getTagName())
                    content[-1].fromDom(contents[indx])
                    indx += 1
                self.attr_content = tuple(content)


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
        'final':lambda self: self._parent().getFinalDefault()}
    contents = {'xsd':['annotation', 'restriction', 'list', 'union']}

    def __init__(self, parent):
        XMLSchemaComponent.__init__(self, parent)
        self.annotation = None
        self.content = None
        self.attr_content = None

    def fromDom(self, node):
        self.setAttributes(node)
        contents = self.getContents(node)
        for child in contents:
            component = SplitQName(child.getTagName())[1]
            if component == 'annotation':
                self.annotation = Annotation(self)
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
            content = []
            self.attr_content = []

            for indx in range(len(contents)):
                component = SplitQName(contents[indx].getTagName())[1]
                if (component == 'annotation') and (not indx):
                    self.annotation = Annotation(self)
                    self.annotation.fromDom(contents[indx])
                    continue
                elif (component == 'simpleType') and (not indx or indx == 1):
                    content.append(AnonymousSimpleType(self))
                    content[-1].fromDom(contents[indx])
                elif component in RestrictionMarker.facets:
                    #print_debug('%s class instance, skipping %s' %(self.__class__, component))
                    pass
                else:
                    raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
            self.content = tuple(content)


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
        def __init__(self, parent):
            XMLSchemaComponent.__init__(self, parent)
            self.annotation = None
            self.content = None
            self.attr_content = None

        def fromDom(self, node):
            self.setAttributes(node)
            contents = self.getContents(node)
            content = []
            self.attr_content = []

            for indx in range(len(contents)):
                component = SplitQName(contents[indx].getTagName())[1]
                if (component == 'annotation') and (not indx):
                    self.annotation = Annotation(self)
                    self.annotation.fromDom(contents[indx])
                elif (component == 'simpleType'):
                    content.append(AnonymousSimpleType(self))
                    content[-1].fromDom(contents[indx])
                else:
                    raise SchemaError, 'Unknown component (%s)' %(i.getTagName())
            self.content = tuple(content)

    class List(XMLSchemaComponent):
        """<list>
           parents:
               simpleType
           attributes:
               id -- ID
               itemType -- QName, required or simpleType child.

           contents:
               annotation?, simpleType?
        """
        attributes = {'id':None, 
            'itemType':None }
        contents = {'xsd':['annotation', 'simpleType']}
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
                    self.annotation = Annotation(self)
                    self.annotation.fromDom(contents[indx])
                elif (component == 'simpleType'):
                    self.content = AnonymousSimpleType(self)
                    self.content.fromDom(contents[indx])
                    break
                else:
                    raise SchemaError, 'Unknown component (%s)' %(i.getTagName())

                 
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


if sys.version_info[:2] >= (2, 2):
    tupleClass = tuple
else:
    import UserTuple
    tupleClass = UserTuple.UserTuple

class TypeDescriptionComponent(tupleClass):
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
