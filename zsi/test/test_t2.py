import unittest, sys
from ZSI import *


class t2TestCase(unittest.TestCase):
    "Test case wrapper for old ZSI t2 test case"

    def checkt1(self):
        try: 
            ps = ParsedSoap(IN)
        except ParseException, e:
             FaultFromZSIException(e).AsSOAP(OUT)
             unittest.fail()
        except Exception, e:
            # Faulted while processing; assume it's in the
            # header.
            FaultFromException(e, 1).AsSOAP(OUT)
            unittest.fail()
        # We are not prepared to handle any actors or mustUnderstand elements.  
        # Arbitrary fault back with the first one found.  
        a = ps.WhatActorsArePresent() 
        if len(a): 
            FaultFromActor(a[0]).AsSOAP(OUT) 
            unittest.fail()
        mu = ps.WhatMustIUnderstand() 
        if len(mu): 
            uri, localname = mu[0] 
            FaultFromNotUnderstood(uri, localname).AsSOAP(OUT) 
            unitest.fail() 
           
        class Player: 
            '''Input class.''' 
            def __init__(self, name=None): 
                pass 
        Player.typecode = TC.Struct(Player, [ TC.String('Name', optional=1), 
                                            TC.Array('xsd:integer', TC.Integer(), 
                                            'Scores'), ], 'GetAverage') 
        class Average: 
            '''Output class.''' 
            def __init__(self, average): 
                self.average = average 
        Average.typecode = TC.Struct(Average, [ TC.Integer('average'), 
                                            ], 'GetAverageResponse', inline=1) 
                                            
        try: 
            #player = ps.Parse(Player.typecode) 
            player = ps.Parse(Player) 
        except EvaluateException, e: 
            FaultFromZSIException(e).AsSOAP(OUT) 
            unittest.fail() 
            
        def bar(total, len): 
            return total / len 
        
        def foo(total, len): 
            return bar(total, len) 
        
        try: 
            import operator 
            total = reduce(operator.add, player.Scores, 0)
            result = Average(foo(total, len(player.Scores)))
            #sw = SoapWriter(OUT)
            #sw.serialize(result).close()
            #sw.serialize(result, Average.typecode)
            #sw.close()
            SoapWriter(OUT).serialize(result) 
        except Exception, e: 
            FaultFromException(e, 0, sys.exc_info()[2]).AsSOAP(OUT) 
            unittest.fail()


def makeTestSuite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(t2TestCase, "check"))
    return suite

OUT = sys.stdout
IN='''<SOAP-ENV:Envelope
 xmlns="http://www.example.com/schemas/TEST"
 xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
 xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"
 xmlns:ZSI="http://www.zolera.com/schemas/ZSI/">
 <SOAP-ENV:Header>
   <trans SOAP-ENV:mustUnderstand="0"/>
 </SOAP-ENV:Header>
 <SOAP-ENV:Body>
   <GetAverage>
     <Scores SOAP-ENC:arrayType="xsd:integer">
       <i>84</i>
       <xxi>101</xxi>
       <foi>200</foi> 
       <izzz>4</izzz> 
     </Scores> 
     <Name>John Doe</Name> 
   </GetAverage>
 </SOAP-ENV:Body> 
</SOAP-ENV:Envelope>'''

def main():
    unittest.main(defaultTest="makeTestSuite")


if __name__ == "__main__" : main()

