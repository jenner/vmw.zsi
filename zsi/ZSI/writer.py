#! /usr/bin/env python
# $Header$
'''SOAP message serialization.
'''

from ZSI import _copyright, ZSI_SCHEMA_URI
from ZSI import _stringtypes, _seqtypes
from ZSI.TC import TypeCode
try:
    from xml.dom.ext import Canonicalize
    from xml.ns import XMLNS, SOAP, SCHEMA
except:
    from ZSI.compat import Canonicalize, XMLNS, SOAP, SCHEMA
import types

_standard_ns = [ ('xml', XMLNS.XML), ('xmlns', XMLNS.BASE) ]

_reserved_ns = {
	'SOAP-ENV': SOAP.ENV,
	'SOAP-ENC': SOAP.ENC,
	'ZSI': ZSI_SCHEMA_URI,
	'xsd': SCHEMA.BASE,
	'xsi': SCHEMA.BASE + '-instance',
}

class SoapWriter:
    '''SOAP output formatter.'''

    def __init__(self, out, **kw):
	self.out, self.callbacks, self.memo, self.closed = \
	    out, [], [], 0
	nsdict = kw.get('nsdict', {})
	self.envelope = kw.get('envelope', 1)

	if not self.envelope: return
	print >>self, '<SOAP-ENV:Envelope\n' \
	    ' xmlns:SOAP-ENV="%(SOAP-ENV)s"\n' \
	    ' xmlns:SOAP-ENC="%(SOAP-ENC)s"\n' \
	    ' xmlns:xsi="%(xsi)s"\n' \
	    ' xmlns:xsd="%(xsd)s"\n' \
	    ' xmlns:ZSI="%(ZSI)s"' % _reserved_ns,
	if nsdict: self.writeNSdict(nsdict)
	print >>self, '>'
	header = kw.get('header', None)
	if header:
	    print >>self, '<SOAP-ENV:Header>'
	    if type(header) in _stringtypes:
		print >>self, header,
		if header[-1] not in ['\r', '\n']: print >>self
	    else:
		for n in header:
		    Canonicalize(n, self, nsdict=nsdict)
		    print >>self
	    print >>self, '</SOAP-ENV:Header>'
	print >>self, '<SOAP-ENV:Body>'

    def serialize(self, pyobj, typecode=None, root=None, **kw):
	'''Serialize a Python object to the output stream.
	'''
	if typecode == None: typecode = pyobj.__class__.__dict__['typecode']
	if TypeCode.typechecks and type(pyobj) == types.InstanceType and \
	not typecode.__dict__.has_key('pyclass'):
	    pass
	    # XXX XML ...
#	    raise TypeError('Serializing Python object with other than Struct.')
	kw = kw.copy()
	if root in [ 0, 1 ]:
	    kw['attrtext'] = ' SOAP-ENC:root="%d"' % root
	typecode.serialize(self, pyobj, **kw)
	return self

    def write(self, arg):
	'''Write convenience function; writes a string, but will also
	iterate through a sequence (recursively) of strings.
	'''
	if type(arg) in _seqtypes:
	    W = self.out.write
	    for a in arg:
		if a != None: W(a)
	else:
	    self.out.write(arg)

    def writeNSdict(self, nsdict):
	'''Write a namespace dictionary, taking care to not clobber the
	standard (or reserved by us) prefixes.
	'''
	for k,v in nsdict.items():
	    if (k,v) in _standard_ns: continue
	    rv = _reserved_ns.get(k, None)
	    if rv:
		if rv != v:
		    raise KeyError("Reserved namespace " + str((k,v)) + " used")
		continue
	    if k:
		print >>self, '\n  xmlns:%s="%s"' % \
			(k, v.replace('"', "&quot;")),
	    else:
		print >>self, '\n  xmlns="%s"' % v.replace('"', "&quot;"),

    def ReservedNS(self, prefix, uri):
	'''Is this namespace (prefix,uri) reserved by us?
	'''
	return _reserved_ns.get(prefix, uri) != uri

    def AddCallback(self, func, *arglist):
	'''Add a callback function and argument list to be invoked before
	closing off the SOAP Body.
	'''
	self.callbacks.append((func, arglist))

    def Known(self, obj):
	'''Seen this object (known by its id()?  Return 1 if so,
	otherwise add it to our memory and return 0.
	'''
	obj = id(obj)
	if obj in self.memo: return 1
	self.memo.append(obj)
	return 0

    def Forget(self, obj):
	'''Forget we've seen this object.
	'''
	obj = id(obj)
	try:
	    self.memo.remove(obj)
	except ValueError:
	    pass

    def close(self, trailer=None, nsdict=None):
	'''Invoke all the callbacks, and close off the SOAP message.
	'''
	for func,arglist in self.callbacks:
	    apply(func, (self,) + arglist)
	print >>self, '</SOAP-ENV:Body>'
	if type(trailer) in _stringtypes:
	    print >>self, trailer
	elif trailer != None:
	    for n in trailer:
		Canonicalize(n, self, nsdict=nsdict or _reserved_ns)
		print >>self
	if not self.envelope: print >>self, '</SOAP-ENV:Envelope>'
	self.closed = 1

    def __del__(self):
	if not self.closed: self.close()

if __name__ == '__main__': print _copyright
