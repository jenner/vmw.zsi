#!/usr/bin/env python

############################################################################
# David W. Robertson, LBNL
# See LBNLCopyright for copyright notice!
###########################################################################
import sys, unittest
from ZSI import FaultException

import utils
from paramWrapper import ParamWrapper
from clientGenerator import ClientGenerator

"""
Unittest for contacting the FreeDB Web service.

WSDL:  http://soap.systinet.net:6080/FreeDB/
"""

class FreeDBServiceTest(unittest.TestCase):
    """Test case for FreeDBService Web service
    """

    def setUp(self):
        """unittest calls setUp and tearDown after each
           test method call.
        """
        global testdiff
        global FreeDBService

        if not testdiff:
            testdiff = utils.TestDiff(self, 'generatedCode')
            testdiff.setDiffFile('FreeDBService.diffs')

        #kw = {'tracefile':sys.stdout}
        kw = {}
        FreeDBService = service.JavaServiceLocator().getFreeDBService(**kw)
    
    def test_getDetails(self):
        request = service.FreeDBService_getDetails_1_RequestWrapper()
        request._title = 'Hollywood Town Hall'
        request._discId = '8509ff0a'
        request._artist = 'Jayhawks'
        request._category = 'rock'
        response = FreeDBService.getDetails(request)
        print ParamWrapper(response)

    def test_search(self):
        response = FreeDBService.search('Ted Nugent and the Amboy Dukes')
        print ParamWrapper(response)

    def test_searchByTitle(self):
        response = FreeDBService.searchByTitle('Ummagumma')
        print ParamWrapper(response)

    def test_searchByTrack(self):
        response = FreeDBService.searchByTrack('Species of Animals')
        print ParamWrapper(response)

    def test_searchByArtist(self):
        response = FreeDBService.searchByArtist('Steppenwolf')
        print ParamWrapper(response)
    

def setUp():
    global testdiff
    global deleteFile
    global service

    deleteFile = utils.handleExtraArgs(sys.argv[1:])
    testdiff = None
    service = ClientGenerator().getModule('complex_types',
                                   'com.systinet.demo.freedb.FreeDBService',
                                   'generatedCode')
    return service


def makeTestSuite():
    suite = unittest.TestSuite()
    if service:
        suite.addTest(unittest.makeSuite(FreeDBServiceTest, 'test_'))
    return suite


def main():
    if setUp():
        utils.TestProgram(defaultTest="makeTestSuite")
                  

if __name__ == "__main__" : main()
