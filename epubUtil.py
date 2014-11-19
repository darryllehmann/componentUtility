#!/usr/local/bin/python

from __future__ import with_statement

__license__ = """
    Copyright (c) 2014, Will Manis
    All rights reserved.

    Redistribution and use in source and binary forms, with or without
    modification, are permitted provided that the following conditions are met:

    1. Redistributions of source code must retain the above copyright notice, this
       list of conditions and the following disclaimer.
    2. Redistributions in binary form must reproduce the above copyright notice,
       this list of conditions and the following disclaimer in the documentation
       and/or other materials provided with the distribution.

    THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
    ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
    WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
    DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
    ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
    (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
    LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
    ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
    (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
    SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

    The views and conclusions contained in the software and documentation are those
    of the authors and should not be interpreted as representing official policies,
    either expressed or implied, of the FreeBSD Project.
"""

import os
import zipfile
import posixpath
import urllib
import time
import xmlom
import xmlElement

__author__ = 'wmanis'

componentDirectory = 'components'
componentNamespace = 'component: http://www.idpf.org/vocab/component/#'


def getCollectionCreatorAndName(collection):
    creatorName = { 'creator': None, 'name' : None }

    metadata = xmlom.findChildrenByTagName(collection, 'metadata')
    if len(metadata) == 1:
        metas = xmlom.findChildrenByTagName(metadata[0], 'meta')
        for meta in metas:
            propval = xmlElement.getAttributeValue(meta, 'property')
            if propval == "component:creator":
                creatorName['creator'] =  xmlElement.getText(meta)
            elif propval == "component:name":
                creatorName['name'] =  xmlElement.getText(meta)
    return creatorName

#---------------------------------------------------------------------------
def getComponentDir(creator, name):
    return posixpath.normpath(posixpath.join(componentDirectory, creator, name))

# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
class EPUBSpineItem:
    def __init__(self, zipfile, path):
        self.zipfile_ = zipfile
        self.path_ = path
        self.spineXML_ = xmlom.XMLOM(self.zipfile_.getBytes(path))

    def insert(self, elementID, src):
        def walk(node, elementid):
            attributes = xmlElement.getAttributes(node)
            for attr in attributes:
                if attr == 'id' and attributes[attr] == elementid:
                    return node

            children = xmlElement.getChildElements(node)
            for child in children:
                id = walk(child, elementid)
                if id != None:
                    return id
            return None

        node = walk(self.spineXML_.getRootElement(), elementID)
        if node != None:
            xmlElement.setAttribute(node, 'src', src)
            return

        raise "no element with that id"


    def tostring(self):
        lines = self.spineXML_.toPrettyXML()
        lines = lines.split('\n')

        trimmedlines = []
        for line in lines:
            line = line.rstrip()
            if len(line) != 0:
                trimmedlines.append(line)

        print "\n\nPatched html file\n==============================================="
        print "==============================================="
        print '\n'.join(trimmedlines)
        print "==============================================="
        print "===============================================\n\n"
        return '\n'.join(trimmedlines)


    def update(self):
        self.zipfile_.putfile(self.path_, self.tostring())


# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
class PackageDom(xmlom.XMLOM):
    def getPackageElement(self):
        return self.getRootElement()

    # ---------------------------------------------------------------------------
    # get the manifest

    def getManifest(self):
        return self.findChildrenByTagName(self.getRootElement(), 'manifest')[0]

    # ---------------------------------------------------------------------------
    # get the manifest

    def getManifestItems(self):
        items = []
        for item in self.getManifest().childNodes:
            if xmlElement.isElement(item):
                items.append(item)

        return items


    # ---------------------------------------------------------------------------
    # get the metadata

    def getMetadata(self):
        return self.findAllByTagName('metadata')[0]

    # ---------------------------------------------------------------------------
    # get the metadata

    def getMetadataItems(self):
        return self.findChildrenByTagName(self.getMetadata(), 'meta')

    #---------------------------------------------------------------------------
    # get the metadata with attr & value

    def getOpfMetadataItemsByAttr(self, name, value = None):
        items = []

        metadataitems = self.getMetadataItems()

        for item in metadataitems:
            itemValue = xmlElement.getAttributeValue(item, name)
            if itemValue == None:
                # no attribute with that value - continue
                continue
            elif value == None:
                # we don't care about value, so this is a match
                items.append(item)
            elif itemValue == value:
                # we care about, so this is a match
                items.append(item)
            # elif itemValue!= value:
            #   this is not a match

        return items


    #---------------------------------------------------------------------------
    # get the spine

    def getSpine(self):
        return self.findAllByTagName('spine')[0]

    #---------------------------------------------------------------------------
    # get the spine items

    def getSpineItems(self):
        return self.findChildrenByTagName(self.getSpine(), 'itemref')

    #---------------------------------------------------------------------------
    # get the collections

    def getCollections(self):
        return self.findChildrenByTagName(self.getRootElement(), 'collection')

    #---------------------------------------------------------------------------
    # get the component collections

    def getComponentCollections(self):
        collections = self.getCollections()
        found = 0

        for collection in collections:
           if xmlElement.getAttributeValue(collection, 'role') != 'component:component':
               collections.remove(collection)
        return collections

    #---------------------------------------------------------------------------
    # get a component collection

    def getComponentCollection(self, vendor, componentName):
        collections = self.getCollections()
        found = 0

        for collection in collections:
            metadata = self.findChildrenByTagName(collection, 'metadata')
            if len(metadata) == 1:
                metas = self.findChildrenByTagName(metadata[0], 'meta')
                for meta in metas:
                    #<meta property="component:creator">Acme</meta>
                    #<meta property="component:name">Gallery_example</meta>
                    propval = xmlElement.getAttributeValue(meta, 'property')
                    if propval == "component:creator" and xmlElement.getText(meta) == vendor:
                        found += 1
                    elif propval == "component:name" and xmlElement.getText(meta) == componentName:
                        found += 1
                    if found == 2:
                        return collection
        return None


# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
class EPUBZipContainer:


    def __init__(self, name, opt = 'r', debug=False):
        self.name_ = name
        self.zipfile_ = zipfile.ZipFile(name, opt)
        self.__unzip()
        self.opfpath_ = None

        if len(self.names_) == 0:
            # this is a blank epub, need to create an opf file and meta-inf
            self.createMetaInf()
            self.createPackageFile()

        self.getOpfPath()
        self.packagedom_ = PackageDom(self.contents_[self.opfpath_])

        self.debug_ = debug


    # ------------------------------------------------------------------------------
    # interface definition

    def createMetaInf(self):
        pass

    # ------------------------------------------------------------------------------
    # interface definition

    def createPackageFile(self):
        pass


    # ---------------------------------------------------------------------------
    # get original zipfile
    def __unzip(self):
        self.names_ = self.zipfile_.namelist()
        self.contents_ = {}
        for name in self.names_:
            self.contents_[name] = self.zipfile_.read(name)

    # ---------------------------------------------------------------------------
    # update original
    def close(self):
        mergedName = posixpath.normpath(posixpath.join(posixpath.splitext(self.name_)[0] + ".merged.epub"))
        if os.path.exists(mergedName):
            os.remove(mergedName)
        newzipfile = zipfile.ZipFile(mergedName, 'a')

        newzipfile.writestr('mimetype', self.contents_['mimetype'])
        self.contents_.pop('mimetype')

        for name in self.contents_:
            newzipfile.writestr(name, self.contents_[name])


    # ---------------------------------------------------------------------------
    # get original zipfile

    def getBytes(self, name):
        return self.contents_[name]

    # ---------------------------------------------------------------------------
    # get the path to the opf file from container.xml

    def getOpfPath(self):
        if self.opfpath_ == None:
            xmlDom = xmlom.XMLOM(self.contents_['META-INF/container.xml'])
            root = xmlDom.findAllByTagName('rootfile')[0]
            self.opfpath_ = xmlDom.getAttribute(root, 'full-path')
        return self.opfpath_


    # ---------------------------------------------------------------------------
    # get the package xmldom

    def getOpfDom(self):
        if self.packagedom_ == None:
            path = self.getOpfPath()
            opfXML = self.contents_[path]
            self.packagedom_ = xmlom.XMLOM(opfXML)
        return self.packagedom_

    # ---------------------------------------------------------------------------
    # get the package xmldom

    def getfile(self, path):
        return self.contents_[path]

    #---------------------------------------------------------------------------
    # get the package xmldom

    def putfile(self, path, text):
        self.contents_[path] = text


    #---------------------------------------------------------------------------
    # get the manifest

    def getOpfManifest(self):
        return self.packagedom_.getManifest()


    #---------------------------------------------------------------------------
    # get the manifest

    def getOpfManifestItems(self):
        return self.packagedom_.getManifestItems()


    #---------------------------------------------------------------------------
    # get the metadata

    def getOpfMetadata(self):
        return self.packagedom_.getMetadata()

    #---------------------------------------------------------------------------
    # get the spine

    def getOpfSpine(self):
        return self.packagedom_.getSpine()

    #---------------------------------------------------------------------------
    # get the spine items

    def getOpfSpineItems(self):
        return self.packagedom_.getSpineItems()

    #---------------------------------------------------------------------------
    def getSpineItemPath(self, xmlid):
        manifest = self.getOpfManifestItems()

        for item in manifest:
            if xmlElement.getAttributeValue(item, 'id') == xmlid:
                return xmlElement.getAttributeValue(item, 'href')
        return None


    #---------------------------------------------------------------------------
    # get spineitem files
    def getOpfSpineItemFiles(self):
        spinefiles = []
        spineitems = self.getOpfSpineItems()

        for itemref in spineitems:
            idref = xmlElement.getAttributeValue(itemref, 'idref')
            spinefiles.append(self.getSpineItemPath(idref))

        return spinefiles

    #---------------------------------------------------------------------------
    # get the spine items

    def getOpfCollections(self):
        return self.packagedom_.getCollections()

    #---------------------------------------------------------------------------
    # debug - print out opf

    def printOPF(self):
        path = self.getOpfPath()
        opfXML = self.contents_[path]
        print opfXML

    #---------------------------------------------------------------------------

    def getComponentRelativePath(self, componentDir):
        dstOPFPath = self.getOpfPath()
        return os.path.relpath(componentDir, os.path.dirname(dstOPFPath))

    #---------------------------------------------------------------------------
    # transfer component assets and update the destination opf file

    def transferItems(self, srcComponent, dstDir):

        # get items from manifest for transfer
        itemList = srcComponent.getOpfManifestItems()

        srcOpfDir = posixpath.dirname(srcComponent.getOpfPath())

        for item in itemList:
            if xmlElement.getAttributeValue(item, 'properties') == 'nav':
                #do not copy nav doc
                continue

            href = xmlElement.getAttributeValue(item, 'href')
            srcPath = posixpath.normpath(posixpath.join(srcOpfDir, href))
            dstPath = posixpath.normpath(posixpath.join(dstDir, href.split('../').pop()))

            # copy the bytes over
            srcbytes = srcComponent.getfile(srcPath)
            self.putfile(dstPath, srcbytes)


    #---------------------------------------------------------------------------
    # build the collection containing the component

    def buildCollection(self, dstComponentDir, items, srcMetadata, idref, vendorName, componentName):
        rootElement = self.getOpfDom().getPackageElement()

        # add comment
        commentString = ' start of component ' + vendorName + ' - ' + componentName + ' transfer time ' + time.asctime(
            time.gmtime()) + ' UTC '
        xmlElement.addComment(rootElement, commentString)

        # add collection
        collection = xmlElement.addChildElement(rootElement, 'collection', {'role': 'component:component'})

        # add metadata to collection
        metadata = xmlElement.addChildElement(collection, 'metadata')

        for datum in srcMetadata:
            meta = xmlElement.addChildElement(metadata, 'meta')
            xmlElement.setAttribute(meta, 'property', datum['property'])
            xmlElement.addTextNode(meta, datum['value'])

        # add manifest collection to collection
        collectionManifest = xmlElement.addChildElement(collection, 'collection', {'role': 'manifest'})
        component = None

        for item in items:
            link = xmlElement.addChildElement(collectionManifest, "link")
            if idref == xmlElement.getAttributeValue(item, 'id'):
                component = item

            href = xmlElement.getAttributeValue(item, 'href')
            dstPath = posixpath.normpath(posixpath.join(dstComponentDir, href))
            xmlElement.setAttribute(link, 'href', dstPath)


        # add the html of the component
        link = xmlElement.addChildElement(collection, 'link')
        href = posixpath.normpath(posixpath.join(dstComponentDir, xmlElement.getAttributeValue(component, 'href')))
        xmlElement.setAttribute(link, 'href', href)

    #---------------------------------------------------------------------------
    # add the component items to the manifest

    def addManifestItems(self, dstComponentDir, items, vendorName, componentName):

        # get the manifest element of the package file
        dstManifest = self.getOpfManifest()

        # add comment to indicate start component items
        xmlElement.addComment(dstManifest,
                              ' start of component manifest items ' + vendorName + ' - ' + componentName + ' ')

        idprefix = vendorName + '_' + componentName + '_'

        for item in items:
            newitem = xmlElement.addChildElement(dstManifest, item.localName)

            attributes = xmlElement.getAttributes(item)

            for attr in attributes:
                value = attributes[attr]
                if attr == 'href':
                    href = posixpath.normpath(posixpath.join(dstComponentDir, value))
                    xmlElement.setAttribute(newitem, 'href', href)
                elif attr != 'id':
                    xmlElement.setAttribute(newitem, attr, value)
                else:
                    xmlElement.setAttribute(newitem, attr, idprefix + value)

        # add comment to indicate end of component items
        xmlElement.addComment(dstManifest,
                              ' end of component manifest items ' + vendorName + ' - ' + componentName + ' ')

    #---------------------------------------------------------------------------
    # transfer data into the destintation package file
    def transferMetadata(self, srcComponent, dstComponentDir, vendorName, componentName):

        # get the component items, ignoring the nav doc
        items = srcComponent.getOpfManifestItems()
        for item in items:
            if xmlElement.getAttributeValue(item, 'properties') == 'nav':
                items.remove(item)
                break

        # get the idref of the component base html doc
        srcSpineItems = srcComponent.getOpfSpineItems()
        assert (len(srcSpineItems) == 1)
        idref = xmlElement.getAttributeValue(srcSpineItems[0], 'idref')

        # create component collection
        self.buildCollection(dstComponentDir, items, srcComponent.getComponentMetadata(), idref, vendorName,
                             componentName)

        # copy over component items into manifest
        self.addManifestItems(dstComponentDir, items, vendorName, componentName)

        # ensure component vocab is present
        package = self.getOpfDom().getPackageElement()
        prefix = xmlElement.getAttributeValue(package, 'prefix')
        if prefix == None:
            xmlElement.setAttribute(package, 'prefix', componentNamespace)
        elif prefix.find(componentNamespace) < 0:
            xmlElement.setAttribute(package, 'prefix', prefix + ' ' + componentNamespace)

        if self.debug_:
            print "\n\nIntegrated package file\n==============================================="
            print "==============================================="
            print self.getOpfDom().toPrettyXML()
            print "==============================================="
            print "===============================================\n\n"
        # write out the updated manifest
        self.putfile(self.getOpfPath(), self.getOpfDom().toPrettyXML())

    def testComponentExistance(self, creator, name ):
        collections = self.getOpfDom().getComponentCollections()

        for collection in collections:
            creatorname = getCollectionCreatorAndName(collection)
            if creatorname['creator'] == creator and  creatorname['name'] == name:
                return True

        return False

#------------------------------------------------------------------------------
#------------------------------------------------------------------------------
class ComponentZipContainer(EPUBZipContainer):
    prefix = 'component'
    namespace = 'component:http://www.idpf.org/vocab/component/#'

    #------------------------------------------------------------------------------

    def __init__(self, name, creator = None, componentName = None, debug=True):
        self.creator_ = creator
        self.componentName_ = componentName
        if self.creator_ == None:
            opt = 'r'
        else:
            opt = 'a'
        EPUBZipContainer.__init__(self, name, opt, debug)

    #------------------------------------------------------------------------------
    # create the metainf for this epub

    def createMetaInf(self):
        # TODO verify this is correct
        opfpath = '"' + posixpath.normpath(posixpath.join(self.componentName_, 'content.opf')) + '"'
        blank_metainf = """<?xml version="1.0" encoding="UTF-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
   <rootfiles>
      <rootfile full-path=""" + opfpath + """ media-type="application/oebps-package+xml"/>
   </rootfiles>
</container>"""
        self.contents_['META-INF/container.xml'] = blank_metainf

    #------------------------------------------------------------------------------
    # create a boiler plate package file, to be filled in with real data

    def createPackageFile(self):
        blank_packagefile = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" xml:lang="en" unique-identifier="uid"
	 prefix="component: http://www.idpf.org/vocab/component/#">
   <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
   </metadata>
   <manifest>
   </manifest>
   <spine>
   </spine>
</package>"""

        self.contents_[posixpath.normpath(posixpath.join(self.componentName_, 'content.opf'))] = blank_packagefile

    #------------------------------------------------------------------------------
    # get the component metadata from the opf

    def extract(self, srcEpub):
        print "Extract: ", self.creator_, self.componentName_
        collection = srcEpub.getOpfDom().getComponentCollection(self.creator_, self.componentName_)
        self.copyMetadata(collection)


        self.buildManifest(collection)


    #------------------------------------------------------------------------------
    # copy over meta data

    def copyMetadata(self, collection):
        srcMetadata = xmlElement.findFirstChildElement(collection, 'metadata')
        srcMetadatas = xmlElement.getChildElements(srcMetadata)

        dstMetadata = self.getOpfDom().getMetadata()

        for meta in srcMetadatas:
            newmeta = xmlElement.addChildElement(dstMetadata, meta.localName, xmlElement.getAttributes(meta))
            xmlElement.addTextNode(newmeta, xmlElement.getText(meta))

        #print xmlElement.toPrettyXML(srcMetadata)



    #------------------------------------------------------------------------------
    # copy over meta data

    def buildManifest(self, collection):
        srcManifest = xmlElement.findFirstChildElement(collection, 'collection', {'role': 'manifest'})
        manifestitems = xmlElement.getChildElements(srcManifest)

        dstManifest = self.getOpfDom().getManifest()

        for item in manifestitems:
            newitem = xmlElement.addChildElement(dstManifest, item.localName, xmlElement.getAttributes(item))
            # TODO make more robust
            href = xmlElement.getAttributeValue(newitem, 'href')
            parts = href.split(self.creator_ + '/')
            xmlElement.setAttribute(newitem, 'href', parts[1])


        #print xmlElement.toPrettyXML(dstManifest)



    #------------------------------------------------------------------------------
    # get the component metadata from the opf

    def getComponentMetadata(self):
        componentMetadatum = []

        metadataItems = self.getOpfDom().getMetadataItems()
        for meta in metadataItems:
            prop = xmlElement.getAttributeValue(meta, 'property')
            if prop != None:
                componentMetadatum.append({'property': prop, 'value': xmlElement.getText(meta)})

        return componentMetadatum

    #------------------------------------------------------------------------------
    # get the component metadata from the opf

    def getComponentManifest(self):
        componentManifest = []
        manifestItems = self.getOpfManifestItems()
        for item in manifestItems:
            componentManifest.append({'property': item.get('property'), 'value': item.text})
        return componentManifest

    #------------------------------------------------------------------------------
    # get component base html

    def getComponentHTML(self):
        return self.getOpfSpineItemFiles()[0]


    #---------------------------------------------------------------------------
    # get the component creator and name from the meta properties

    def getComponentCreatorAndName(self):
        creatorProp = self.prefix + ":creator"
        nameProp = self.prefix + ":name"

        metadata = self.getComponentMetadata()
        for meta in metadata:
            if meta['property'] == creatorProp:
                self.creator_ = meta['value']
            if meta['property'] == nameProp:
                self.componentName_ = meta['value']

        if self.creator_ != None and self.componentName_ != None:
            return {'creator': urllib.quote(self.creator_), 'name': urllib.quote(self.componentName_)}

        return {'creator': None, 'name': None }
    #---------------------------------------------------------------------------
    # get the component creator and name from the meta properties

    def setComponentCreatorAndName(self, creator, name):
        creatorProp = self.prefix + ":creator"
        nameProp = self.prefix + ":name"

        metadata = self.getComponentMetadata()
        for meta in metadata:
            if meta['property'] == creatorProp:
                meta['value'] = creator
            if meta['property'] == nameProp:
                meta['value'] = name
